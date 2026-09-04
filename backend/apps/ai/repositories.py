"""ChunkRepository: two implementations of one contract (IR-89 F, IR-115 G).

``InMemoryChunkRepository`` is a real implementation, not a mock — it makes
retrieval logic testable without standing up Postgres, and everything that
builds on top of a repository (starting with IR-108's query path) can be
developed and tested against it. ``DjangoChunkRepository`` is what actually
runs in production. The contract suite in
``apps/ai/tests/test_chunk_repository_contract.py`` runs identically
against both; if they diverge, one of them is wrong.

This module is the only place ``apps.ai.chunking``'s pure value objects
(``Chunk``, ``ChunkSet``, ``ChunkingOptions``) meet Django. The chunking
package itself stays pure — no Django import, no I/O — so this is
deliberately the seam, not an incidental one. The *decision* a re-chunk
turns on lives there too, in ``chunking.diff``; what is here is only the
persistence of that decision.
"""

from dataclasses import dataclass
from typing import Any, Optional, Protocol

from django.db import transaction
from django.utils import timezone

from apps.ai.chunking import (
    Chunk,
    ChunkingOptions,
    ChunkSet,
    chunk_text_hash,
    diff_chunk_sets,
)
from apps.ai.chunking.document import BoundingBox


@dataclass(frozen=True)
class PersistedChunkSet:
    """A chunk set as returned by a repository: the pure domain value plus
    the identifiers a repository is responsible for, which ``ChunkSet``
    itself has no reason to carry."""

    id: object  # an int for DjangoChunkRepository; opaque otherwise
    record_id: int
    extraction_hash: str
    chunk_set: ChunkSet

    @property
    def chunk_count(self) -> int:
        """How many chunks it holds, without the caller walking
        ``.chunk_set.chunks`` — a chain that reads as a typo."""
        return len(self.chunk_set.chunks)


@dataclass(frozen=True)
class RechunkOutcome:
    """What a re-chunk did, and — the part callers act on — what it left to
    pay for.

    ``to_embed`` is the caller's work order: the chunks whose text did not
    exist in the superseded set. ``reused`` counts the rest, whose vectors a
    repository that stores vectors will have carried across. A caller that
    embeds ``chunk_set`` wholesale instead of ``to_embed`` is spending the
    token budget for nothing, which is the mistake this type exists to make
    visible.

    These counts are the *diff*, not an inventory of the vector table: a
    previous set that was chunked but never embedded leaves reused chunks
    with no vector to carry. The embedding stage is where that is caught,
    because "has a vector" is a question about a specific embedding space
    and a repository is not scoped to one.
    """

    chunk_set: PersistedChunkSet
    unchanged: bool
    to_embed: tuple[Chunk, ...]
    reused: int
    soft_deleted: int

    @property
    def to_embed_count(self) -> int:
        """How many chunks the caller has left to embed — a work order,
        not a tally of work done."""
        return len(self.to_embed)


class ChunkRepository(Protocol):
    """Three methods: a chunk set is written whole, the active one is read
    whole, and a re-chunk swaps it. Chunks are never inserted, updated or
    deleted individually — see ``ChunkSet``'s docstring for why."""

    def rechunk(
        self, *, record_id: int, extraction_hash: str, chunk_set: ChunkSet
    ) -> RechunkOutcome:
        """Make ``chunk_set`` the active chunk set for ``record_id``.

        A no-op when the incoming content hash matches the active one: zero
        writes, and nothing for the caller to embed. Otherwise the previous
        set is deactivated and the new one inserted in a single transaction,
        so a concurrent reader observes exactly one active set throughout.
        """

    def save(
        self, *, record_id: int, extraction_hash: str, chunk_set: ChunkSet
    ) -> PersistedChunkSet:
        """``rechunk`` without the cost report, for callers that only want
        the chunk set persisted."""

    def get_active(self, record_id: int) -> Optional[PersistedChunkSet]:
        """The active chunk set for ``record_id``, or ``None`` if there is
        no chunk set for that record."""


def _unchanged_outcome(previous: PersistedChunkSet) -> RechunkOutcome:
    """The outcome of a re-chunk that turned out to be a re-run.

    Shared by both repositories rather than written out twice, because the
    zero-writes claim is the one behaviour the contract suite most needs to
    be identical on either side of the seam.
    """
    return RechunkOutcome(
        chunk_set=previous,
        unchanged=True,
        to_embed=(),
        reused=len(previous.chunk_set.chunks),
        soft_deleted=0,
    )


