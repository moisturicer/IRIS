"""
The owner answers the open revision requests with a new version (ADR-032 §5
and its 2026-10-08 Amendments; IR-273).

**This is ADR-003's contribution on the new model.** One act, by an owner of
a record on the new model with at least one revision request open, that has
changed since the newest request:

1. writes the record's next version through `versions.write_version`, the one
   writer (IR-416). A metadata-only version names the same manuscript as the
   version before it;
2. resolves every open request as `resubmitted` (ADR-021 §11);
3. resets clearances by the resubmission policy (ADR-004, IR-137):
   `CLEARANCE_AWARE`, the default, resets only the requesting parties'; the
   comparison arm `RESTART_ALL` resets every one. **Nothing else differs
   between the two arms**, so seats and assignments below do not read it;
4. returns the requesting parties' finished seats to `in_review`. Their
   reviewers review the new version. Every other party's seats, and the
   Adviser's and RDCO's, are untouched, so if RDCO asked only RDCO looks
   again, and if the Adviser asked only the Adviser does;
5. records the resubmission on the record, as the legacy path does, so
   `clearance_state.is_preserved` tells a surviving clearance from a reset
   one.

Nothing is deleted: every round stays visible as a version in the timeline.

**What counts as a change** (`unchanged_reason`): a manuscript other than the
latest version's, a supporting document an owner uploaded since the newest
request, or a detail edited since then (`Record.details_edited_at`). The
legacy `resubmit_record()` counts only supporting uploads.

The requesting parties' reviewers are told, after commit.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.records import lifecycle
from apps.records.versions import latest_version, write_version
from core.enums import (
    OPEN_SEAT_STATES,
    AssignmentState,
    ClearanceStatus,
    ResubmissionRequestState,
    SeatState,
    VersionCause,
)

from . import revisions, routing
from .models import RecordClearance, ResubmissionRequest, ReviewerSeat

logger = logging.getLogger(__name__)

_label = revisions._label


class NewVersionError(Exception):
    """Understood, but not possible as asked. A 400."""


class NewVersionRefused(Exception):
    """The caller may not submit a new version of this record. A 403."""


def _is_owner(record, user) -> bool:
    return (
        user is not None and getattr(user, "is_authenticated", False)
        and record.owners.filter(user=user).exists()
    )


def _parties(requests) -> list[str]:
    """The parties that asked, in the tracker's order."""
    asked = {r.party for r in requests}
    return [p for p in revisions.ASKING_PARTIES if p in asked]


# --- what a version would do ---------------------------------------------------------

def unchanged_reason(record, requests) -> Optional[str]:
    """Why a new version would answer none of `requests` now, or None (module note)."""
    from apps.documents.models import RecordUpload

    since = max(r.created_at for r in requests)
    latest = latest_version(record)
    stored = record.abstract_file.name or None
    if latest is None or (latest.manuscript.name or None) != stored:
        return None
    if record.details_edited_at is not None and record.details_edited_at > since:
        return None
    if RecordUpload.objects.filter(
        record=record, created_at__gt=since, uploaded_by__owned_records__record=record,
    ).exists():
        return None
    who = revisions._join([_label(p) for p in _parties(requests)])
    return (
        f"Nothing has changed since {who} asked for a revision. Upload a revised "
        f"manuscript or a supporting document, or edit the record's details, "
        f"then submit the new version."
    )


def _reset_offices(record, parties) -> list[str]:
    """The offices whose clearance this version resets, by the policy (module note)."""
    rows = RecordClearance.objects.filter(record=record)
    if lifecycle.resubmission_policy() is not lifecycle.ResubmissionPolicy.RESTART_ALL:
        rows = rows.filter(office__in=parties)
    return list(rows.values_list("office", flat=True))


