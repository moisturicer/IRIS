"""Accepted source identity, shared by the current writer and its workers (ADR-053)."""
import uuid

from django.db import transaction

from .models import DocumentKind, PdfExtraction


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
    if same and not retry and (extraction.status != "queued" or extraction.phase != "awaiting_submission" or defer):
        return
    extraction, _ = PdfExtraction.objects.update_or_create(record=record, defaults={
        "source_revision": revision, "source_file": record.abstract_file.name,
        "kind": DocumentKind.MANUSCRIPT, "status": "queued",
        "phase": "awaiting_submission" if defer else "queued", "attempt": None,
        "extracted_text": "", "structure": {}, "content_hash": "", "extractor": "",
        "error": "", "completed_at": None, "celery_task_id": "",
    })
    if not defer:
        from apps.ai.models import ChunkSet
        ChunkSet.objects.filter(record=record, is_active=True).exclude(source_revision=revision).update(is_active=False)
        pinned = str(revision) if revision else None
        transaction.on_commit(lambda: extract_manuscript_text.delay(record.pk, pinned))


def current_source(extraction, record):
    """A legacy source may finish only while the legacy attachment is still current."""
    return (
        not record.is_deleted and bool(record.abstract_file)
        and record.manuscript_revision == extraction.source_revision
        and (not extraction.source_file or record.abstract_file.name == extraction.source_file)
    )


