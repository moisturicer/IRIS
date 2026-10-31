"""Decide download requests, say who may download, and resolve record files."""
import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.documents.models import RecordUpload
from apps.notifications.services import notify_download_reviewed
from core.enums import RequestStatus
from core.permissions import is_record_owner, is_record_participant, office_parties_of

from .models import DownloadRequest
from .watermark import CopyIdentity


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
        if approved:
            download_request.grant_expires_at = (
                download_request.reviewed_at + timedelta(days=settings.DOWNLOAD_GRANT_DAYS)
            )
        download_request.save(update_fields=["status", "reviewed_by", "reviewed_at", "grant_expires_at"])
    notify_download_reviewed(download_request, reviewed_by=reviewer, approved=approved)


def grant_is_live(download_request) -> bool:
    """An approved, unrevoked request whose grant has not expired."""
    expires = download_request.grant_expires_at
    return (
        download_request.status == RequestStatus.APPROVED
        and expires is not None
        and expires > timezone.now()
    )


def download_exemption(user, record) -> str | None:
    """Why `user` needs no request to download `record`, or None (ADR-048, decision 2)."""
    if is_record_owner(user, record):
        return "record_owner"
    if record.adviser_id == user.pk:
        return "record_adviser"
    if office_parties_of(user):
        return "office_staff"
    if is_record_participant(user, record):
        return "assigned_reviewer"
    return None


@dataclass(frozen=True)
class DownloadAccess:
    """May this reader download this record, and on what basis or why not?"""

    allowed: bool
    source: str = ""  # "exempt" or "grant", when allowed
    exemption: str | None = None
    request: DownloadRequest | None = None
    refusal: str = ""  # A key of DOWNLOAD_REFUSALS, when not allowed


#: Each refusal's `code` in the 403, and what the reader is told.
DOWNLOAD_REFUSALS = {
    "request_needed": "Request a download of this paper to save a copy.",
    "request_pending": "Your download request is waiting for RDCO's decision.",
    "request_declined": "Your download request was declined. You may request again.",
    "request_revoked": "Your download access was revoked. You may request again.",
    "grant_expired": "Your download access has expired. You may request again.",
}

_REFUSAL_BY_STATUS = {
    RequestStatus.DECLINED: "request_declined",
    RequestStatus.REVOKED: "request_revoked",
    RequestStatus.APPROVED: "grant_expired",
}


def download_access(user, record) -> DownloadAccess:
    """
    The one answer to "may this reader save a copy?" (ADR-048).

    The reader's newest decided request is the one that counts, so revoking it
    is not undone by an older approval. A pending request does not end a live
    grant, and is what the reader hears about when no grant is live.
    """
    exemption = download_exemption(user, record)
    if exemption:
        return DownloadAccess(allowed=True, source="exempt", exemption=exemption)

    requests = list(
        DownloadRequest.objects.filter(record=record, requested_by=user).order_by("-created_at", "-pk")
    )
    decided = next((r for r in requests if r.status != RequestStatus.PENDING), None)
    if decided and grant_is_live(decided):
        return DownloadAccess(allowed=True, source="grant", request=decided)
    if any(r.status == RequestStatus.PENDING for r in requests):
        return DownloadAccess(allowed=False, refusal="request_pending")
    if decided is None:
        return DownloadAccess(allowed=False, refusal="request_needed")
    return DownloadAccess(allowed=False, refusal=_REFUSAL_BY_STATUS[decided.status])


def copy_identity(user, access: DownloadAccess) -> CopyIdentity:
    """What a copy made under `access` says about who it was made for (IR-676)."""
    return CopyIdentity(
        name=user.get_full_name(),
        email=user.email,
        date=timezone.localdate().isoformat(),
        basis=f"request #{access.request.pk}" if access.request else access.exemption.replace("_", " "),
    )


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
    Pick the best available PDF for download. It comes back unmarked: the
    download route is what marks a copy that leaves IRIS (`watermark.py`).
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
