"""Decide download requests, and resolve record files for approved ones."""
import re
from pathlib import Path

from django.db import transaction
from django.http import FileResponse
from django.utils import timezone

from apps.documents.models import RecordUpload
from apps.notifications.services import notify_download_reviewed
from core.enums import RequestStatus

from .models import DownloadRequest


class OwnDownloadRequest(Exception):
    """RDCO may not decide a request they made themselves."""


class DownloadRequestAlreadyDecided(Exception):
    """Only a pending request can be decided."""


def decide_download_request(download_request, reviewer, *, approved: bool) -> None:
    """
    Record RDCO's decision and tell the requester (IR-674). Every route that
    decides a request comes through here, so its rules cannot drift apart. The
    row lock makes two simultaneous decisions one decision and one refusal.
    """
    with transaction.atomic():
        current = DownloadRequest.objects.select_for_update().get(pk=download_request.pk)
        if current.requested_by_id == reviewer.pk:
            raise OwnDownloadRequest("You cannot decide your own download request.")
        if current.status != RequestStatus.PENDING:
            raise DownloadRequestAlreadyDecided("This request has already been reviewed.")
        download_request.status = RequestStatus.APPROVED if approved else RequestStatus.DECLINED
        download_request.reviewed_by = reviewer
        download_request.reviewed_at = timezone.now()
        download_request.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    notify_download_reviewed(download_request, reviewed_by=reviewer, approved=approved)


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


def resolve_served_manuscript(record, user):
    """
    `resolve_record_download_file`, for the reader `user` (IR-273): while an
    owner's revised manuscript is not yet submitted, everyone else is handed
    the latest version's (`versions.served_manuscript`).
    """
    from .versions import served_manuscript

    served = served_manuscript(record, user)
    if served and served.name != (record.abstract_file.name or None):
        return served.open("rb"), manuscript_download_name(record, served.name)
    return resolve_record_download_file(record)


def file_response_for_record(record) -> FileResponse | None:
    handle, filename = resolve_record_download_file(record)
    if not handle:
        return None
    return FileResponse(handle, as_attachment=True, filename=filename)
