"""
Retention of download notes (ADR-051 decision 19, IR-794).

A reader's note on a download request and RDCO's decline or revocation note are
free text about a person's reasons. Once the request is over and its period has
passed, both are blanked. The request, its status, dates and people stay: only
the text goes, so the page shows what it already shows for a request made before
notes existed ("No note recorded").

A pending request is never touched, since someone still has to decide on it.
Otherwise a request's age runs from the latest thing that happened to it: its
creation, RDCO's decision, a revocation, its cancellation or the end of its
grant. A note exactly one period old is kept; one second older is erased.
"""
from django.db.models.functions import Greatest

from apps.audit.retention import RetentionType, register
from core.enums import RequestStatus

from .models import DownloadRequest

TYPE_KEY = "download_notes"
SETTING_KEY = "retention.download_notes_days"


def erase_download_notes(cutoff) -> int:
    """Blank the notes of every finished download request last active before `cutoff`."""
    return (
        DownloadRequest.objects
        .exclude(status=RequestStatus.PENDING)
        .exclude(note="", rdco_note="")
        .annotate(last_activity=Greatest(
            "created_at", "reviewed_at", "revoked_at", "cancelled_at", "grant_expires_at",
        ))
        .filter(last_activity__lt=cutoff)
        .update(note="", rdco_note="")
    )


register(RetentionType(key=TYPE_KEY, setting_key=SETTING_KEY, erase=erase_download_notes))
