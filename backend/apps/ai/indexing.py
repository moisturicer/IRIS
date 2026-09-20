"""Turning stored text into vectors (IR-281, ADR-024).

Two things get embedded, and they are deliberately two functions rather than
one with a flag:

* a **record's summary** — title and abstract — which stage 1 of ADR-013's
  two-stage retrieval ranks records on, and which ADR-029 §5 also uses as the
  similarity source for proposal matching;
* a **record's active chunk set**, which stage 2 ranks passages within.

Both run **in Django's own process**, through ``EmbeddingProvider``. ADR-024
took this path off the AI gateway: the route the old task posted to was never
registered, the endpoint it aimed at returned no vector field, and the gateway
may hold no database connection anyway, so on this path it could only ever
have been a proxy for the vendor call with a 404 in front of it.

**What this module guarantees before any money is spent.** In order: the
active ``EmbeddingSpace`` agrees with the vector columns; the provider agrees
with the space; the disclosure gate permits this record's content to leave the
deployment; and there is actually something left to embed. A vendor call that
turns out to have been unnecessary is the cheapest bug to prevent and the
hardest to notice afterwards, because its output looks exactly like output
that was needed.

**What it deliberately does not do.** No retries, no circuit breaking, no rate
limiting — those compose *around* the port (IR-132) and an adapter or a
service that hides them cannot be tested for the failure it hides. No Celery,
no logging decisions: the tasks in ``apps/ai/tasks.py`` own that, and this
module is callable from a management command with no broker running, which is
what IR-282's backfill needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from django.core.exceptions import ImproperlyConfigured

from apps.ai.providers.ports import EmbeddingProvider


class EmbeddingRefused(Exception):
    """The disclosure policy will not let this record's content be sent.

    Not an error and not a failure: it is the gate doing its job (ADR-015
    §Security Impact). Raised rather than returned as a quiet zero so a
    backfill can count it and say which records were withheld — the callers
    here catch it and record it on the outcome.
    """


@dataclass(frozen=True)
class EmbeddingOutcome:
    """What one embedding run did, and what it declined to do.

    ``skipped`` is not a rounding error to be ignored: on a re-run it is the
    whole point, and a run reporting ``embedded=0, skipped=47`` is a healthy
    idempotent re-run while ``embedded=0, skipped=0`` means the record has no
    chunks and something upstream did not happen.
    """

    record_id: int
    space_id: Optional[int]
    embedded: int = 0
    skipped: int = 0
    refused: bool = False
    reason: str = ""

    #: True when only part of the document was sent, so the vectors were
    #: contextualized against the changed passages rather than the whole
    #: document. Carried on the outcome rather than left in a docstring
    #: because the resulting vectors are indistinguishable from fully
    #: contextualized ones, and a caller comparing retrieval quality across
    #: a re-chunk needs to know which it is looking at.
    partial_context: bool = False

    @property
    def spent_a_vendor_call(self) -> bool:
        return self.embedded > 0

    def as_dict(self) -> dict:
        """The shape a Celery task returns.

        Here rather than built by hand in each task: two tasks assembling
        the same six keys is two places to forget one, and a result dict
        missing ``refused`` reads as a success.
        """
        return {
            "record_id": self.record_id,
            "space_id": self.space_id,
            "embedded": self.embedded,
            "skipped": self.skipped,
            "refused": self.refused,
            "reason": self.reason,
            "partial_context": self.partial_context,
        }


def build_embedding_provider() -> EmbeddingProvider:
    """The adapter the indexing path uses.

    A function rather than a module-level instance so a test can monkeypatch
    one place, and so nothing is constructed at import time — ``VoyageEmbedding
    Provider`` reads settings in its constructor, and a module that builds one
    on import cannot be imported without them.

    There is exactly one adapter (ADR-015: Voyage, always), so there is no
    selection logic here to get wrong. The real composition root, where the
    resilience decorators are stacked, is IR-283's.
    """
    from apps.ai.providers.voyage import VoyageEmbeddingProvider

    return VoyageEmbeddingProvider()


def _checked_space(provider: EmbeddingProvider, space_id: Optional[int] = None):
    """The ``EmbeddingSpace`` to write into, having checked everything that
    can be checked for free.

    Three assertions, not one. ``assert_embedding_space_consistent`` compares
    the *active* space against the schema — what the vector columns can hold.
    The target space, when it is not the active one, is compared against the
    same columns. Then the space is compared against the *provider* — what the
    vendor is about to be asked to emit. They are different mistakes: the
    first two write a vector the column rejects, the third writes one it
    accepts and that means something else, which is the kind that returns
    plausible rankings forever.

    ``space_id`` names a space other than the active one, which is how
    IR-282's backfill fills a **pending** space before promoting it. A
    retired space is refused outright: writing new vectors into one is
    indexing into a space nothing will ever read.
    """
    from apps.ai.models import (
        VECTOR_COLUMN_DIMENSIONS,
        EmbeddingSpace,
        EmbeddingSpaceState,
        assert_embedding_space_consistent,
        get_active_embedding_space,
    )

    assert_embedding_space_consistent(VECTOR_COLUMN_DIMENSIONS, context="indexing")
    if space_id is None:
        space = get_active_embedding_space()
    else:
        space = EmbeddingSpace.objects.get(pk=space_id)
        if space.state == EmbeddingSpaceState.RETIRED:
            raise ImproperlyConfigured(
                f"EmbeddingSpace {space_id} is retired. Indexing into a space "
                f"no query path reads spends money for nothing."
            )
        if space.dimensions != VECTOR_COLUMN_DIMENSIONS:
            raise ImproperlyConfigured(
                f"EmbeddingSpace {space_id} is {space.dimensions} dimensions "
                f"but the vector columns hold {VECTOR_COLUMN_DIMENSIONS}."
            )
    if provider.dimensions != space.dimensions:
        raise ImproperlyConfigured(
            f"The embedding provider emits {provider.dimensions} dimensions "
            f"but space {space.pk} ({space.model_id!r}) is {space.dimensions}. "
            f"Refusing before the vendor call rather than after it."
        )
    return space


def _require_disclosure(record) -> None:
    """Refuse to send this record's content to a commercial vendor unless the
    policy allows it (ADR-015 §Security Impact).

    Embedding is an outbound call carrying the document's own words, so it
    sits behind the same gate as reranking and answer generation. **Today the
    gate refuses every record**, because ``Record`` carries no embargo field
    and an undetermined embargo is treated as an embargo — that is IR-250, and
    it is the correct failure direction for a gate whose purpose is to stop
    content leaving. Indexing a real corpus therefore waits on IR-250; nothing
    here works around it, because the way around a fail-closed gate is to add
    the missing fact, not to make the gate optional.
    """
    from apps.ai.policy import inputs_for_record, may_disclose

    decision = may_disclose(inputs_for_record(record))
    if not decision:
        raise EmbeddingRefused(decision.explain())


def embed_record_summary(
    record_id: int,
    *,
    provider: Optional[EmbeddingProvider] = None,
    skip_existing: bool = False,
) -> EmbeddingOutcome:
    """Embed a record's title and abstract into ``RecordEmbedding``.

    ``skip_existing`` is off by default and on for a backfill. The task path
    is queued *because* a record changed, so re-embedding is the point; a
    backfill walking thousands of records must not pay again for the ones a
    previous, interrupted run already did. The skip keys on the model id the
    existing row was written under, which is what ``RecordEmbedding`` records
    — so a record whose title or abstract changed under an unchanged model is
    *not* re-embedded by a backfill. Say so plainly rather than implying a
    freshness guarantee this table cannot give: re-indexing edited text is the
    task path's job, and a text-hash column that would let a backfill notice
    is schema IR-281 did not add.
    """
    from apps.ai.models import RecordEmbedding
    from apps.records.models import Record

    record = Record.objects.get(pk=record_id)
    provider = provider or build_embedding_provider()
    space = _checked_space(provider)

    if skip_existing and RecordEmbedding.objects.filter(
        record_id=record_id, model_name=space.model_id
    ).exists():
        return EmbeddingOutcome(record_id=record_id, space_id=space.id, skipped=1)

    try:
        _require_disclosure(record)
    except EmbeddingRefused as exc:
        return EmbeddingOutcome(
            record_id=record_id, space_id=space.id, refused=True, reason=str(exc)
        )

    text = f"{record.title}. {record.abstract}"
    vector = provider.embed_documents([text])[0]
    RecordEmbedding.objects.update_or_create(
        record=record,
        defaults={"embedding": vector, "model_name": space.model_id},
    )
    return EmbeddingOutcome(record_id=record_id, space_id=space.id, embedded=1)


def active_chunks(record_id: int):
    """A record's retrievable chunks: the active set, tombstones excluded.

    **The one definition of that phrase.** It was written out four times
    across the indexing, planning and promotion code, and four copies of a
    predicate is how a chunk ends up counted as owing by one of them and
    finished by another — which, in a run that costs money per chunk, is a
    bill and a half-indexed space rather than a wrong number.

    Sequence order, because that is reading order, and reading order is what
    makes a contextualized embedding contextual — the model sees the chunks
    as a document, not as a bag.
    """
    from apps.ai.models.chunk import DocumentChunk

    return DocumentChunk.objects.filter(
        record_id=record_id,
        chunk_set__is_active=True,
        deleted_at__isnull=True,
    ).order_by("sequence")


def pending_chunks(record_id: int, space_id: int, *, force: bool = False) -> list:
    """The active chunks that have no vector in ``space_id`` yet.

    A chunk whose text survived a re-chunk already carries its vector across
    (``DjangoChunkRepository._carry_vectors_over``), so "already has a row" is
    exactly the unchanged-text skip, with no second definition of unchanged to
    drift from the first.
    """
    chunks = active_chunks(record_id)
    if not force:
        chunks = chunks.exclude(embeddings__space_id=space_id)
    return list(chunks)


def embed_active_chunk_set(
    record_id: int,
    *,
    provider: Optional[EmbeddingProvider] = None,
    force: bool = False,
    space_id: Optional[int] = None,
) -> EmbeddingOutcome:
    """Embed the chunks of ``record_id``'s active chunk set that lack a vector.

    The chunks go to the provider **as one document**, which is the whole
    reason ``embed_document_chunks`` exists: ``voyage-context-4`` embeds a
    chunk with its siblings in view, so "this reduced error by 12%" keeps
    hold of what "this" was.

    One honest limit. When only some chunks are pending — an incremental
    re-chunk — only those are sent, so their context is the changed passages
    rather than the whole document. Re-sending every chunk to restore full
    context would mean paying for every chunk, which is the cost the
    incremental path exists to avoid. ``force=True`` is how a caller chooses
    the other trade.
    """
    from apps.ai.models.chunk import ChunkEmbedding
    from apps.records.models import Record

    provider = provider or build_embedding_provider()
    space = _checked_space(provider, space_id)

    chunks = pending_chunks(record_id, space.id, force=force)
    total = active_chunks(record_id).count()
    if not chunks:
        # Nothing to pay for, so nothing to check a gate about and no reason
        # to load the record.
        return EmbeddingOutcome(record_id=record_id, space_id=space.id, skipped=total)

    try:
        _require_disclosure(Record.objects.get(pk=record_id))
    except EmbeddingRefused as exc:
        return EmbeddingOutcome(
            record_id=record_id, space_id=space.id, refused=True, reason=str(exc)
        )

    vectors = provider.embed_document_chunks([chunk_texts(chunks)])[0]
    if len(vectors) != len(chunks):
        raise ValueError(
            f"The provider returned {len(vectors)} vectors for {len(chunks)} "
            f"chunks of record {record_id}. Vectors are matched positionally."
        )

    ChunkEmbedding.objects.bulk_create(
        (
            ChunkEmbedding(chunk=chunk, space=space, embedding=vector)
            for chunk, vector in zip(chunks, vectors)
        ),
        # A second worker that embedded the same chunk while this one was
        # waiting on the vendor has written an identical vector under the
        # same (chunk, space) key. Losing the race is not an error.
        ignore_conflicts=True,
    )
    return EmbeddingOutcome(
        record_id=record_id,
        space_id=space.id,
        embedded=len(chunks),
        skipped=max(total - len(chunks), 0),
        partial_context=len(chunks) < total,
    )


def estimate_pending_tokens(record_id: int, space_id: int) -> int:
    """A conservative token estimate for what embedding this record would cost.

    Shared with IR-282's pre-flight so the number an operator is shown and the
    number the run actually sends are derived from one place. It uses the same
    estimator the batching rule does, for the same reason: a ceiling wants an
    upper bound, not an exact count.
    """
    from apps.ai.providers.batching import estimate_tokens

    return sum(
        estimate_tokens(chunk.text) for chunk in pending_chunks(record_id, space_id)
    )


def chunk_texts(chunks: Sequence) -> list[str]:
    """What a caller sends to the vendor for ``chunks``, in order.

    One line, but it names the decision — a vector comes from ``text``, never
    ``content`` — in a place a caller can reuse instead of rediscovering.
    ``text`` is exactly what a vector was computed from and never changes;
    ``content`` is what a citation shows a reader, and embedding that would
    let the vector drift from the passage it indexes.
    """
    return [chunk.text for chunk in chunks]
