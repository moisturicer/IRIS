"""PDF extraction: a PDF in, structure out (IR-107, ADR-056).

What this module used to be is worth recording, because it explains the shape
it has now. It held a three-tier extractor chain — ``unstructured``, PyMuPDF,
Tesseract — tried in order, each catching ``ImportError`` and falling through
to the next. None of the three libraries was declared in any requirements
file, so on a clean install all three fell through and extraction raised. It
was scaffolding, and its own module docstring said so.

It is replaced by one call to the Extractor ``apps.ai.extraction`` chooses
(IR-838); this task never names a vendor. **There is no fallback extractor.**
A second extractor produces documents
without the structure this pipeline exists to consume, which means the
fallback path silently yields chunks with no regions and citations that
cannot be highlighted. Failing and retrying is the honest behaviour: the
Celery retry below is what covers a vendor that is briefly down.

Only a transient failure retries (IR-839): an unavailable Extractor, after 1,
3 and 9 minutes. Anything else, an unexpected exception included, fails once.

The task stays thin on purpose. Reading bytes, persisting a row and moving a
status through its states is all it does; every judgement — reading order,
table shape, coordinate origin, what counts as a failure — lives in
``apps.ai.extraction``, where it is pure and tested without a vendor.
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
    from .figures import replace_figures
    from . import formulas
    from .models import DocumentKind
    from .pdf_evidence import sandbox

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
        manuscript = extraction.kind == DocumentKind.MANUSCRIPT

    try:
        with storage.open(filename, "rb") as source:
            pdf_bytes = source.read()
        with reading(record_id):
            extracted = current_extractor().extract(pdf_bytes, filename=os.path.basename(filename))
        # Local and after the vendor read; a bad PDF stores its error, never fails (IR-1053).
        evidence = sandbox.read_pdf_evidence(pdf_bytes) if manuscript else {}
        # Each located Formula, cropped from this PDF; never its OCR text (IR-1102).
        cropped = formulas.crop(pdf_bytes, extracted.document) if manuscript else []
        values = {
            "extracted_text": flatten_for_search(extracted.document),
            "structure": document_to_json(extracted.document),
            "content_hash": extraction_hash(extracted.document),
            "extractor": extracted.provenance.name,
            "extractor_version": extracted.provenance.version,
            "extractor_options": dict(extracted.provenance.options),
            "warnings": [{"kind": "page_failed", "page": page} for page in extracted.failed_pages],
            "raw_result": dict(extracted.raw),
            "pdf_evidence": evidence,
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
        replace_figures(extraction, extracted.figures)
        formulas.replace_formulas(extraction, cropped)
        _queue_chunking_if_manuscript(extraction)
        _queue_metadata_if_llamaparse(extraction)


class ExtractionTask(Task):
    """Every dispatch, retries included, carries the current Extractor's time limit."""

    def apply_async(self, args=None, kwargs=None, **options):
        from apps.ai.extraction import current_extractor

        from django.conf import settings

        # The evidence read and the formula crops run inside the same attempt
        # (IR-1053, IR-1102), each under the evidence wall limit.
        evidence = 2 * (settings.PDF_EVIDENCE_WALL_SECONDS or 0)
        limit = int(current_extractor().timeout_seconds + evidence) + TIME_LIMIT_MARGIN_SECONDS
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
        pinned = str(extraction.source_revision) if extraction.source_revision else None
        _queue_chunk_extraction(extraction.pk, pinned)
        if extraction.figures.exists():
            from django.db import transaction
            from apps.ai.tasks import describe_extraction_figures

            transaction.on_commit(lambda: describe_extraction_figures.delay(extraction.pk, pinned))
        if extraction.formulas.exists():
            from django.db import transaction
            from apps.ai.tasks import transcribe_extraction_formulas

            transaction.on_commit(lambda: transcribe_extraction_formulas.delay(extraction.pk, pinned))


def _queue_chunk_extraction(extraction_id: int, source_revision=None) -> None:
    from django.db import transaction
    from apps.ai.tasks import chunk_extraction

    transaction.on_commit(lambda: chunk_extraction.delay(extraction_id, source_revision))


