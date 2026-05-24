import re
from celery import shared_task
from django.utils import timezone


def _clean_text(raw: str) -> str:
    """
    Clean raw PDF text extracted by PyMuPDF.

    Steps:
    1. Split into lines and drop lines that look like headers/footers
       (page numbers, very short repeated lines, running titles).
    2. Strip special/control characters, keeping printable ASCII +
       common punctuation used in academic text.
    3. Collapse excessive whitespace.
    """
    lines = raw.splitlines()

    # --- Remove likely header / footer lines ----------------------------
    # Heuristic: lines shorter than 4 chars are usually page numbers or
    # decorative separators; drop them.
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if len(stripped) < 4:
            continue
        # Drop lines that are *only* digits (page numbers)
        if re.fullmatch(r"\d+", stripped):
            continue
        cleaned_lines.append(stripped)

    text = " ".join(cleaned_lines)

    # --- Remove non-printable / control characters ----------------------
    # Keep: letters, digits, whitespace, and common punctuation
    text = re.sub(r"[^\w\s.,;:!?()\-\'\"/]", " ", text)

    # --- Collapse whitespace --------------------------------------------
    text = re.sub(r"\s+", " ", text).strip()

    return text


@shared_task(bind=True, max_retries=3)
def extract_pdf_text(self, upload_id: int):
    """
    Background task: open the uploaded PDF with PyMuPDF, extract raw text
    from every page, clean it, and persist the result in PdfExtraction.

    Triggered by SubmitDocumentView immediately after saving the file so
    the API response is never blocked.
    """
    from apps.documents.models import RecordUpload, PdfExtraction

    extraction = PdfExtraction.objects.filter(upload_id=upload_id).first()
    if not extraction:
        return  # Record was deleted before task ran — nothing to do

    # Mark as running
    extraction.status         = "running"
    extraction.celery_task_id = self.request.id
    extraction.save(update_fields=["status", "celery_task_id"])

    try:
        import fitz  # PyMuPDF

        upload = RecordUpload.objects.get(pk=upload_id)

        # Open the PDF from Django's storage backend
        with upload.file.open("rb") as pdf_file:
            pdf_bytes = pdf_file.read()

        doc      = fitz.open(stream=pdf_bytes, filetype="pdf")
        raw_text = ""
        for page in doc:
            raw_text += page.get_text()
        doc.close()

        cleaned = _clean_text(raw_text)

        extraction.extracted_text = cleaned
        extraction.status         = "done"
        extraction.completed_at   = timezone.now()
        extraction.save(update_fields=["extracted_text", "status", "completed_at"])

    except Exception as exc:
        extraction.status = "failed"
        extraction.error  = str(exc)
        extraction.save(update_fields=["status", "error"])
        raise self.retry(exc=exc, countdown=60)
