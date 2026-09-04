"""Chunk-level RAG: the chunker domain.

The chunk, not the record, is the unit of retrieval (ADR-013). This package
turns a normalized document into a ``ChunkSet``.

It is **pure**: no Django, no database, no network, no clock, no randomness,
and no vendor import. That is deliberate and load-bearing — it makes the most
novel part of the RAG work the part that needs the least infrastructure to
develop, and it means the entire component is testable with a fixture and an
assertion.

Chunking runs in the Celery worker at ingestion, off the request path.
"""

from .document import (
    CAPTION,
    HEADING,
    LIST_ITEM,
    PARAGRAPH,
    TABLE_HEADER,
    TABLE_ROW,
    BoundingBox,
    DocumentElement,
    NormalizedDocument,
)
from .hashing import chunk_text_hash, chunkset_hash
from .ports import Chunker, ChunkingError, UnknownChunkingStrategy
from .registry import build_chunker, register_chunker, registered_strategies
from .tokens import count_tokens
from .values import DEFAULT_STRATEGY, Chunk, ChunkingOptions, ChunkSet

# Importing the strategies registers them.
from . import strategies  # noqa: E402,F401  (import for side effect)

__all__ = [
    # document
    "NormalizedDocument",
    "DocumentElement",
    "BoundingBox",
    "HEADING",
    "PARAGRAPH",
    "TABLE_ROW",
    "TABLE_HEADER",
    "LIST_ITEM",
    "CAPTION",
    # values
    "Chunk",
    "ChunkSet",
    "ChunkingOptions",
    "DEFAULT_STRATEGY",
    # port and registry
    "Chunker",
    "ChunkingError",
    "UnknownChunkingStrategy",
    "build_chunker",
    "register_chunker",
    "registered_strategies",
    # helpers
    "chunkset_hash",
    "chunk_text_hash",
    "count_tokens",
]
