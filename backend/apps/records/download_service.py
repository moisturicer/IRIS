"""Resolve record files for approved download requests."""
import re
from pathlib import Path

from django.http import FileResponse

from apps.documents.models import RecordUpload


def manuscript_download_name(record, stored_name: str, *, version=None) -> str:
    # The stored name is random, not the title (IR-422) -- rebuild a readable
    # download name instead of reading it back off the stored path. An earlier
    # version says which one it is (IR-416).
    ext = Path(stored_name).suffix or ".pdf"
    title = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", record.title or "download").strip() or "download"
    suffix = f" (v{version})" if version is not None else ""
    return f"{title[:150]}{suffix}{ext}"


def _manuscript_download_name(record) -> str:
    return manuscript_download_name(record, record.abstract_file.name)


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
        return record.abstract_file.open("rb"), _manuscript_download_name(record)

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
