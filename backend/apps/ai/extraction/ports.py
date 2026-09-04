"""The extraction port: PDF bytes in, a document the chunker can consume out.

One method, over an adapter that talks HTTP to a container. The port exists
so the rest of ingestion never learns that extraction is remote — the Celery
task reads bytes, calls ``extract``, and persists the result; whether that
took a millisecond in-process or ninety seconds of OCR in another container
is not its concern.

``ExtractedDocument`` deliberately does **not** carry the flattened text that
full-text search indexes. That string is derived from the structure by
``flatten_for_search`` at the call site, so no adapter can return a text that
disagrees with its own elements — the two were separate fields in the design
sketch, and separate fields are exactly how they drift.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from apps.ai.chunking.document import NormalizedDocument


class ExtractionError(Exception):
    """Extraction did not produce a usable document."""


class ExtractorUnavailable(ExtractionError):
    """The extractor could not be reached, or failed in a way that says
    nothing about the document — a connection refused, a timeout, a 5xx.

    Kept distinct from its parent because the two want different operational
    responses: a retry is likely to succeed here and unlikely to succeed on a
    document the extractor rejected. Both retry today (ADR-016 keeps the
    Celery retry either way); only this one is a reason to look at the
    container rather than at the PDF.
    """


class EmptyExtraction(ExtractionError):
    """The extractor succeeded and returned nothing to chunk.

    Treated as a failure rather than an empty success: an upload that
    silently indexes to zero chunks is invisible to search and looks
    identical to one that was never uploaded.
    """


@dataclass(frozen=True)
class ExtractedDocument:
    """What an extractor returns: the structured document, and its own name.

    ``extractor`` is stored on the extraction row so that "which extractor
    produced this?" is answerable from the data rather than from the date of
    the row and a memory of when the code changed.
    """

    document: NormalizedDocument
    extractor: str


@runtime_checkable
class StructuredExtractor(Protocol):
    """Turns PDF bytes into a structured document.

    Synchronous: it runs in a Celery worker, which has no event loop to
    block, and the one caller has nothing else to do while it waits.

    ``filename`` is passed because the extractor may use it — Docling-serve
    sniffs the content type from it — and because it is the last-resort
    document title when the PDF names itself nothing.

    Raises ``ExtractionError`` (or a subclass) rather than returning an empty
    document on failure.
    """

    def extract(self, pdf_bytes: bytes, *, filename: str) -> ExtractedDocument: ...
