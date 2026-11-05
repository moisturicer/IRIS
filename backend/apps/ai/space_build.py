"""Building a pending Embedding Space beside the active one (IR-752).

ADR-049 §23: a model upgrade is built next to the live index, checked, and only
then promoted -- never by mutating the active index in place. This module is the
build and the check. **It cannot activate a space**; promotion and rollback are
IR-739, and nothing here imports ``apps.ai.promotion``'s ``promote``.

**Isolation is by construction, not by filter.** A build writes ``(record,
space)`` and ``(chunk, space)`` rows for the *pending* space only, and refuses
any space that is not pending. It never touches ``RecordEmbedding``, which holds
one vector per record for the live space, so every reader -- two-stage
retrieval, similarity, the status counts, the research tools -- sees exactly
what it saw before, whatever state the build is in.

**Pinned identity.** The space row is the identity: model id, dimensions,
metric. The provider must name the same model (``EmbeddingProvider.model_id``)
and emit the same width, or nothing is sent. Document and query semantics are
pinned by the port itself (ADR-015 rule 3): a build can only call
``embed_documents`` and ``embed_document_chunks``, and a reader only
``embed_query``. The source revision is pinned per vector: a summary vector
carries the hash of the text it was computed from, and passage vectors are
written only against the chunk set, and manuscript revision, that was active
when the record's turn began.

**Bounded, restartable, redeliverable.** What a build embeds is "owed" work,
recomputed from the database on every call: a summary with no current vector,
and active chunks with no vector in the space. A crash, a stop or a duplicate
delivery therefore resumes where it stopped; vectors already stored -- and paid
for -- are kept, and a finished build costs queries and no vendor call. A
session advisory lock per ``(space, record)`` (it needs a direct or
session-pooled connection, not a transaction-pooling proxy) makes a duplicate delivery skip a
record another worker is embedding instead of paying for it twice. This is not
exactly-once billing: a send that is lost between the vendor and the commit is
paid for and sent again, under a new admission.

**Every attempt is checked.** Embedding runs on the ``ingestion`` lane, so each
vendor request goes through the shared provider admission; the disclosure gate
is evaluated before each record's send and again inside the outbound fence; and
the passage write re-checks that the chunk set it embedded is still the active
one. An admission refusal stops the run -- the next record would meet the same
ledger -- and what finished stays.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Optional, Sequence

from django.db import connection

from apps.ai import indexing
from apps.ai.admission.errors import AdmissionDenied
from apps.ai.admission.scope import charged_to
from apps.ai.indexing import (
    embed_active_chunk_set,
    embed_record_summary,
    pending_chunks,
    record_source_hash,
    summary_text,
)
from apps.ai.providers.ports import EmbeddingProvider

__all__ = [
    "BuildRefused",
    "BuildReport",
    "Readiness",
    "build_pending_space",
    "pinned_space",
    "record_lock_keys",
    "record_source_hash",
    "space_readiness",
    "stored_dimension_mismatches",
]

STOPPED_MAX_RECORDS = "max_records"
STOPPED_TOKEN_BUDGET = "token_budget"
#: The space left the pending state while the build ran.
STOPPED_NOT_PENDING = "space_not_pending"
#: ``admission:<reason>`` when the shared ledger refused an attempt.
STOPPED_ADMISSION = "admission:"

#: High half of the two-int advisory-lock key. Only needs to differ from the
#: other users of that form; the space id is added so spaces do not contend.
_LOCK_NAMESPACE = 752 << 20


class BuildRefused(Exception):
    """The target or the provider is not something a build may write with."""


@dataclass
class BuildReport:
    """What one bounded build did. Accumulated as it goes, so it is still true
    when the run stops half way."""

    space_id: int
    records_built: int = 0
    summaries_embedded: int = 0
    passages_embedded: int = 0
    records_already_built: int = 0
    estimated_tokens: int = 0
    refused: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    busy: list = field(default_factory=list)
    #: Why the run ended early; empty when it walked every record.
    stopped: str = ""

    def as_dict(self) -> dict:
        return {
            "space_id": self.space_id,
            "records_built": self.records_built,
            "summaries_embedded": self.summaries_embedded,
            "passages_embedded": self.passages_embedded,
            "records_already_built": self.records_already_built,
            "estimated_tokens": self.estimated_tokens,
            "refused": list(self.refused),
            "failed": list(self.failed),
            "busy": list(self.busy),
            "stopped": self.stopped,
        }


def pinned_space(space_id: int, provider: EmbeddingProvider):
    """The pending space ``provider`` is allowed to fill, or ``BuildRefused``.

    Everything that can be known for free is checked here, before any send.
    """
    from apps.ai.models import (
        VECTOR_COLUMN_DIMENSIONS,
        EmbeddingSpace,
        EmbeddingSpaceState,
        assert_embedding_space_consistent,
    )

    assert_embedding_space_consistent(VECTOR_COLUMN_DIMENSIONS, context="indexing")
    space = EmbeddingSpace.objects.filter(pk=space_id).first()
    if space is None:
        raise BuildRefused(f"No EmbeddingSpace with id {space_id}.")
    if space.state != EmbeddingSpaceState.PENDING:
        raise BuildRefused(
            f"Space {space.pk} is {space.state}. Only a pending space is built; "
            f"writing into the active one would mutate the live index in place, "
            f"and a retired one is read by nothing."
        )
    if space.dimensions != VECTOR_COLUMN_DIMENSIONS:
        raise BuildRefused(
            f"Space {space.pk} is {space.dimensions} dimensions but the vector "
            f"columns hold {VECTOR_COLUMN_DIMENSIONS}."
        )
    if space.metric != "cosine":
        raise BuildRefused(
            f"Space {space.pk} uses the {space.metric!r} metric; the vector "
            f"indexes are cosine."
        )
    if provider.model_id is None or provider.model_id != space.model_id:
        raise BuildRefused(
            f"The embedding provider names model {provider.model_id!r} but space "
            f"{space.pk} is pinned to {space.model_id!r}. A build refuses a "
            f"provider that cannot be shown to be the space's model."
        )
    if provider.dimensions != space.dimensions:
        raise BuildRefused(
            f"The embedding provider emits {provider.dimensions} dimensions but "
            f"space {space.pk} is {space.dimensions}."
        )
    return space


def record_lock_keys(space_id: int, record_id: int) -> tuple[int, int]:
    return _LOCK_NAMESPACE + space_id, record_id


@contextmanager
def _claim(space_id: int, record_id: int):
    """Hold the ``(space, record)`` advisory lock, yielding whether we got it."""
    keys = record_lock_keys(space_id, record_id)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", keys)
        got = cursor.fetchone()[0]
    try:
        yield got
    finally:
        if got:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s, %s)", keys)


def _still_pending(space_id: int) -> bool:
    from apps.ai.models import EmbeddingSpace, EmbeddingSpaceState

    return EmbeddingSpace.objects.filter(
        pk=space_id, state=EmbeddingSpaceState.PENDING
    ).exists()


def _active_chunk_set(record_id: int):
    from apps.ai.models.chunk import ChunkSet

    return ChunkSet.objects.filter(record_id=record_id, is_active=True).first()


def _owed(record, space_id: int):
    """``(summary owed, pending chunks)`` for one record, from the database."""
    from apps.ai.models.embedding import RecordSpaceEmbedding

    stored = (
        RecordSpaceEmbedding.objects.filter(record_id=record.pk, space_id=space_id)
        .values_list("source_hash", flat=True)
        .first()
    )
    return stored != record_source_hash(record), pending_chunks(record.pk, space_id)


def _estimate(record, needs_summary: bool, chunks) -> int:
    from apps.ai.providers.batching import estimate_tokens

    tokens = sum(estimate_tokens(chunk.text) for chunk in chunks)
    return tokens + (estimate_tokens(summary_text(record)) if needs_summary else 0)


@charged_to("ingestion")
def build_pending_space(
    space_id: int,
    *,
    provider: Optional[EmbeddingProvider] = None,
    record_ids: Optional[Sequence[int]] = None,
    max_records: int = 0,
    token_budget: int = 0,
) -> BuildReport:
    """Embed what ``space_id`` still owes, up to the bounds, and report.

    ``max_records`` counts records that owed work and were attempted (one
    another worker holds is skipped and not counted); ``token_budget`` is an
    upper-bound estimate (the batching rule's own) and stops the run *before*
    the record that would exceed it, though a slice always takes its first
    record so an oversized one cannot stall the build. ``0`` means no bound. A record with no active chunks is not part of the corpus and is
    left alone, the same rule promotion uses.
    """
    from apps.ai.backfill import records_to_consider

    if provider is None:
        from apps.ai.models import EmbeddingSpace

        model = EmbeddingSpace.objects.filter(pk=space_id).values_list(
            "model_id", flat=True
        ).first()
        if model is None:
            raise BuildRefused(f"No EmbeddingSpace with id {space_id}.")
        # The space's own model, not the configured one: the live setting is
        # what readers embed queries with and must not move for a build.
        provider = indexing.build_embedding_provider(model=model)
    space = pinned_space(space_id, provider)
    report = BuildReport(space_id=space.pk)
    attempted = 0

    for record in records_to_consider(record_ids).iterator():
        active_set = _active_chunk_set(record.pk)
        if active_set is None:
            continue
        needs_summary, chunks = _owed(record, space.pk)
        if not needs_summary and not chunks:
            report.records_already_built += 1
            continue

        if max_records and attempted >= max_records:
            report.stopped = STOPPED_MAX_RECORDS
            break
        estimate = _estimate(record, needs_summary, chunks)
        # A slice always takes its first record, even one larger than the
        # budget: otherwise that record would stop every later slice too and
        # the build could never move past it.
        if (token_budget and report.estimated_tokens
                and report.estimated_tokens + estimate > token_budget):
            report.stopped = STOPPED_TOKEN_BUDGET
            break

        # A promotion (IR-739) or any other change of state ends the build:
        # from then on a write would mutate the live index in place.
        if not _still_pending(space.pk):
            report.stopped = STOPPED_NOT_PENDING
            break

        with _claim(space.pk, record.pk) as claimed:
            if not claimed:
                report.busy.append(record.pk)
                continue
            attempted += 1
            # Owed work is read again under the lock: the worker that held it
            # may have finished the record while this one waited its turn.
            needs_summary, chunks = _owed(record, space.pk)
            if not needs_summary and not chunks:
                report.records_already_built += 1
                continue
            report.estimated_tokens += estimate
            try:
                if _build_record(record, space, provider, active_set, needs_summary,
                                 bool(chunks), report):
                    report.records_built += 1
            except AdmissionDenied as denied:
                report.stopped = STOPPED_ADMISSION + denied.reason
                break
            except Exception as error:  # noqa: BLE001 - reported, and the run goes on
                report.failed.append((record.pk, str(error)))
    return report


def _build_record(record, space, provider, active_set, needs_summary, needs_passages, report) -> bool:
    """Embed one record's owed summary and passages. True when nothing refused."""
    if needs_summary:
        outcome = embed_record_summary(record.pk, provider=provider, space_id=space.pk)
        if outcome.refused:
            report.refused.append((record.pk, outcome.reason))
            return False
        report.summaries_embedded += outcome.embedded
    if needs_passages:
        outcome = embed_active_chunk_set(
            record.pk,
            provider=provider,
            space_id=space.pk,
            chunk_set_id=active_set.pk,
            source_revision=active_set.source_revision,
        )
        if outcome.refused:
            report.refused.append((record.pk, outcome.reason))
            return False
        report.passages_embedded += outcome.embedded
    return True


# -- readiness -----------------------------------------------------------------


@dataclass(frozen=True)
class Readiness:
    """Whether a space holds a complete, current, well-formed copy of the corpus.

    Read-only, calls no vendor. ``ready`` says a space *could* be promoted; it
    promotes nothing.
    """

    space_id: int
    state: str
    records_total: int
    summaries_built: int
    summaries_missing: int
    summaries_stale: int
    summaries_unverified: int
    passages_total: int
    passages_embedded: int
    passages_missing: int
    #: Stored vectors whose width is not the space's, plus one if the space
    #: itself does not match the columns.
    dimension_mismatches: int
    shortfalls: tuple = ()

    @property
    def ready(self) -> bool:
        return not (
            self.summaries_missing
            or self.summaries_stale
            or self.summaries_unverified
            or self.passages_missing
            or self.dimension_mismatches
        )


def stored_dimension_mismatches(space) -> int:
    """Stored vectors whose width is not the space's, plus one if the space
    itself does not match the columns. Shared with activation (IR-739)."""
    from apps.ai.models import VECTOR_COLUMN_DIMENSIONS

    mismatches = 0
    with connection.cursor() as cursor:
        for table in ("ai_chunkembedding", "ai_recordspaceembedding"):
            cursor.execute(
                f"SELECT count(*) FROM {table} WHERE space_id = %s AND vector_dims(embedding) <> %s",
                [space.pk, space.dimensions],
            )
            mismatches += cursor.fetchone()[0]
    if space.dimensions != VECTOR_COLUMN_DIMENSIONS:
        mismatches += 1
    return mismatches


def space_readiness(space_id: int) -> Readiness:
    from django.db.models import Q

    from apps.ai.models import EmbeddingSpace
    from apps.ai.models.chunk import ChunkEmbedding, DocumentChunk
    from apps.ai.models.embedding import RecordSpaceEmbedding
    from apps.ai.promotion import records_missing_vectors
    from apps.records.models import Record

    space = EmbeddingSpace.objects.get(pk=space_id)
    active = Q(chunk_set__is_active=True, deleted_at__isnull=True)
    corpus = Record.objects.filter(
        pk__in=DocumentChunk.objects.filter(active).values("record_id")
    ).order_by("pk")

    stored = dict(
        RecordSpaceEmbedding.objects.filter(space_id=space_id).values_list(
            "record_id", "source_hash"
        )
    )
    total = built = missing = stale = unverified = 0
    for record in corpus.iterator():
        total += 1
        if record.pk not in stored:
            missing += 1
        elif stored[record.pk] == "":
            unverified += 1
        elif stored[record.pk] != record_source_hash(record):
            stale += 1
        else:
            built += 1

    passages_total = DocumentChunk.objects.filter(active).count()
    passages_embedded = ChunkEmbedding.objects.filter(
        space_id=space_id, chunk__chunk_set__is_active=True, chunk__deleted_at__isnull=True
    ).count()

    mismatches = stored_dimension_mismatches(space)

    return Readiness(
        space_id=space.pk,
        state=space.state,
        records_total=total,
        summaries_built=built,
        summaries_missing=missing,
        summaries_stale=stale,
        summaries_unverified=unverified,
        passages_total=passages_total,
        passages_embedded=passages_embedded,
        passages_missing=passages_total - passages_embedded,
        dimension_mismatches=mismatches,
        shortfalls=tuple(records_missing_vectors(space_id)),
    )
