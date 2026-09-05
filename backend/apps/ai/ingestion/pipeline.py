"""The ingestion pipeline: extraction in, active chunk set out (IR-116 H).

Stages 3, 4 and 6 of the six in ``docs/chunker_architecture.md`` §4 —
normalize, chunk, persist. Stage 5, embedding, is IR-108 and deliberately
absent: what a re-chunk leaves to embed is reported on the outcome rather
than spent here.

Every piece this joins was built and tested on its own in A through G; this
module is the first place they touch each other, and it is kept as thin as
that job allows. It makes exactly three decisions:

**Where the pure/impure line falls.** ``build_chunk_set`` is normalize-then-
chunk and nothing else — no database, no settings, no clock — so the five
thesis shapes are asserted against it directly. ``ingest_extraction`` is the
Django half: claim a key, persist, complete.

**That a duplicate returns before anything is spent.** The key is claimed
before the document is read, so a Celery retry storm on an already-indexed
extraction costs one indexed lookup.

**That a failure is recorded, not swallowed.** Any stage raising leaves the
job ``Failed`` carrying the message, and the exception propagates so the
task's retry still sees it. There is no partial chunk set to clean up: the
repository's swap is one transaction, so it either replaced the active set
or did nothing.

Two limitations, stated rather than left to be discovered.

**The idempotency key does not include ``ChunkingOptions``.** It is
``(record, extraction_hash, strategy_id, space)``, as the design specifies.
So changing ``max_tokens`` produces a different chunk set under the same key,
and a re-run would report itself a duplicate and skip. ``force=True`` is the
way past that, and it is what this ticket's manual token-ceiling comparison
uses.

**A chunk set is per record, but uploads are per slot.** The partial unique
index allows exactly one active chunk set per record, which assumes one
document per record; IRIS lets a record carry an upload in every slot, each
with its own extraction. Chunking whichever extraction finished last
therefore replaces the previous one's chunks — an ethical clearance form can
displace the thesis it belongs to. Nothing here works around that, because
the fix is to key a chunk set on the upload rather than the record, and that
is a schema decision ADR-013 has not taken. Until it does, ingestion is
sound only for records whose substantive document is the one being uploaded.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from apps.ai.chunking import (
    DEFAULT_STRATEGY,
    ChunkingOptions,
    ChunkSet,
    build_context_path_chunker,
    normalize,
)
from apps.ai.chunking.document import NormalizedDocument

if TYPE_CHECKING:  # pragma: no cover - typing only
    from apps.ai.repositories import ChunkRepository


class IngestionError(Exception):
    """Ingestion cannot proceed for this extraction.

    Distinct from a chunking bug or a database failure: it means the input
    is not there — an extraction that failed, or one predating the structured
    extractor. Retrying does not help, and the task does not.
    """


@dataclass(frozen=True)
class IngestionOutcome:
    """What one ingestion run did.

    ``duplicate`` and ``unchanged`` both mean nothing was written, and they
    are separate because they are different findings: ``duplicate`` is the
    key saying this exact work already completed, ``unchanged`` is the
    content hash saying the document chunks to what is already active. The
    first costs one lookup; the second costs a chunking run.
    """

    record_id: int
    chunk_set_id: object | None
    chunk_count: int
    duplicate: bool
    unchanged: bool
    to_embed: int = 0
    reused: int = 0
    soft_deleted: int = 0

    @property
    def wrote_anything(self) -> bool:
        return not (self.duplicate or self.unchanged)


def default_chunking_options() -> ChunkingOptions:
    """The options every ingestion run uses unless a caller overrides them.

    Read from settings rather than hardcoded, because IR-116's exit criterion
    is a person reading real chunks and *then* choosing the ceiling — which
    makes the chosen value a deployment decision, not a code change.
    """
    from django.conf import settings

    return ChunkingOptions(
        # Blank means the domain's default rather than a second copy of the
        # id in settings, which could drift from the registry unnoticed.
        strategy=settings.AI_CHUNK_STRATEGY or DEFAULT_STRATEGY,
        max_tokens=settings.AI_CHUNK_MAX_TOKENS,
        min_tokens=settings.AI_CHUNK_MIN_TOKENS,
        context_path_max_tokens=settings.AI_CHUNK_CONTEXT_PATH_MAX_TOKENS,
        exclude_sections=tuple(settings.AI_CHUNK_EXCLUDE_SECTIONS),
    )


def build_chunk_set(
    document: NormalizedDocument, options: ChunkingOptions
) -> ChunkSet:
    """Normalize ``document`` and chunk it, with the context path applied.

    Pure and deterministic, like both halves it composes. ``build_context_
    path_chunker`` rather than ``build_chunker``: a chunk embedded without
    its heading trail is the failure the decorator exists to prevent, and
    this is the one place in the codebase that builds the chunker for real
    ingestion.
    """
    return build_context_path_chunker(options).chunk(
        normalize(document, options), options
    )


def _record_failure(extraction, error: Exception) -> Exception:
    """Write ``error`` onto the extraction row and return it, for raising.

    IR-116 asks that "a failure at any stage records the failure against the
    extraction". An ``IngestionJob`` carries the failure too, but only once
    one exists — the two checks above run before a job can be keyed, and
    without this a record would go unindexed with no durable trace anywhere.

    ``status`` is deliberately untouched: extraction succeeded, and
    overwriting its verdict with a chunking failure would make a document
    that has perfectly good text look unextracted. A re-extraction clears the
    field, which is the right lifetime for this message.
    """
    extraction.error = f"chunking: {error}"
    extraction.save(update_fields=["error"])
    return error


def ingest_extraction(
    extraction,
    *,
    repository: "ChunkRepository",
    options: Optional[ChunkingOptions] = None,
    force: bool = False,
) -> IngestionOutcome:
    """Chunk ``extraction`` and make the result the record's active chunk set.

    ``extraction`` is a ``documents.PdfExtraction``; it is not imported or
    type-annotated as one because ``apps.ai`` has no other reason to depend
    on ``apps.documents`` and the dependency only ever runs the other way.
    """
    from apps.ai.ingestion.jobs import claim_ingestion_job, complete_ingestion_job
    from apps.ai.ingestion.lifecycle import IngestionState
    from apps.ai.models import get_active_embedding_space

    options = options or default_chunking_options()
    record_id = extraction.upload.record_id

    document = extraction.as_normalized_document()
    if document is None:
        raise _record_failure(
            extraction,
            IngestionError(
                f"Extraction {extraction.pk} has no stored structure to chunk "
                f"(status={extraction.status!r}). Extraction must succeed first."
            ),
        )
    if not extraction.content_hash:
        raise _record_failure(
            extraction,
            IngestionError(
                f"Extraction {extraction.pk} has no content hash, so an "
                f"ingestion job cannot be keyed and a re-run could not be "
                f"recognised."
            ),
        )

    space = get_active_embedding_space()
    claim = claim_ingestion_job(
        record_id=record_id,
        extraction_hash=extraction.content_hash,
        strategy_id=options.strategy,
        space_id=space.id,
    )
    if claim.is_duplicate and not force:
        active = repository.get_active(record_id)
        return IngestionOutcome(
            record_id=record_id,
            chunk_set_id=active.id if active else None,
            chunk_count=active.chunk_count if active else 0,
            duplicate=True,
            unchanged=True,
        )

    job = claim.job
    try:
        chunk_set = build_chunk_set(document, options)
        outcome = repository.rechunk(
            record_id=record_id,
            extraction_hash=extraction.content_hash,
            chunk_set=chunk_set,
        )
        complete_ingestion_job(job, content_hash=chunk_set.content_hash)
    except Exception as exc:
        job.transition_to(IngestionState.FAILED, error=str(exc))
        job.save(update_fields=["state", "error", "updated_at"])
        _record_failure(extraction, exc)
        raise

    return IngestionOutcome(
        record_id=record_id,
        chunk_set_id=outcome.chunk_set.id,
        chunk_count=outcome.chunk_set.chunk_count,
        duplicate=False,
        unchanged=outcome.unchanged,
        to_embed=outcome.to_embed_count,
        reused=outcome.reused,
        soft_deleted=outcome.soft_deleted,
    )
