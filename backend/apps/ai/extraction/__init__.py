"""Structured extraction (IR-107, ADR-016).

The stage between an uploaded PDF and the chunker. It produces the
``NormalizedDocument`` that ``apps.ai.chunking`` consumes, and the flattened
string full-text search indexes — derived from that same document, so the two
cannot disagree.

Everything here except ``docling_client`` and ``selection`` is pure. The one module that does
I/O is the one named after the vendor, which is the shape the rest of the AI
work already uses.
"""

from .docling_client import DoclingExtractor
from .docling_mapping import normalized_document_from_docling
from .flattening import flatten_for_search
from .hashing import extraction_hash
from .memory import InMemoryExtractor
from .pages import page_report
from .ports import (
    DocumentRejected,
    EmptyExtraction,
    ExtractedDocument,
    ExtractionError,
    ExtractorUnavailable,
    Failure,
    FigureImage,
    Provenance,
    StructuredExtractor,
    Usage,
    classify,
)
from .selection import current_extractor, use_extractor, verify_extraction_configuration
from .serialization import document_from_json, document_to_json

__all__ = [
    # port
    "StructuredExtractor",
    "ExtractedDocument",
    "ExtractionError",
    "ExtractorUnavailable",
    "EmptyExtraction",
    "DocumentRejected",
    "Failure",
    "classify",
    "Provenance",
    "Usage",
    "FigureImage",
    # selection
    "current_extractor",
    "use_extractor",
    "verify_extraction_configuration",
    # adapters
    "DoclingExtractor",
    "InMemoryExtractor",
    "normalized_document_from_docling",
    # persistence and derivation
    "document_to_json",
    "document_from_json",
    "flatten_for_search",
    "extraction_hash",
    "page_report",
]