def _serialize_options(options: ChunkingOptions) -> dict:
    return {
        "strategy": options.strategy,
        "max_tokens": options.max_tokens,
        "min_tokens": options.min_tokens,
        "overlap_tokens": options.overlap_tokens,
        "context_path_max_tokens": options.context_path_max_tokens,
        "merge_short_siblings": options.merge_short_siblings,
        "repeat_table_header": options.repeat_table_header,
        "exclude_sections": list(options.exclude_sections),
    }


def _deserialize_options(data: dict) -> ChunkingOptions:
    return ChunkingOptions(
        strategy=data["strategy"],
        max_tokens=data["max_tokens"],
        min_tokens=data.get("min_tokens"),
        overlap_tokens=data.get("overlap_tokens", 0),
        context_path_max_tokens=data.get("context_path_max_tokens", 48),
        merge_short_siblings=data.get("merge_short_siblings", True),
        repeat_table_header=data.get("repeat_table_header", True),
        exclude_sections=tuple(data.get("exclude_sections", ())),
    )


def serialize_regions(bboxes: tuple[BoundingBox, ...]) -> list[dict[str, Any]]:
    """Regions as stored JSON.

    A degenerate rect — zero-area, or inverted by a bad scan — is kept
    rather than dropped, because it still says which page the passage came
    from, and carries ``degenerate: true`` so the citation overlay skips
    drawing it. Dropping it would lose the page; drawing it would paint an
    invisible, unclickable box and tell the reader nothing.
    """
    rows: list[dict[str, Any]] = []
    for b in bboxes:
        row = {
            "page": b.page,
            "left": b.left,
            "top": b.top,
            "right": b.right,
            "bottom": b.bottom,
        }
        if b.is_degenerate:
            row["degenerate"] = True
        rows.append(row)
    return rows


def deserialize_regions(rows: list[dict[str, Any]]) -> tuple[BoundingBox, ...]:
    """The inverse. ``degenerate`` is derived from the rect itself, so it is
    dropped on the way in rather than stored on the value object — two
    sources for one fact is how they come to disagree. Rows written before
    the flag existed simply do not carry the key."""
    return tuple(
        BoundingBox(
            page=row["page"],
            left=row["left"],
            top=row["top"],
            right=row["right"],
            bottom=row["bottom"],
        )
        for row in rows
    )


def _serialize_page_sizes(page_sizes) -> dict:
    # JSON object keys are strings — mirrors apps.ai.extraction.serialization.
    return {str(page): list(size) for page, size in page_sizes.items()}


def _deserialize_page_sizes(data: dict) -> dict:
    return {int(page): tuple(size) for page, size in data.items()}


class InMemoryChunkRepository:
    """A dict keyed by record id, holding the same swap semantics as the
    Django one: the previous set is superseded rather than forgotten, so the
    diff a re-chunk reports is the same on both sides of the contract.

    It carries no vectors, because nothing in memory embeds anything — the
    counts it reports are the plan, and the Django implementation is where
    that plan turns into rows.
    """

    def __init__(self) -> None:
        self._by_record: dict[int, PersistedChunkSet] = {}
        self._next_id = 1

    def rechunk(
        self, *, record_id: int, extraction_hash: str, chunk_set: ChunkSet
    ) -> RechunkOutcome:
        previous = self._by_record.get(record_id)
        diff = diff_chunk_sets(
            previous=previous.chunk_set if previous else None, incoming=chunk_set
        )
        if diff.unchanged:
            return _unchanged_outcome(previous)

        persisted = PersistedChunkSet(
            id=self._next_id,
            record_id=record_id,
            extraction_hash=extraction_hash,
            chunk_set=chunk_set,
        )
        self._next_id += 1
        self._by_record[record_id] = persisted
        return RechunkOutcome(
            chunk_set=persisted,
            unchanged=False,
            to_embed=diff.to_embed,
            reused=len(diff.reused),
            soft_deleted=len(diff.removed_hashes),
        )

    def save(
        self, *, record_id: int, extraction_hash: str, chunk_set: ChunkSet
    ) -> PersistedChunkSet:
        return self.rechunk(
            record_id=record_id, extraction_hash=extraction_hash, chunk_set=chunk_set
        ).chunk_set

    def get_active(self, record_id: int) -> Optional[PersistedChunkSet]:
        return self._by_record.get(record_id)


