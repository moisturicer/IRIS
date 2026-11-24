from io import BytesIO

from .models import RecordUpload, UploadSlot


def get_next_version(record_id: int, slot_id: int) -> int:
    """Return the next version number for a given record + slot combination."""
    latest = (
        RecordUpload.objects.filter(record_id=record_id, slot_id=slot_id)
        .order_by("-version")
        .first()
    )
    return (latest.version + 1) if latest else 1


def holds_upload(record, uploaded_by) -> bool:
    """
    Is an upload by `uploaded_by` to `record` held until they send it?
    (ADR-022 Amendment 8, IR-1322.) An owner's, on a submitted Record. A
    draft's uploads are sent at once, since the draft is its creator's alone,
    and anyone else's upload is sent at once, as before.
    """
    from apps.records.models import PipelineStatus, Record
    from core.permissions import is_record_owner

    # Read now, not from the caller's copy: a copy loaded before submission
    # would still say draft and send the file early.
    status = Record.objects.filter(pk=record.pk).values_list("pipeline_status", flat=True).first()
    return status not in (None, PipelineStatus.DRAFT) and is_record_owner(uploaded_by, record)


def create_upload(record, slot: UploadSlot, file, uploaded_by) -> RecordUpload:
    """Upload a new version of a document to a slot, held or sent (`holds_upload`)."""
    from django.utils import timezone

    version = get_next_version(record.id, slot.id)
    return RecordUpload.objects.create(
        record=record,
        slot=slot,
        file=file,
        version=version,
        uploaded_by=uploaded_by,
        sent_at=None if holds_upload(record, uploaded_by) else timezone.now(),
    )


def delete_upload(upload: RecordUpload, deleted_by, force: bool = False) -> None:
    """
    Delete a specific upload version.

    Rules:
    - Any authenticated user who is the record owner or staff may delete.
    - Version 1 uploads can only be deleted by staff (force=True) because
      removing the only version of a required slot could corrupt the record.
    - The physical file is removed from storage together with the DB row.

    Raises ValueError with a human-readable message on rule violations.
    """
    # Review history first, for everyone (ADR-058 §2, IR-872): `force` is an
    # office's override of the slot rule below, never of this one.
    from apps.records.versions import deletion_refused_reason

    refused = deletion_refused_reason(upload)
    if refused:
        raise ValueError(refused)

    # A held upload is the owner's to take back, whatever its number: no
    # Version names it and it answers nothing (ADR-022 Amendment 8, point 7).
    if upload.version == 1 and not force and not upload.held:
        raise ValueError(
            "The first version of an upload cannot be deleted without staff override. "
            "Upload a corrected version instead."
        )

    # Remove physical file from storage — best-effort, does not raise
    try:
        if upload.file:
            upload.file.delete(save=False)
    except Exception:
        pass

    upload.delete()


def build_zip_for_record(record) -> "BytesIO":
    """
    Build an in-memory ZIP archive of all RecordFile attachments for a record.
    Uses core.utils.build_zip under the hood.
    """
    from core.utils import build_zip
    files = list(record.files.all())
    return build_zip(files)
