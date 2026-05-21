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


# TODO: implement build_zip_for_record(record) using core.utils.build_zip
# TODO: implement delete_upload -- only allow if version > 1 or admin