class DjangoChunkRepository:
    """The production implementation: an atomic swap, not a replace.

    A re-chunk deactivates the previous chunk set and inserts the new one
    inside one transaction. The order matters — the partial unique index
    ``one_active_chunk_set_per_record`` is checked per statement, so the
    deactivate has to land before the insert; and the transaction is what
    means a concurrent reader observes exactly one active set and never two
    or zero.

    The superseded set is **kept**. IR-89 F deleted it outright and its
    docstring said this ticket was where that would be revisited: keeping it
    is what makes ``text_hash`` a reusable vector rather than a column
    nothing reads. A chunk whose text survives into the new set has its
    vectors copied across; a chunk whose text does not is tombstoned with
    ``deleted_at`` rather than removed, so "this content left the corpus"
    stays answerable after the fact.
    """

    def rechunk(
        self, *, record_id: int, extraction_hash: str, chunk_set: ChunkSet
    ) -> RechunkOutcome:
        from apps.ai.models.chunk import ChunkEmbedding
        from apps.ai.models.chunk import ChunkSet as ChunkSetModel
        from apps.ai.models.chunk import DocumentChunk as DocumentChunkModel
        from apps.records.models import Record

        # This first read is deliberately outside the transaction opened
        # below: the no-op path must not write, and it must not take a row
        # lock either — an idempotent re-run of a 3,000-document backfill
        # would otherwise serialise on rows it never touches.
        previous_row, previous = self._load_active(record_id)
        if self._diff_against(previous, chunk_set).unchanged:
            return _unchanged_outcome(previous)

        with transaction.atomic():
            # Two workers re-chunking one record would otherwise both diff
            # against the same superseded set and both insert an active row,
            # and the loser would surface the partial unique index as an
            # IntegrityError. The record row is the lock because a first
            # chunking has no chunk set row to take one on. It is acquired
            # here rather than around the read above so the no-op path stays
            # lock-free, which is the whole point of that read.
            Record.objects.select_for_update().filter(pk=record_id).first()

            # Re-read under the lock: a swap that committed while this call
            # was diffing is now the set to supersede, and if it wrote the
            # same content this call is a no-op after all.
            previous_row, previous = self._load_active(record_id)
            diff = self._diff_against(previous, chunk_set)
            if diff.unchanged:
                return _unchanged_outcome(previous)

            if previous_row is not None:
                ChunkSetModel.objects.filter(pk=previous_row.pk).update(is_active=False)

            db_chunk_set = ChunkSetModel.objects.create(
                record_id=record_id,
                extraction_hash=extraction_hash,
                strategy_id=chunk_set.strategy_id,
                options=_serialize_options(chunk_set.options),
                content_hash=chunk_set.content_hash,
                page_sizes=_serialize_page_sizes(chunk_set.page_sizes),
                is_active=True,
            )

            max_sequence = len(chunk_set.chunks) - 1 if chunk_set.chunks else 0
            rows = DocumentChunkModel.objects.bulk_create(
                DocumentChunkModel(
                    chunk_set=db_chunk_set,
                    record_id=record_id,
                    sequence=chunk.sequence,
                    max_sequence=max_sequence,
                    text=chunk.text,
                    content=chunk.content,
                    context_path=list(chunk.context_path),
                    text_hash=chunk_text_hash(chunk),
                    token_count=chunk.token_count,
                    source_page=chunk.source_page,
                    element_kinds=sorted(chunk.element_kinds),
                    bboxes=serialize_regions(chunk.bboxes),
                )
                for chunk in chunk_set.chunks
            )

            self._carry_vectors_over(
                previous_row=previous_row, new_rows=rows, embedding_model=ChunkEmbedding
            )
            soft_deleted = self._tombstone_removed(
                previous_row=previous_row,
                removed_hashes=diff.removed_hashes,
                chunk_model=DocumentChunkModel,
            )

        persisted = PersistedChunkSet(
            id=db_chunk_set.id,
            record_id=record_id,
            extraction_hash=extraction_hash,
            chunk_set=chunk_set,
        )
        return RechunkOutcome(
            chunk_set=persisted,
            unchanged=False,
            to_embed=diff.to_embed,
            reused=len(diff.reused),
            soft_deleted=soft_deleted,
        )

    def save(
        self, *, record_id: int, extraction_hash: str, chunk_set: ChunkSet
    ) -> PersistedChunkSet:
        return self.rechunk(
            record_id=record_id, extraction_hash=extraction_hash, chunk_set=chunk_set
        ).chunk_set

    def get_active(self, record_id: int) -> Optional[PersistedChunkSet]:
        from apps.ai.models.chunk import ChunkSet as ChunkSetModel

        db_chunk_set = ChunkSetModel.objects.filter(
            record_id=record_id, is_active=True
        ).first()
        if db_chunk_set is None:
            return None
        return self._to_value(db_chunk_set)

    # -- internals -------------------------------------------------------

    @classmethod
    def _load_active(cls, record_id: int):
        """The active chunk set row and its value, or ``(None, None)``."""
        from apps.ai.models.chunk import ChunkSet as ChunkSetModel

        row = ChunkSetModel.objects.filter(record_id=record_id, is_active=True).first()
        return row, (cls._to_value(row) if row else None)

    @staticmethod
    def _diff_against(previous: Optional[PersistedChunkSet], incoming: ChunkSet):
        return diff_chunk_sets(
            previous=previous.chunk_set if previous else None, incoming=incoming
        )

    @staticmethod
    def _to_value(db_chunk_set) -> PersistedChunkSet:
        from apps.ai.models.chunk import DocumentChunk as DocumentChunkModel

        rows = DocumentChunkModel.objects.filter(
            chunk_set=db_chunk_set, deleted_at__isnull=True
        ).order_by("sequence")
        chunks = tuple(
            Chunk(
                text=row.text,
                content=row.content,
                context_path=tuple(row.context_path),
                sequence=row.sequence,
                token_count=row.token_count,
                source_page=row.source_page,
                element_kinds=frozenset(row.element_kinds),
                bboxes=deserialize_regions(row.bboxes),
            )
            for row in rows
        )
        chunk_set = ChunkSet(
            chunks=chunks,
            strategy_id=db_chunk_set.strategy_id,
            options=_deserialize_options(db_chunk_set.options),
            content_hash=db_chunk_set.content_hash,
            page_sizes=_deserialize_page_sizes(db_chunk_set.page_sizes),
        )
        return PersistedChunkSet(
            id=db_chunk_set.id,
            record_id=db_chunk_set.record_id,
            extraction_hash=db_chunk_set.extraction_hash,
            chunk_set=chunk_set,
        )

    @staticmethod
    def _carry_vectors_over(*, previous_row, new_rows, embedding_model) -> int:
        """Copy every vector whose text survived into the new chunk set.

        Copied rather than repointed: the superseded chunk keeps its own
        vector, so the old set stays a complete, self-consistent record of
        what was indexed rather than a half-stripped one.

        Returns the number of *chunks* given a carried-over vector, not the
        number of vectors — a chunk embedded under two spaces is one chunk
        the caller no longer has to pay for. That count is not what
        ``RechunkOutcome.reused`` reports: reuse is a fact about text, and
        the two differ whenever the superseded set was never embedded.
        """
        if previous_row is None:
            return 0

        old_vectors: dict[str, dict[int, list]] = {}
        for text_hash, space_id, vector in embedding_model.objects.filter(
            chunk__chunk_set=previous_row
        ).values_list("chunk__text_hash", "space_id", "embedding"):
            old_vectors.setdefault(text_hash, {}).setdefault(space_id, vector)

        carried_rows = []
        carried_chunks = 0
        for row in new_rows:
            by_space = old_vectors.get(row.text_hash)
            if not by_space:
                continue
            carried_chunks += 1
            carried_rows.extend(
                embedding_model(chunk=row, space_id=space_id, embedding=vector)
                for space_id, vector in by_space.items()
            )

        if carried_rows:
            embedding_model.objects.bulk_create(carried_rows)
        return carried_chunks

    @staticmethod
    def _tombstone_removed(*, previous_row, removed_hashes, chunk_model) -> int:
        """Soft-delete the superseded chunks whose text left the document.

        Only the ones that left: a chunk whose text carried over is still in
        the corpus under the new set, and tombstoning it would make
        ``deleted_at`` mean "superseded" instead of "gone", which is the
        distinction the column exists to record.
        """
        if previous_row is None or not removed_hashes:
            return 0
        return chunk_model.objects.filter(
            chunk_set=previous_row,
            text_hash__in=list(removed_hashes),
            deleted_at__isnull=True,
        ).update(deleted_at=timezone.now())
