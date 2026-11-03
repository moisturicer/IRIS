"""PDF extraction: Docling-serve in, structure out (IR-107, ADR-016).

What this module used to be is worth recording, because it explains the shape
it has now. It held a three-tier extractor chain — ``unstructured``, PyMuPDF,
Tesseract — tried in order, each catching ``ImportError`` and falling through
to the next. None of the three libraries was declared in any requirements
file, so on a clean install all three fell through and extraction raised. It
was scaffolding, and its own module docstring said so.

It is replaced by one call to the Extractor ``apps.ai.extraction`` chooses
(IR-838); this task never names a vendor. **There is no fallback extractor.** ADR-016
retained PyMuPDF for Docling-serve unavailability; that clause is dropped —
see the divergence note in the ADR. A second extractor produces documents
without the structure this pipeline exists to consume, which means the
fallback path silently yields chunks with no regions and citations that
cannot be highlighted. Failing and retrying is the honest behaviour: the
Celery retry below is what covers a container that is briefly down.

Only a transient failure retries (IR-839): an unavailable Extractor, after 1,
3 and 9 minutes. Anything else, an unexpected exception included, fails once.

The task stays thin on purpose. Reading bytes, persisting a row and moving a
status through its states is all it does; every judgement — reading order,
table shape, coordinate origin, what counts as a failure — lives in
``apps.ai.extraction``, where it is pure and tested without a container.
"""

import logging
import os
from typing import TYPE_CHECKING

from celery import Task, shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.utils import timezone
from .phases import ExtractionPhase

logger = logging.getLogger(__name__)

PERMANENT_MESSAGE = "This PDF can't be read automatically. Enter the details manually."
TRANSIENT_MESSAGE = "Reading is temporarily unavailable. Try again later."
RETRY_COUNTDOWNS = (60, 180, 540)
TIME_LIMIT_MARGIN_SECONDS = 60
# The soft limit fires first so an overrun attempt can still record itself.
SOFT_LIMIT_HEADROOM_SECONDS = 30

if TYPE_CHECKING:  # pragma: no cover - typing only
    from apps.documents.models import PdfExtraction

#: Rows a stale message must not start reading.
_HELD = frozenset({ExtractionPhase.AWAITING_SUBMISSION, ExtractionPhase.AWAITING_DISCLOSURE})


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
    from apps.ai.admission.errors import AdmissionDenied
    from apps.ai.extraction import (
        ExtractionError, Failure, classify, current_extractor,
        document_to_json, extraction_hash, flatten_for_search,
    )
    from apps.ai.extraction.gate import NotDisclosed, reading

    attempt = uuid.uuid4()
    with transaction.atomic():
        extraction = _locked_extraction(extraction_id)
        if not extraction or str(extraction.source_revision) != str(source_revision):
            return
        if extraction.status in {"done", "failed"} or extraction.phase in _HELD:
            return
        extraction.status = "running"
        extraction.phase = ExtractionPhase.READING
        extraction.attempt = attempt
        extraction.celery_task_id = self.request.id or ""
        extraction.save(update_fields=["status", "phase", "attempt", "celery_task_id"])
        field = extraction.upload.file if extraction.upload_id else extraction.record.abstract_file
        filename = extraction.source_file or field.name
        storage = field.storage
        record_id = extraction.resolved_record_id

    try:
        with storage.open(filename, "rb") as source:
            pdf_bytes = source.read()
        with reading(record_id):
            extracted = current_extractor().extract(pdf_bytes, filename=os.path.basename(filename))
        values = {
            "extracted_text": flatten_for_search(extracted.document),
            "structure": document_to_json(extracted.document),
            "content_hash": extraction_hash(extracted.document),
            "extractor": extracted.provenance.name,
            "extractor_version": extracted.provenance.version,
            "extractor_options": dict(extracted.provenance.options),
            "warnings": [{"kind": "page_failed", "page": page} for page in extracted.failed_pages],
            "raw_result": dict(extracted.raw),
            "pages_read": extracted.usage.pages if extracted.usage else None,
            "credits": extracted.usage.credits if extracted.usage else None,
            "error": "", "status": "done",
            "phase": ExtractionPhase.READY, "completed_at": timezone.now(),
        }
    except NotDisclosed:
        # Nothing was sent. Held, then rechecked under the lock in case a
        # release committed since (IR-850).
        from .sources import HELD, read_awaiting

        with transaction.atomic():
            extraction = _locked_extraction(extraction_id)
            if (not extraction or extraction.attempt != attempt
                    or str(extraction.source_revision) != str(source_revision)):
                return
            for key, value in HELD.items():
                setattr(extraction, key, value)
            extraction.save(update_fields=list(HELD))
            read_awaiting(record_id)
        return
    except Exception as error:
        # A refused admission says nothing about the PDF: retried (IR-850).
        transient = (isinstance(error, (SoftTimeLimitExceeded, AdmissionDenied))
                     or classify(error) is Failure.TRANSIENT)
        if not transient and not isinstance(error, ExtractionError):
            logger.exception("Unexpected failure extracting PdfExtraction %s", extraction_id)
        final = not transient or self.request.retries >= len(RETRY_COUNTDOWNS)
        with transaction.atomic():
            extraction = _locked_extraction(extraction_id)
            if (not extraction or extraction.attempt != attempt
                    or str(extraction.source_revision) != str(source_revision)):
                return
            extraction.status = "failed" if final else "retrying"
            extraction.phase = ExtractionPhase.FAILED if final else ExtractionPhase.RETRYING
            if not final:
                extraction.error = ""
            else:
                extraction.error = TRANSIENT_MESSAGE if transient else PERMANENT_MESSAGE
            extraction.save(update_fields=["status", "phase", "error"])
        # No parser exception/path in Celery messages or public status.
        safe_error = RuntimeError("PDF extraction failed")
        if final:
            raise safe_error from None
        raise self.retry(exc=safe_error, countdown=RETRY_COUNTDOWNS[self.request.retries]) from None

    with transaction.atomic():
        extraction = _locked_extraction(extraction_id)
        if (not extraction or extraction.attempt != attempt
                or str(extraction.source_revision) != str(source_revision)):
            return
        for key, value in values.items():
            setattr(extraction, key, value)
        extraction.save(update_fields=list(values))
        _queue_chunking_if_manuscript(extraction)


class ExtractionTask(Task):
    """Every dispatch, retries included, carries the current Extractor's time limit."""

    def apply_async(self, args=None, kwargs=None, **options):
        from apps.ai.extraction import current_extractor

        limit = current_extractor().timeout_seconds + TIME_LIMIT_MARGIN_SECONDS
        options.setdefault("time_limit", limit)
        options.setdefault("soft_time_limit", limit - SOFT_LIMIT_HEADROOM_SECONDS)
        return super().apply_async(args, kwargs, **options)


@shared_task(bind=True, base=ExtractionTask, max_retries=len(RETRY_COUNTDOWNS))
def extract_pdf_text(self, upload_id: int, source_revision=None):
    from apps.documents.models import PdfExtraction

    extraction = PdfExtraction.objects.filter(upload_id=upload_id).first()
    if extraction:
        _run_extraction(self, extraction.pk, source_revision)


@shared_task(bind=True, base=ExtractionTask, max_retries=len(RETRY_COUNTDOWNS))
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
