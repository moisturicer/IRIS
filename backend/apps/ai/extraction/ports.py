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

import enum
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from apps.ai.chunking.document import NormalizedDocument


class ExtractionError(Exception):
    """Extraction did not produce a usable document."""


class ExtractorUnavailable(ExtractionError):
    """The extractor could not be reached, or failed in a way that says
    nothing about the document — a connection refused, a timeout, a 5xx.

    The one transient failure (IR-839): the only one the task retries.
    """


class DocumentRejected(ExtractionError):
    """The extractor read the document and refused it. Permanent (IR-839)."""


class EmptyExtraction(ExtractionError):
    """The extractor succeeded and returned nothing to chunk.

    Treated as a failure rather than an empty success: an upload that
    silently indexes to zero chunks is invisible to search and looks
    identical to one that was never uploaded.
    """


class IncompleteExtraction(ExtractionError):
    """The extractor reports partial coverage rather than a complete document."""


@dataclass(frozen=True)
class Provenance:
    """Which Extractor produced an Extraction, at which version, with which
    options (IR-838). Stored on the row, so the answer is in the data."""

    name: str
    version: str = ""
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Usage:
    """What the vendor billed for one read (IR-850). ``credits`` is ``None``
    when it was not reported, and admission then keeps the reservation."""

    pages: int
    credits: Optional[Decimal] = None


@dataclass(frozen=True)
class FigureImage:
    """A figure the Extractor cropped, downloaded before its copy is deleted
    (IR-841). ``bbox`` is the vendor's page-point box; IR-845 stores it."""

    page: int
    bbox: Mapping[str, float]
    media_type: str
    data: bytes
    caption: Optional[str] = None


@dataclass(frozen=True)
class ExtractedDocument:
    """What an extractor returns: the structured document and its provenance.

    ``failed_pages`` are pages the extractor could not read; the rest of the
    document is still used (IR-839). ``usage`` is what a billing Extractor
    reported; ``None`` when nothing was (IR-850). ``raw`` is the vendor's
    whole result, less expiring URLs, so shaping can re-run without a paid
    re-read (IR-841).
    """

    document: NormalizedDocument
    provenance: Provenance
    failed_pages: tuple[int, ...] = ()
    usage: Optional[Usage] = None
    figures: tuple[FigureImage, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict)


class Failure(enum.Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"


def classify(error: BaseException) -> Failure:
    """Only an unavailable extractor is worth retrying; anything else,
    an unexpected exception included, fails once (IR-839)."""
    return Failure.TRANSIENT if isinstance(error, ExtractorUnavailable) else Failure.PERMANENT


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

    ``timeout_seconds`` is the longest one call may take; the task's time
    limit is derived from it (IR-839).

    ``leaves_campus`` is true when the PDF is sent off the deployment; such an
    Extractor is gated and admitted, and also names the ``account`` it spends
    (``admission.ledger.account_for``) and the ``model`` it is recorded under
    (IR-850).
    """

    timeout_seconds: float
    leaves_campus: bool

    def extract(self, pdf_bytes: bytes, *, filename: str) -> ExtractedDocument: ...
