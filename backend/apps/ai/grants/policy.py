"""The research-read policy's tables, as PostgreSQL enforces them (IR-718, ADR-049 §5).

Migration `ai/0035` creates one SELECT policy per table below. The
restricted runtime roles may SELECT them and nothing else in `public`.
"""

from __future__ import annotations

#: Record rows and every relation that carries their content, metadata,
#: vectors or provenance.
PROTECTED_TABLES = (
    "records_record",
    "records_recordowner",
    "records_author",
    "records_recordversion",
    "documents_pdfextraction",
    "ai_chunkset",
    "ai_documentchunk",
    "ai_chunkembedding",
    "ai_recordembedding",
    "ai_recordoverview",
    "ai_paperbrief",
)
