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

from celery import shared_task
from django.utils import timezone


def _build_extractor():
    """The seam. Tests replace this function rather than patching a client
    into the middle of the task."""
    from django.conf import settings

    from apps.ai.extraction import DoclingExtractor

    return DoclingExtractor(
        settings.DOCLING_API_URL,
        timeout=settings.DOCLING_TIMEOUT_SECONDS,
    )


_EXTRACTION_RESULT_FIELDS = [
    "extracted_text",
    "structure",
    "content_hash",
    "extractor",
    "error",
    "status",
    "completed_at",
]


def _run_extraction(self, extraction, *, file_field) -> None:
    """Shared body of ``extract_pdf_text``/``extract_manuscript_text``
    (IR-195): both differ only in which file field they read and how they
    looked up ``extraction`` -- the Docling call, status lifecycle and
    retry policy are identical either way.

    ``self`` is the bound Celery task (for ``self.request.id``/``self.retry``);
    passed through rather than looked up, since a plain function has neither.
    """
    from apps.ai.extraction import document_to_json, extraction_hash, flatten_for_search

    extraction.status         = "running"
    extraction.celery_task_id = self.request.id
    extraction.save(update_fields=["status", "celery_task_id"])

    try:
        with file_field.open("rb") as f:
            pdf_bytes = f.read()

        extracted = _build_extractor().extract(
            pdf_bytes, filename=os.path.basename(file_field.name)
        )

        extraction.extracted_text = flatten_for_search(extracted.document)
        extraction.structure      = document_to_json(extracted.document)
        extraction.content_hash   = extraction_hash(extracted.document)
        extraction.extractor      = extracted.extractor
        extraction.error          = ""
        extraction.status         = "done"
        extraction.completed_at   = timezone.now()
        extraction.save(update_fields=_EXTRACTION_RESULT_FIELDS)

    except Exception as exc:
        extraction.status = "failed"
        extraction.error  = str(exc)
        extraction.save(update_fields=["status", "error"])
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def extract_pdf_text(self, upload_id: int):
    """Background task: extract a supplementary upload's PDF and persist the
    result.

    Triggered by ``SubmitDocumentView`` immediately after the file is saved,
    so the API response is never blocked on a conversion that can take
    minutes on a scanned thesis. Retries three times, sixty seconds apart.

    Deliberately does not queue chunking (IR-195, ADR-013's 2026-09-08
    amendment): every ``UploadSlot`` a real record uses is supplementary --
    an Ethics Clearance form, a Patent Draft, and so on -- never the
    manuscript, so nothing extracted here belongs in the RAG corpus. See
    ``extract_manuscript_text`` below for the path that does chunk.
    """
    from apps.documents.models import PdfExtraction, RecordUpload

    extraction = PdfExtraction.objects.filter(upload_id=upload_id).first()
    if not extraction:
        return  # record deleted before the task ran

    upload = RecordUpload.objects.get(pk=upload_id)
    _run_extraction(self, extraction, file_field=upload.file)


@shared_task(bind=True, max_retries=3)
def extract_manuscript_text(self, record_id: int):
    """Background task: extract a record's manuscript and persist the result.

    The manuscript-side counterpart to ``extract_pdf_text`` above: same
    Docling call, same status lifecycle, but reading ``Record.abstract_file``
    and writing a ``PdfExtraction`` keyed by ``record`` rather than
    ``upload`` -- the manuscript has no ``UploadSlot`` to hang one off.
    Queued by ``RecordViewSet.perform_update`` whenever a PATCH changes
    ``abstract_file`` (IR-195).

    Unlike ``extract_pdf_text``, a successful run here does queue chunking
    (``chunk_manuscript``): the manuscript is the one document ADR-013's
    2026-09-08 amendment says belongs in the RAG corpus. That distinction is
    still drawn by *which task ran*, not by an inspectable field on the
    document itself -- sound today only because ``abstract_file`` structurally
    can never hold a supplementary document and no ``UploadSlot`` is seeded as
    "Manuscript". If a manuscript ``UploadSlot`` is ever introduced (the
    alternative IR-195 considered and did not take), this exclusion needs a
    real document-type marker instead of relying on which endpoint was hit.
    """
    from apps.documents.models import PdfExtraction
    from apps.records.models import Record

    extraction = PdfExtraction.objects.filter(record_id=record_id).first()
    if not extraction:
        return  # record deleted, or its manuscript removed, before the task ran

    record = Record.objects.get(pk=record_id)
    _run_extraction(self, extraction, file_field=record.abstract_file)

    # Reachable only on success -- _run_extraction's handler always raises.
    _queue_manuscript_chunking(record_id)


def _queue_manuscript_chunking(record_id: int) -> None:
    """Hand the extracted manuscript to the chunker, in another worker.

    ``on_commit`` rather than a bare ``delay``, for the same reason IR-116's
    original ``_queue_chunking`` used it: the chunker reads the row this task
    just wrote, and a worker that picked the message up inside an open
    transaction would find the pre-save extraction.
    """
    from django.db import transaction

    from apps.ai.tasks import chunk_manuscript

    transaction.on_commit(lambda: chunk_manuscript.delay(record_id))
