"""What an uploaded PDF must be, stated once (IR-408).

`SubmitDocumentView` (a supplementary file) and `RecordWriteSerializer`
(the manuscript, `Record.abstract_file`) both accept PDFs, and before IR-408
only the first checked them. Both now ask this module, so the two cannot
disagree about the type or the limit.
"""
from typing import Optional

MAX_PDF_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


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
    return None