def new_version_hint(record, user) -> Optional[dict]:
    """
    What record detail tells an owner about the version they would submit
    (IR-273), for the confirmation that names who reviews it. None for
    anyone else, or with no request open. A rendering hint; the endpoint
    re-checks all of it.

    - `number`: the version it would be;
    - `rereview`: the parties that asked, who review it;
    - `kept`: the offices whose `cleared` clearance it keeps;
    - `blocked`: why it cannot be submitted yet.
    """
    if not routing.is_new_model(record) or not _is_owner(record, user):
        return None
    requests = list(revisions.open_requests(record))
    if not requests:
        return None
    parties = _parties(requests)
    reset = set(_reset_offices(record, parties))
    latest = latest_version(record)
    kept = (
        RecordClearance.objects.filter(record=record, status=ClearanceStatus.CLEARED)
        .exclude(office__in=reset).order_by("office").values_list("office", flat=True)
    )
    return {
        "number": (latest.number if latest else 0) + 1,
        "rereview": [_label(p) for p in parties],
        "kept": [_label(o) for o in kept],
        "blocked": unchanged_reason(record, requests),
    }


# --- the act --------------------------------------------------------------------------

@transaction.atomic
def submit_new_version(record, actor):
    """
    Submit `record`'s next version, answering every open revision request
    (module note). Who comes first, then what: a caller who is not an owner is
    a 403 whatever state the record is in.
    """
    record = routing._locked(record)
    if not _is_owner(record, actor):
        raise NewVersionRefused("Only an owner of this record may submit a new version of it.")
    if not routing.is_new_model(record):
        raise NewVersionError(
            "This record is still on the current review pipeline. Use Resubmit "
            "for review instead."
        )
    # Read before anything is written, so a misconfigured policy refuses this
    # version cleanly instead of halfway through it (IR-137).
    lifecycle.resubmission_policy()
    requests = list(revisions.open_requests(record))
    if not requests:
        raise NewVersionError(
            "No reviewer has asked for a revision, so there is nothing for a new "
            "version to answer."
        )
    blocked = unchanged_reason(record, requests)
    if blocked:
        raise NewVersionError(blocked)

    parties = _parties(requests)
    reset = _reset_offices(record, parties)
    now = timezone.now()

    version = write_version(record, actor, VersionCause.REVISION)
    ResubmissionRequest.objects.filter(pk__in=[r.pk for r in requests]).update(
        state=ResubmissionRequestState.RESUBMITTED, resolved_by=actor, resolved_at=now,
    )
    # Recorded before the reset, so every reset row is dated after it and
    # never reads as preserved (`clearance_state.is_preserved`).
    record.resubmission_count = (record.resubmission_count or 0) + 1
    record.last_resubmitted_at = now
    record.save(update_fields=["resubmission_count", "last_resubmitted_at", "updated_at"])
    RecordClearance.objects.filter(record=record, office__in=reset).update(
        **lifecycle._clearance_reset_fields()
    )
    ReviewerSeat.objects.filter(
        assignment__record=record, assignment__party__in=parties,
        assignment__state=AssignmentState.ACTIVE, state=SeatState.DONE,
    ).update(state=SeatState.IN_REVIEW, done_at=None)

    # Which policy was active, per resubmission, as the legacy path logs it
    # (IR-137, ADR-004's documentation requirement).
    logger.info(
        "record %s: v%s submitted under %s policy; %s review again",
        record.pk, version.number, lifecycle.resubmission_policy().value, ", ".join(parties),
    )

    reviewers = list({
        seat.reviewer for seat in ReviewerSeat.objects.filter(
            assignment__record=record, assignment__party__in=parties,
            assignment__state=AssignmentState.ACTIVE, state__in=OPEN_SEAT_STATES,
            reviewer__isnull=False,
        ).select_related("reviewer")
    })
    from apps.notifications.services import notify_new_version

    transaction.on_commit(lambda: notify_new_version(
        record, version, submitted_by=actor, reviewers=reviewers,
        rereview=[_label(p) for p in parties],
    ))
    return version
