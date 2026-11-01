"""Tables under the research-read policy (IR-718, ADR-049 §5).

`ai/0035` puts one SELECT policy on each.
"""

from __future__ import annotations

#: Records and their content, metadata, vectors and provenance.
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
