"""Resolve record files for approved download requests."""
from django.http import FileResponse

from apps.documents.models import RecordUpload


def has_record_download_file(record) -> bool:
    """Whether `resolve_record_download_file` would find something.

    The same two places, asked without opening a handle -- a serializer only
    needs to know whether to advertise a URL.
    """
    if record.abstract_file:
        return True
    return (
        RecordUpload.objects.filter(record=record).exclude(file="").exists()
    )


def resolve_record_download_file(record):
    """
    Pick the best available PDF for download.
    Watermarking is not applied here — see download_service TODO when SRS requires it.
    """
    if record.abstract_file:
        name = record.abstract_file.name.split("/")[-1]
        return record.abstract_file.open("rb"), name

    upload = (
        RecordUpload.objects.filter(record=record)
        .exclude(file="")
        .order_by("-created_at")
        .first()
    )
    if upload and upload.file:
        return upload.file.open("rb"), upload.file.name.split("/")[-1]

    return None, None


def file_response_for_record(record) -> FileResponse | None:
    handle, filename = resolve_record_download_file(record)
    if not handle:
        return None
    return FileResponse(handle, as_attachment=True, filename=filename)
