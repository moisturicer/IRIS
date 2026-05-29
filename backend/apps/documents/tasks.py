"""
PDF text extraction task.

TODO (AI engineer — FR-M3-01 architecture change):
  Replace the three-tier extractor chain below with a single Docling-serve API call.

  Target architecture:
    1. Read PDF bytes from storage.
    2. POST bytes to Docling-serve: POST <settings.DOCLING_API_URL>/convert
       - Docling handles text-layer PDFs, complex layouts, and OCR internally.
       - Returns extracted text as Markdown.
    3. Apply _clean_text() to the response.
    4. Store in PdfExtraction.extracted_text.

  Required settings:
    DOCLING_API_URL = "http://<docling-host>:<port>"  (add to settings/base.py)

  Required packages:
    requests (already available via django-storages transitive dep, verify)

  Remove when done:
    - _run_extraction_chain(), _extract_with_opendataloader(),
      _extract_with_pymupdf(), _extract_with_tesseract()
    - requirements: unstructured[pdf], pymupdf, pytesseract, Pillow

  The _clean_text() helper below is still needed — keep it.
"""
import io
import re
from celery import shared_task
from django.utils import timezone


# ---------------------------------------------------------------------------
# Text cleaning helper
# ---------------------------------------------------------------------------

def _clean_text(raw: str) -> str:
    """
    Normalise raw extracted text for storage and FTS indexing.

    Steps:
      1. Drop lines shorter than 3 chars (page numbers, decorators).
      2. Drop lines that are purely digits (page-number lines).
      3. Strip non-printable / control characters.
      4. Collapse excessive whitespace.
    """
    lines = raw.splitlines()
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if len(stripped) < 3:
            continue
        if re.fullmatch(r"\d+", stripped):
            continue
        cleaned_lines.append(stripped)

    text = " ".join(cleaned_lines)
    text = re.sub(r"[^\w\s.,;:!?()\-\'\"/]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Extractor implementations
# ---------------------------------------------------------------------------

def _extract_with_opendataloader(pdf_bytes: bytes) -> str:
    """
    Primary extractor: unstructured library (OpenDataLoader).

    Install: pip install "unstructured[pdf]"

    unstructured.partition.auto.partition() detects the document type and
    applies the best available strategy (pdfminer → OCR as its own fallback).
    This aligns with the SRS requirement for OpenDataLoader as the primary
    extraction method.
    """
    from unstructured.partition.auto import partition  # type: ignore[import]

    elements = partition(
        file=io.BytesIO(pdf_bytes),
        content_type="application/pdf",
        strategy="fast",       # avoids spawning heavyweight OCR on the task worker
    )
    return "\n".join(str(e) for e in elements if str(e).strip())


def _extract_with_pymupdf(pdf_bytes: bytes) -> str:
    """
    Fallback extractor: PyMuPDF (fitz).

    Install: pip install pymupdf
    """
    import fitz  # type: ignore[import]

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    raw = ""
    for page in doc:
        raw += page.get_text()
    doc.close()
    return raw


def _extract_with_tesseract(pdf_bytes: bytes) -> str:
    """
    Tertiary extractor: Tesseract OCR via pytesseract.

    Uses PyMuPDF to render each PDF page to a bitmap at 2× zoom, then runs
    Tesseract on each rendered image.  This covers fully image-based / scanned
    PDFs that text-based extractors cannot handle.

    Requires:
      pip install pytesseract pillow pymupdf
      System: tesseract-ocr ≥ 4 must be on PATH.
    """
    import fitz          # type: ignore[import]
    import pytesseract   # type: ignore[import]
    from PIL import Image  # type: ignore[import]

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_texts: list[str] = []
    zoom_matrix = fitz.Matrix(2, 2)   # 2× for reasonable OCR resolution

    for page in doc:
        pix = page.get_pixmap(matrix=zoom_matrix, alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        page_texts.append(pytesseract.image_to_string(img))

    doc.close()
    return "\n".join(page_texts)


# ---------------------------------------------------------------------------
# Extraction chain
# ---------------------------------------------------------------------------

_EXTRACTORS = [
    ("opendataloader", _extract_with_opendataloader),
    ("pymupdf",        _extract_with_pymupdf),
    ("tesseract",      _extract_with_tesseract),
]


def _run_extraction_chain(pdf_bytes: bytes) -> tuple[str, str]:
    """
    Try each extractor in priority order.

    Returns (raw_text, method_name) for the first extractor that yields
    non-empty text.  Raises RuntimeError if all extractors fail or are
    unavailable.
    """
    errors: list[str] = []

    for name, fn in _EXTRACTORS:
        try:
            raw = fn(pdf_bytes)
            if raw and raw.strip():
                return raw, name
            # Extractor ran but returned empty — try next
            errors.append(f"{name}: returned empty text")
        except ImportError:
            errors.append(f"{name}: library not installed")
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    raise RuntimeError(
        "All PDF extractors failed or produced empty text. "
        "Details: " + " | ".join(errors)
    )


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=3)
def extract_pdf_text(self, upload_id: int):
    """
    Background task: extract text from an uploaded PDF and persist the result.

    Triggered by SubmitDocumentView immediately after saving the file so the
    API response is never blocked.  Retries up to 3 times (60-second delay)
    on extraction failure.
    """
    from apps.documents.models import RecordUpload, PdfExtraction

    extraction = PdfExtraction.objects.filter(upload_id=upload_id).first()
    if not extraction:
        return  # record deleted before task ran

    extraction.status         = "running"
    extraction.celery_task_id = self.request.id
    extraction.save(update_fields=["status", "celery_task_id"])

    try:
        upload = RecordUpload.objects.get(pk=upload_id)

        with upload.file.open("rb") as f:
            pdf_bytes = f.read()

        raw_text, method = _run_extraction_chain(pdf_bytes)
        cleaned = _clean_text(raw_text)

        extraction.extracted_text = cleaned
        extraction.status         = "done"
        extraction.completed_at   = timezone.now()
        # Store which extractor succeeded so it's observable in the admin
        extraction.save(update_fields=["extracted_text", "status", "completed_at"])

    except Exception as exc:
        extraction.status = "failed"
        extraction.error  = str(exc)
        extraction.save(update_fields=["status", "error"])
        raise self.retry(exc=exc, countdown=60)
