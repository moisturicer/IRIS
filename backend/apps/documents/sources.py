"""Accepted source identity, shared by the current writer and its workers (IR-830)."""
import uuid

from django.db import transaction
from django.db.models import Q

from .models import DocumentKind, PdfExtraction, RecordUpload
from .phases import ExtractionPhase
from apps.ai.extraction.gate import awaits_disclosure

NOT_READ = "Not read: awaiting consent or release. Enter details manually."
#: A read the disclosure gate holds back (IR-850).
HELD = {"status": "queued", "phase": ExtractionPhase.AWAITING_DISCLOSURE, "error": NOT_READ}


def manuscript_changes(instance, file):
    """Fields committed with accepted bytes. None means an idempotent re-upload."""
    if not file:
        return {"manuscript_revision": None, "manuscript_sha256": "", "manuscript_filename": ""}
    digest = file.source_sha256  # only the shared validator may attest these bytes
    if instance and instance.abstract_file and instance.manuscript_sha256 == digest:
        return None
    return {"manuscript_revision": uuid.uuid4(), "manuscript_sha256": digest,
            "manuscript_filename": file.name[:255]}


def reset_manuscript(record, *, defer=False, retry=False):
    """Under the Record lock: invalidate all current output, then queue after commit."""
    from .tasks import extract_manuscript_text

    extraction = PdfExtraction.objects.filter(record=record).first()
    revision = record.manuscript_revision
    if not record.abstract_file:
        if extraction:
            extraction.delete()
        from apps.ai.models import ChunkSet
        ChunkSet.objects.filter(record=record, is_active=True).update(is_active=False)
        return
    same = extraction and extraction.source_revision == revision and extraction.source_file == record.abstract_file.name
    if same and not retry and (extraction.status != "queued" or extraction.phase != ExtractionPhase.AWAITING_SUBMISSION or defer):
        return
    held = not defer and awaits_disclosure(record)
    extraction, _ = PdfExtraction.objects.update_or_create(record=record, defaults={
        "source_revision": revision, "source_file": record.abstract_file.name,
        "kind": DocumentKind.MANUSCRIPT, "status": "queued",
        "phase": ExtractionPhase.AWAITING_SUBMISSION if defer else ExtractionPhase.QUEUED, "attempt": None,
        "extracted_text": "", "structure": {}, "content_hash": "", "extractor": "",
        "pdf_evidence": {},
        "error": "", "warnings": [], "completed_at": None, "celery_task_id": "",
        **(HELD if held else {}),
    })
    if not defer:
        from apps.ai.models import ChunkSet
        from .figures import remove_superseded
        ChunkSet.objects.filter(record=record, is_active=True).exclude(source_revision=revision).update(is_active=False)
        remove_superseded(extraction)
    if not defer and not held:
        pinned = str(revision) if revision else None
        transaction.on_commit(lambda: extract_manuscript_text.delay(record.pk, pinned))


def queue_upload_read(upload) -> PdfExtraction:
    """Track a supplementary upload's read; queue it unless the gate holds it (IR-850)."""
    from apps.records.models import Record
    from .tasks import extract_pdf_text

    # Gate under the Record lock, so a release cannot slip past this row.
    record = Record.objects.select_for_update().get(pk=upload.record_id)
    held = awaits_disclosure(record)
    extraction = PdfExtraction.objects.create(
        upload=upload, kind=DocumentKind.SUPPLEMENTARY, **(HELD if held else {}),
    )
    if not held:
        transaction.on_commit(lambda: extract_pdf_text.delay(upload.id))
    return extraction


def read_awaiting(record_id) -> None:
    """Queue every read the gate held back, if it now allows them (IR-850).
    Locks the Record first, as upload and the task do."""
    from apps.records.models import Record
    from .tasks import extract_pdf_text

    with transaction.atomic():
        record = Record.objects.select_for_update().filter(pk=record_id, is_deleted=False).first()
        if record is None:
            return
        uploads = RecordUpload.objects.filter(record=record).values("pk")
        held = list(PdfExtraction.objects.select_for_update().filter(
            Q(record=record) | Q(upload_id__in=uploads), phase=ExtractionPhase.AWAITING_DISCLOSURE,
        ))
        if not held or awaits_disclosure(record):
            return
        for extraction in held:
            if extraction.record_id:
                reset_manuscript(record, retry=True)
                continue
            extraction.phase = ExtractionPhase.QUEUED
            extraction.error = ""
            extraction.save(update_fields=["phase", "error"])
            transaction.on_commit(lambda upload_id=extraction.upload_id: extract_pdf_text.delay(upload_id))


def current_source(extraction, record):
    """A legacy source may finish only while the legacy attachment is still current."""
    return (
        not record.is_deleted and bool(record.abstract_file)
        and record.manuscript_revision == extraction.source_revision
        and (not extraction.source_file or record.abstract_file.name == extraction.source_file)
    )
