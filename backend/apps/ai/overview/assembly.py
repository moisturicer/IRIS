"""Every chunk of a record's active ChunkSet, in document order (IR-431)."""

from __future__ import annotations

from apps.ai.models import ChunkSet
from apps.ai.regions import normalized_regions
from apps.ai.retrieval.ports import RetrievedChunk


def whole_paper(chunk_set: ChunkSet) -> tuple[RetrievedChunk, ...]:
    """The chunk set as numbered sources for `build_prompt`, nothing ranked."""
    record = chunk_set.record
    chunks = chunk_set.chunks.filter(deleted_at__isnull=True).order_by("sequence")
    return tuple(
        RetrievedChunk(
            chunk_id=chunk.pk,
            record_id=record.pk,
            record_title=record.title,
            content=chunk.content,
            context_path=tuple(chunk.context_path or ()),
            source_page=chunk.source_page,
            score=0.0,
            regions=normalized_regions(chunk.bboxes, chunk_set.page_sizes),
        )
        for chunk in chunks
    )
