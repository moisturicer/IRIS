"""ChunkRepository: two implementations of one contract (IR-89 F).

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
deliberately the seam, not an incidental one.
"""

from dataclasses import dataclass
from typing import Any, Optional, Protocol

from django.db import transaction

from apps.ai.chunking import (
    Chunk,
    ChunkingOptions,
    ChunkSet,
    chunk_text_hash,
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


class ChunkRepository(Protocol):
    """Two methods, because that is all a chunk set's lifecycle needs so
    far: it is written whole, and the active one is read whole. Chunks are
    never inserted, updated or deleted individually — see ``ChunkSet``'s
    docstring for why."""

    def save(
        self, *, record_id: int, extraction_hash: str, chunk_set: ChunkSet
    ) -> PersistedChunkSet:
        """Persist ``chunk_set`` as the active chunk set for ``record_id``.

        Replaces any existing chunk set for the record — incremental
        re-chunking (diffing per-chunk hashes to avoid re-embedding
        unchanged chunks) is IR-115's job, not this one's.
        """

    def get_active(self, record_id: int) -> Optional[PersistedChunkSet]:
        """The active chunk set for ``record_id``, or ``None`` if there is
        no chunk set for that record."""


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
    """A dict keyed by record id. Fine as a real implementation: a chunk set
    is a value, so "replace what's there" is the entire persistence model,
    same as the Django one — it just skips the database."""

    def __init__(self) -> None:
        self._by_record: dict[int, PersistedChunkSet] = {}
        self._next_id = 1

    def save(
        self, *, record_id: int, extraction_hash: str, chunk_set: ChunkSet
    ) -> PersistedChunkSet:
        persisted = PersistedChunkSet(
            id=self._next_id,
            record_id=record_id,
            extraction_hash=extraction_hash,
            chunk_set=chunk_set,
        )
        self._next_id += 1
        self._by_record[record_id] = persisted
        return persisted

    def get_active(self, record_id: int) -> Optional[PersistedChunkSet]:
        return self._by_record.get(record_id)


class DjangoChunkRepository:
    """The production implementation: one chunk set and its chunks written
    per record, inside one transaction, with any previous chunk set for
    that record deleted first (cascading to its chunks and their
    embeddings) — the same "replace, don't diff" model as the in-memory
    one, at the schema level rather than in a dict.

    This is a deliberate departure from the chunker architecture doc's
    section 9, which keeps a superseded chunk set around and flips
    ``is_active`` instead of deleting it — that history is what lets a
    later re-chunk diff per-chunk ``text_hash`` values and re-embed only
    what changed. Retaining it now, with nothing yet reading it, would be
    exactly the unread-field problem this codebase already calls out
    elsewhere (see ``Chunk.element_kinds`` in the chunking package). IR-115
    ("G", incremental re-chunking and idempotency) is where that history
    starts being read, and is the right place to revisit whether ``save``
    should stop deleting the old chunk set outright.
    """

    def save(
        self, *, record_id: int, extraction_hash: str, chunk_set: ChunkSet
    ) -> PersistedChunkSet:
        from apps.ai.models.chunk import ChunkSet as ChunkSetModel
        from apps.ai.models.chunk import DocumentChunk as DocumentChunkModel

        with transaction.atomic():
            ChunkSetModel.objects.filter(record_id=record_id).delete()

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
            DocumentChunkModel.objects.bulk_create(
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

        return PersistedChunkSet(
            id=db_chunk_set.id,
            record_id=record_id,
            extraction_hash=extraction_hash,
            chunk_set=chunk_set,
        )

    def get_active(self, record_id: int) -> Optional[PersistedChunkSet]:
        from apps.ai.models.chunk import ChunkSet as ChunkSetModel
        from apps.ai.models.chunk import DocumentChunk as DocumentChunkModel

        db_chunk_set = ChunkSetModel.objects.filter(
            record_id=record_id, is_active=True
        ).first()
        if db_chunk_set is None:
            return None

        rows = DocumentChunkModel.objects.filter(chunk_set=db_chunk_set).order_by(
            "sequence"
        )
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
            record_id=record_id,
            extraction_hash=db_chunk_set.extraction_hash,
            chunk_set=chunk_set,
        )
