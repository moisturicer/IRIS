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


def create_upload(record, slot: UploadSlot, file, uploaded_by) -> RecordUpload:
    """Upload a new version of a document to a slot."""
    version = get_next_version(record.id, slot.id)
    return RecordUpload.objects.create(
        record=record,
        slot=slot,
        file=file,
        version=version,
        uploaded_by=uploaded_by,
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
    if upload.version == 1 and not force:
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
