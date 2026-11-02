"""PDF extraction: Docling-serve in, structure out (IR-107, ADR-016).

What this module used to be is worth recording, because it explains the shape
it has now. It held a three-tier extractor chain — ``unstructured``, PyMuPDF,
Tesseract — tried in order, each catching ``ImportError`` and falling through
to the next. None of the three libraries was declared in any requirements
file, so on a clean install all three fell through and extraction raised. It
was scaffolding, and its own module docstring said so.

It is replaced by one call to the Docling-serve container that both Compose
files have declared all along. **There is no fallback extractor.** ADR-016
retained PyMuPDF for Docling-serve unavailability; that clause is dropped —
see the divergence note in the ADR. A second extractor produces documents
without the structure this pipeline exists to consume, which means the
fallback path silently yields chunks with no regions and citations that
cannot be highlighted. Failing and retrying is the honest behaviour: the
Celery retry below is what covers a container that is briefly down.

The task stays thin on purpose. Reading bytes, persisting a row and moving a
status through its states is all it does; every judgement — reading order,
table shape, coordinate origin, what counts as a failure — lives in
``apps.ai.extraction``, where it is pure and tested without a container.
"""

import os
from typing import TYPE_CHECKING

from celery import shared_task
from django.utils import timezone

if TYPE_CHECKING:  # pragma: no cover - typing only
    from apps.documents.models import PdfExtraction


def _build_extractor():
    """The seam. Tests replace this function rather than patching a client
    into the middle of the task."""
    from django.conf import settings

    from apps.ai.extraction import DoclingExtractor

    return DoclingExtractor(
        settings.DOCLING_API_URL,
        timeout=settings.DOCLING_TIMEOUT_SECONDS,
        do_ocr=settings.DOCLING_DO_OCR,
        do_formula_enrichment=settings.DOCLING_DO_FORMULA_ENRICHMENT,
        do_code_enrichment=settings.DOCLING_DO_CODE_ENRICHMENT,
        do_picture_classification=settings.DOCLING_DO_PICTURE_CLASSIFICATION,
    )


def _locked_extraction(extraction_id):
    """Lock order matches upload: Record first, then its extraction row."""
    from apps.documents.models import PdfExtraction
    from apps.records.models import Record

    reference = PdfExtraction.objects.filter(pk=extraction_id).first()
    if not reference:
        return None
    record = Record.objects.select_for_update().filter(pk=reference.resolved_record_id).first()
    extraction = PdfExtraction.objects.select_for_update().filter(pk=extraction_id).first()
    if not record or record.is_deleted or not extraction:
        return None
    from .sources import current_source
    if extraction.record_id and not current_source(extraction, record):
        return None
    return extraction


def _run_extraction(self, extraction_id, source_revision):
    import uuid
    from django.db import transaction
    from apps.ai.extraction import document_to_json, extraction_hash, flatten_for_search

    attempt = uuid.uuid4()
    with transaction.atomic():
        extraction = _locked_extraction(extraction_id)
        if not extraction or str(extraction.source_revision) != str(source_revision):
            return
        if extraction.status in {"done", "failed"} or extraction.phase == "awaiting_submission":
            return
        extraction.status = "running"
        extraction.phase = "reading"
        extraction.attempt = attempt
        extraction.celery_task_id = self.request.id or ""
        extraction.save(update_fields=["status", "phase", "attempt", "celery_task_id"])
        field = extraction.upload.file if extraction.upload_id else extraction.record.abstract_file
        filename = extraction.source_file or field.name
        storage = field.storage

    try:
        with storage.open(filename, "rb") as source:
            pdf_bytes = source.read()
        extracted = _build_extractor().extract(pdf_bytes, filename=os.path.basename(filename))
        values = {
            "extracted_text": flatten_for_search(extracted.document),
            "structure": document_to_json(extracted.document),
            "content_hash": extraction_hash(extracted.document),
            "extractor": extracted.extractor, "error": "", "status": "done",
            "phase": "ready", "completed_at": timezone.now(),
        }
    except Exception:
        final = self.request.retries >= self.max_retries
        with transaction.atomic():
            extraction = _locked_extraction(extraction_id)
            if (not extraction or extraction.attempt != attempt
                    or str(extraction.source_revision) != str(source_revision)):
                return
            extraction.status = "failed" if final else "retrying"
            extraction.phase = "failed" if final else "retrying"
            extraction.error = "PDF reading failed. Retry extraction or enter details manually."
            extraction.save(update_fields=["status", "phase", "error"])
        # No parser exception/path in Celery messages or public status.
        safe_error = RuntimeError("PDF extraction failed")
        if final:
            raise safe_error from None
        raise self.retry(exc=safe_error, countdown=60) from None

    with transaction.atomic():
        extraction = _locked_extraction(extraction_id)
        if (not extraction or extraction.attempt != attempt
                or str(extraction.source_revision) != str(source_revision)):
            return
        for key, value in values.items():
            setattr(extraction, key, value)
        extraction.save(update_fields=list(values))
        _queue_chunking_if_manuscript(extraction)


@shared_task(bind=True, max_retries=3)
def extract_pdf_text(self, upload_id: int, source_revision=None):
    from apps.documents.models import PdfExtraction

    extraction = PdfExtraction.objects.filter(upload_id=upload_id).first()
    if extraction:
        _run_extraction(self, extraction.pk, source_revision)


@shared_task(bind=True, max_retries=3)
def extract_manuscript_text(self, record_id: int, source_revision=None):
    """Unpinned pre-upgrade messages cannot process a revisioned attachment."""
    from apps.documents.models import PdfExtraction

    extraction = PdfExtraction.objects.filter(record_id=record_id).first()
    if extraction:
        _run_extraction(self, extraction.pk, source_revision)


def _queue_chunking_if_manuscript(extraction: "PdfExtraction") -> None:
    from apps.documents.models import DocumentKind

    if extraction.kind == DocumentKind.MANUSCRIPT:
        _queue_chunk_extraction(extraction.pk, str(extraction.source_revision) if extraction.source_revision else None)


def _queue_chunk_extraction(extraction_id: int, source_revision=None) -> None:
    from django.db import transaction
    from apps.ai.tasks import chunk_extraction

    transaction.on_commit(lambda: chunk_extraction.delay(extraction_id, source_revision))