def _queue_metadata_if_llamaparse(extraction: "PdfExtraction") -> None:
    """Publish's LlamaExtract reading of this parse (IR-846, ADR-056 §15).

    Only a Manuscript LlamaParse read, and only when LlamaExtract is set up;
    otherwise Publish reads the shaped document instead. Under the caller's
    lock, so the row and the source revision it names are the current ones.
    """
    from django.db import transaction
    from apps.ai.extraction.llamaparse_client import EXTRACTOR_NAME
    from apps.ai.extraction.selection import metadata_reader_configured
    from apps.documents.models import DocumentKind, ManuscriptMetadata

    if (extraction.kind != DocumentKind.MANUSCRIPT or extraction.extractor != EXTRACTOR_NAME
            or extraction.source_revision is None or not metadata_reader_configured()):
        return
    reading, _ = ManuscriptMetadata.objects.update_or_create(
        extraction=extraction, source_revision=extraction.source_revision,
        defaults={"status": ManuscriptMetadata.QUEUED, "attempt": None, "result": {},
                  "credits": None, "completed_at": None},
    )
    transaction.on_commit(lambda: read_manuscript_metadata.delay(reading.pk))


def _locked_metadata(reading_id):
    """The reading and its extraction, locked, while both still name the
    Record's current Manuscript; ``None`` once anything has moved on."""
    from apps.documents.models import ManuscriptMetadata

    reading = ManuscriptMetadata.objects.filter(pk=reading_id).first()
    if not reading:
        return None
    extraction = _locked_extraction(reading.extraction_id)
    if not extraction or str(extraction.source_revision) != str(reading.source_revision):
        return None
    if str(extraction.record.manuscript_revision) != str(reading.source_revision):
        return None
    return ManuscriptMetadata.objects.select_for_update().filter(pk=reading_id).first()


def _run_metadata(reading_id) -> None:
    import uuid
    from django.db import transaction
    from apps.ai.extraction.gate import NotDisclosed, reading as sending_for
    from apps.ai.extraction.selection import current_metadata_reader
    from apps.documents.models import ManuscriptMetadata

    attempt = uuid.uuid4()
    with transaction.atomic():
        row = _locked_metadata(reading_id)
        if not row or row.status != ManuscriptMetadata.QUEUED:
            return
        extraction = row.extraction
        parse_job_id = ((extraction.raw_result or {}).get("job") or {}).get("id")
        if not parse_job_id:
            row.status = ManuscriptMetadata.FAILED
            row.save(update_fields=["status"])
            return
        row.status = ManuscriptMetadata.RUNNING
        row.attempt = attempt
        row.started_at = timezone.now()
        row.save(update_fields=["status", "attempt", "started_at"])
        record_id, pages = extraction.record_id, extraction.pages_read

    try:
        with sending_for(record_id):
            result = current_metadata_reader().read(parse_job_id, pages=pages)
        values = {"status": ManuscriptMetadata.DONE, "result": result.as_json(), "credits": result.credits}
    except NotDisclosed:
        values = {"status": ManuscriptMetadata.REFUSED}
    except Exception:
        # Not retried: Publish falls back to the shaped document at once
        # rather than keep the author waiting on a second vendor attempt.
        logger.warning("LlamaExtract reading %s failed; Publish falls back", reading_id, exc_info=True)
        values = {"status": ManuscriptMetadata.FAILED}

    with transaction.atomic():
        row = _locked_metadata(reading_id)
        if not row or row.attempt != attempt:
            return
        for key, value in {**values, "completed_at": timezone.now()}.items():
            setattr(row, key, value)
        row.save(update_fields=[*values, "completed_at"])


class MetadataTask(Task):
    """Carries the LlamaExtract reader's own time limit."""

    def apply_async(self, args=None, kwargs=None, **options):
        from django.conf import settings

        limit = settings.LLAMAEXTRACT_TIMEOUT_SECONDS + TIME_LIMIT_MARGIN_SECONDS
        options.setdefault("time_limit", limit)
        options.setdefault("soft_time_limit", limit - SOFT_LIMIT_HEADROOM_SECONDS)
        return super().apply_async(args, kwargs, **options)


@shared_task(base=MetadataTask)
def read_manuscript_metadata(reading_id: int):
    _run_metadata(reading_id)
