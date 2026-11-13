"""
Settling a notification when the task it asked for has ended (ADR-069, IR-1075).

A notification that asks its recipient to act is bound at creation to one row
(`task_kind` + `task_id`). **Settling** looks at that row and, once its task
has ended, stamps `resolved_at` and `resolved_label` on the notification. The
stamp is written once and never cleared, so a resolved notification is final
whatever the workflow does next.

Why stored, not derived on each read (the choice ADR-069 decision 6 leaves
here). Two paths *reopen* the row a task lived on: a resubmission reopens the
same `RecordAssignment` and puts finished seats back in review
(`reviews/new_version.py`), and rejecting an uploaded document reopens a
fulfilled `DocumentRequest`. A notification worked out from today's row would
therefore un-resolve itself, and its unread count would rise on its own. So the
ending is remembered on the notification:

- every resolver below reads only a fact that is final once true (a closed
  assignment, a withdrawn seat, a `Review` written for the seat, a request that
  left `open`/`pending`);
- `settle_record` runs **before** each of the two reopening paths, so a task
  that ended is stamped before its row is reopened;
- the notification endpoints settle what the reader can see before answering,
  so anything else that ended is stamped the first time it is looked at.

The label is built only from workflow facts the recipient already sees (the
office, the seat holder, the date): it never names a record they cannot read.
Notifications sent before IR-1075 have no task and are never resolved.
"""
import logging

from django.utils import timezone

from core.enums import (
    AssignmentState,
    DocumentRequestState,
    Party,
    RequestStatus,
    ResubmissionRequestState,
    SeatState,
)
from .models import Notification, TaskKind

logger = logging.getLogger(__name__)


def _day(when) -> str:
    """"20 Oct": the day in the site's own time zone, no leading zero."""
    local = timezone.localtime(when)
    return f"{local.day} {local:%b}"


def _party(party: str) -> str:
    return str(Party(party).label)


def _closed_assignment(assignment, notification):
    """How a closed assignment ended, as (when, label); None while it is open."""
    if assignment.state == AssignmentState.ACTIVE:
        return None
    when = assignment.closed_at or timezone.now()
    day = _day(when)
    if assignment.state == AssignmentState.WITHDRAWN:
        if assignment.closed_by_decision_id:
            return when, f"Closed by the Decision on {day}"
        return when, f"Withdrawn on {day}"
    direct = notification.recipient_id is not None
    if direct and assignment.closed_by_id == notification.recipient_id:
        return when, f"Reviewed by you on {day}"
    return when, f"{_party(assignment.party)} review finished on {day}"


def _assignment(notification):
    from apps.reviews.models import RecordAssignment

    assignment = RecordAssignment.objects.filter(pk=notification.task_id).first()
    if assignment is None:
        return None
    if notification.broadcast_to_role_id is not None:
        # A pool broadcast: the task is the pool's, so it ends for every member
        # at once when anyone takes it. Seats are never deleted, so "a seat
        # exists" stays true even if that seat is later withdrawn.
        seat = (
            assignment.seats.select_related("reviewer")
            .order_by("assigned_at", "pk").first()
        )
        if seat is not None:
            who = seat.reviewer.get_full_name() or seat.reviewer.email if seat.reviewer else "a colleague"
            verb = "Claimed by" if seat.source == "claimed" else "Taken by"
            return seat.assigned_at, f"{verb} {who} on {_day(seat.assigned_at)}"
    return _closed_assignment(assignment, notification)


