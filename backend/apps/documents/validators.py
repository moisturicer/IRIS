"""What an uploaded PDF must be, stated once (IR-408).

`SubmitDocumentView` (a supplementary file) and `RecordWriteSerializer`
(the manuscript, `Record.abstract_file`) both accept PDFs, and before IR-408
only the first checked them. Both now ask this module, so the two cannot
disagree about the type or the limit.

The name and content type are the client's say-so, so the bytes decide (IR-665).
The parser only opens the file and counts its pages: no page content is read, so
a compressed stream is never expanded here.
"""
import logging
from typing import Optional

from pypdf import PdfReader

logger = logging.getLogger(__name__)

MAX_PDF_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB

#: How far into a file readers look for the signature.
PDF_SIGNATURE_WINDOW = 1024


def _is_readable_pdf(file) -> bool:
    """Whether `file` opens as a PDF with at least one page. Leaves it at the start."""
    try:
        file.seek(0)
        if b"%PDF-" not in file.read(PDF_SIGNATURE_WINDOW):
            return False
        file.seek(0)
        return len(PdfReader(file).pages) > 0
    # A parser reading hostile bytes fails in more ways than it documents, and
    # any of them means the same thing here: this file is refused, not a 500.
    except Exception as exc:  # noqa: BLE001
        logger.info("Refused an upload that does not open as a PDF: %s", type(exc).__name__)
        return False
    finally:
        file.seek(0)


def pdf_upload_problem(file) -> Optional[str]:
    """Why `file` is not an acceptable PDF upload, or None when it is."""
    name = (getattr(file, "name", "") or "").lower()
    content_type = getattr(file, "content_type", "") or ""
    if not name.endswith(".pdf") or "pdf" not in content_type:
        return "Only PDF files are accepted."
    if file.size > MAX_PDF_SIZE_BYTES:
        mb = file.size / (1024 * 1024)
        limit = MAX_PDF_SIZE_BYTES / (1024 * 1024)
        return f"File size {mb:.1f} MB exceeds the {limit:.0f} MB limit."
    if not _is_readable_pdf(file):
        return "This file is not a readable PDF."
    return None
