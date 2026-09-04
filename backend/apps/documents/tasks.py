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


def _queue_chunking(upload_id: int) -> None:
    """Hand the extracted document to the chunker, in another worker (IR-116).

    A second seam, for the same reason as the one above: tests replace this
    rather than standing up a broker. Queued rather than called, because
    chunking is CPU work of its own and a failure to chunk must not mark a
    perfectly good extraction failed or send the document back through
    Docling.

    ``on_commit`` rather than a bare ``delay``: the chunker reads the row this
    task just wrote, and a worker that picked the message up inside an open
    transaction would find the pre-save extraction and fail on a document that
    is actually fine. Under autocommit -- how this task runs today -- the
    callback fires immediately, so this costs nothing and stops being correct
    only by accident later.
    """
    from django.db import transaction

    from apps.ai.tasks import chunk_record_document

    transaction.on_commit(lambda: chunk_record_document.delay(upload_id))


@shared_task(bind=True, max_retries=3)
def extract_pdf_text(self, upload_id: int):
    """Background task: extract an uploaded PDF and persist the result.

    Triggered by ``SubmitDocumentView`` immediately after the file is saved,
    so the API response is never blocked on a conversion that can take
    minutes on a scanned thesis. Retries three times, sixty seconds apart.
    """
    from apps.ai.extraction import document_to_json, extraction_hash, flatten_for_search
    from apps.documents.models import PdfExtraction, RecordUpload

    extraction = PdfExtraction.objects.filter(upload_id=upload_id).first()
    if not extraction:
        return  # record deleted before the task ran

    extraction.status         = "running"
    extraction.celery_task_id = self.request.id
    extraction.save(update_fields=["status", "celery_task_id"])

    try:
        upload = RecordUpload.objects.get(pk=upload_id)

        with upload.file.open("rb") as f:
            pdf_bytes = f.read()

        extracted = _build_extractor().extract(
            pdf_bytes, filename=os.path.basename(upload.file.name)
        )

        extraction.extracted_text = flatten_for_search(extracted.document)
        extraction.structure      = document_to_json(extracted.document)
        extraction.content_hash   = extraction_hash(extracted.document)
        extraction.extractor      = extracted.extractor
        extraction.error          = ""
        extraction.status         = "done"
        extraction.completed_at   = timezone.now()
        extraction.save(
            update_fields=[
                "extracted_text",
                "structure",
                "content_hash",
                "extractor",
                "error",
                "status",
                "completed_at",
            ]
        )

    except Exception as exc:
        extraction.status = "failed"
        extraction.error  = str(exc)
        extraction.save(update_fields=["status", "error"])
        raise self.retry(exc=exc, countdown=60)

    # Reachable only on success -- the handler above always raises.
    _queue_chunking(upload_id)