def _seat(notification):
    from apps.reviews.models import Review, ReviewerSeat

    seat = (
        ReviewerSeat.objects.select_related("assignment")
        .filter(pk=notification.task_id).first()
    )
    if seat is None:
        return None
    # A Review of the seat holder's own, written after this notification: the
    # reviewer did what was asked. A review from before it (the first round of a
    # resubmitted record) is not this notification's answer.
    review = (
        Review.objects.filter(
            assignment=seat.assignment, reviewed_by_id=seat.reviewer_id,
            created_at__gte=notification.created_at,
        ).order_by("created_at").first()
    )
    if review is not None:
        return review.created_at, f"Reviewed by you on {_day(review.created_at)}"
    if seat.state == SeatState.WITHDRAWN:
        label = "Closed by the Decision" if seat.closed_by_decision_id else "Your seat was withdrawn"
        return timezone.now(), label
    return _closed_assignment(seat.assignment, notification)


def _revision(notification):
    from apps.reviews.models import ResubmissionRequest

    request = ResubmissionRequest.objects.filter(pk=notification.task_id).first()
    if request is None or request.state == ResubmissionRequestState.OPEN:
        return None
    when = request.resolved_at or timezone.now()
    day = _day(when)
    if request.state == ResubmissionRequestState.WITHDRAWN:
        if request.closed_by_decision_id:
            return when, f"Closed by the Decision on {day}"
        return when, f"Withdrawn by {_party(request.party)} on {day}"
    return when, f"Answered with a new version on {day}"


def _document_request(notification):
    from apps.documents.models import DocumentRequest

    request = DocumentRequest.objects.filter(pk=notification.task_id).first()
    if request is None or request.state == DocumentRequestState.OPEN:
        return None
    when = request.closed_at or timezone.now()
    day = _day(when)
    if request.state == DocumentRequestState.FULFILLED:
        return when, f"Documents uploaded on {day}"
    if request.closed_by_decision_id:
        return when, f"Closed by the Decision on {day}"
    return when, f"Withdrawn on {day}"


def _decided_request(model_path):
    """A request RDCO or an admin rules on: ends when it leaves `pending`."""
    def resolve(notification):
        from django.apps import apps

        request = apps.get_model(model_path).objects.filter(pk=notification.task_id).first()
        if request is None or request.status == RequestStatus.PENDING:
            return None
        when = request.reviewed_at or timezone.now()
        return when, f"{request.get_status_display()} on {_day(when)}"
    return resolve


RESOLVERS = {
    TaskKind.ASSIGNMENT: _assignment,
    TaskKind.SEAT: _seat,
    TaskKind.REVISION: _revision,
    TaskKind.DOCUMENT_REQUEST: _document_request,
    TaskKind.DOWNLOAD_REQUEST: _decided_request("records.DownloadRequest"),
    TaskKind.DELETE_REQUEST: _decided_request("records.DeleteRequest"),
    TaskKind.ROLE_REQUEST: _decided_request("accounts.RoleRequest"),
}


def settle(notifications) -> int:
    """
    Stamp every unresolved, task-bound notification in `notifications` whose
    task has ended. Idempotent, and a stamp is never overwritten. Returns how
    many it stamped.

    A resolver that fails leaves its notification unresolved and is logged: a
    listing must never fail because one task could not be read.
    """
    settled = 0
    pending = notifications.filter(resolved_at__isnull=True).exclude(task_kind="")
    for notification in pending.select_related("record"):
        resolver = RESOLVERS.get(notification.task_kind)
        if resolver is None or notification.task_id is None:
            continue
        try:
            outcome = resolver(notification)
        except Exception:
            logger.exception("Settling notification %s failed", notification.pk)
            continue
        if outcome is None:
            continue
        when, label = outcome
        settled += Notification.objects.filter(
            pk=notification.pk, resolved_at__isnull=True,
        ).update(resolved_at=when, resolved_label=label[:200])
    return settled


def settle_for(user) -> int:
    """Settle what `user` can see: called before a list, a read or a mark-all."""
    return settle(Notification.objects.visible_to(user))


def settle_record(record) -> int:
    """
    Settle every notification about `record`. Called just before a resubmission
    or a rejected document reopens a row, so what ended is stamped first.
    """
    return settle(Notification.objects.filter(record=record))
