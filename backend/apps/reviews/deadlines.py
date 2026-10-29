"""Informational assignment clocks. No workflow decision consumes these (ADR-043)."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from apps.audit import workflow as audit
from core.enums import AssignmentState, DocumentRequestState, ResubmissionRequestState
from core.permissions import is_office_coordinator

from .models import Extension, Holiday, RecordAssignment, ResubmissionRequest, Turnaround
from .seats import SeatError, SeatRefused

MANILA = ZoneInfo("Asia/Manila")


def working_days_after(day, count):
    """Count after the opening date, with one holiday snapshot per operation."""
    holidays = set(Holiday.objects.values_list("date", flat=True))
    while count:
        day += timedelta(days=1)
        if day.weekday() < 5 and day not in holidays:
            count -= 1
    return day


def end_of_day(day):
    return datetime.combine(day, time(23, 59), tzinfo=MANILA)


def start_clock(assignment, now):
    """New assignment or new-Version rereview only; never resample on reassignment."""
    days = Turnaround.objects.filter(party=assignment.party).values_list("working_days", flat=True).first()
    assignment.clock_started_at = now
    assignment.due_at = (
        end_of_day(working_days_after(now.astimezone(MANILA).date(), days))
        if days is not None else None
    )
    assignment.original_due_at = assignment.due_at
    # A request can survive a new Version: only the new clock's wait counts.
    assignment.document_pause_started_at = (
        now if assignment.pk and assignment.document_requests.filter(state=DocumentRequestState.OPEN).exists()
        else None
    )


def revision_pending(assignment):
    prefetched = getattr(assignment, "deadline_open_revisions", None)
    if prefetched is not None:
        return bool(prefetched)
    return assignment.resubmission_requests.filter(state=ResubmissionRequestState.OPEN).exists()


def with_deadlines(queryset, *, prefix=""):
    """Batch list facts so My Reviews' SQL count stays independent of page size."""
    return queryset.prefetch_related(
        f"{prefix}extensions",
        Prefetch(f"{prefix}resubmission_requests",
                 queryset=ResubmissionRequest.objects.filter(state=ResubmissionRequestState.OPEN),
                 to_attr="deadline_open_revisions"),
    )


def can_extend(assignment, user):
    return bool(
        assignment and assignment.due_at and assignment.state == AssignmentState.ACTIVE
        and is_office_coordinator(user, assignment.party) and not revision_pending(assignment)
    )


def _move(assignment, due_at, reason, *, actor=None, system=False):
    """Caller holds the assignment lock and owns the transaction."""
    extension = Extension.objects.create(
        assignment=assignment, previous_due_at=assignment.due_at, due_at=due_at,
        reason=reason, actor=actor, system=system,
    )
    assignment.due_at = due_at
    assignment.save(update_fields=["due_at"])
    # Unlike best-effort operational logging this history is mandatory: a
    # failed audit insert rolls back the date movement and its Extension.
    audit.assignment_extended(extension)
    return extension


@transaction.atomic
def extend(assignment, actor, *, due_at, reason):
    # Match the workflow lock order: record, then assignment.
    from apps.records.models import Record

    Record.objects.select_for_update().get(pk=assignment.record_id)
    assignment = RecordAssignment.objects.select_for_update().get(pk=assignment.pk)
    if not is_office_coordinator(actor, assignment.party):
        raise SeatRefused("Only a coordinator of this office may extend its assignment.")
    if not can_extend(assignment, actor):
        raise SeatError("This assignment has no running deadline to extend.")
    if not isinstance(reason, str) or not reason.strip():
        raise SeatError("Give a reason for the extension.")
    if due_at is None or timezone.is_naive(due_at) or due_at <= assignment.due_at:
        raise SeatError("The new deadline must be later than the current deadline, with a timezone.")
    local = due_at.astimezone(MANILA)
    if local.time() != time(23, 59):
        raise SeatError("The deadline must be at 23:59 Asia/Manila.")
    _move(assignment, due_at, reason.strip(), actor=actor)
    return assignment


def sync_document_pause(assignment, *, now):
    """Called under its row lock, inside the document request's save transaction.

    The first open request starts a span; only the last closure ends it.
    Rejected uploads reopen requests and start a new span, not their old one.
    Whole Manila working days are counted after the start date through closure,
    consistently with turnaround counting. A same-day wait adds zero days.
    """
    if assignment.due_at is None or assignment.state != AssignmentState.ACTIVE:
        return
    if assignment.document_requests.filter(state=DocumentRequestState.OPEN).exists():
        if assignment.document_pause_started_at is None:
            assignment.document_pause_started_at = now
            assignment.save(update_fields=["document_pause_started_at"])
        return
    start = assignment.document_pause_started_at
    if start is None:
        return
    holidays = set(Holiday.objects.values_list("date", flat=True))
    day, end = start.astimezone(MANILA).date(), now.astimezone(MANILA).date()
    days = 0
    while day < end:
        day += timedelta(days=1)
        days += day.weekday() < 5 and day not in holidays
    if days:
        due = end_of_day(working_days_after(assignment.due_at.astimezone(MANILA).date(), days))
        _move(assignment, due, f"Document request pause: {days} working days.", system=True)
    assignment.document_pause_started_at = None
    assignment.save(update_fields=["document_pause_started_at"])


def is_overdue(due_at, *, paused, now):
    """An active assignment is overdue past a due date, while its clock runs."""
    return bool(due_at and not paused and now > due_at)


def deadline_payload(assignment, user=None, *, readable=True):
    """One projection for tracker, seats, pools and capabilities; prose is private."""
    if assignment is None:
        return {"due_at": None, "original_due_at": None, "is_overdue": False,
                "clock_paused": False, "extensions": [], "can_extend": False}
    paused = bool(assignment.document_pause_started_at) or revision_pending(assignment)
    due = assignment.due_at
    return {
        "due_at": due.isoformat() if due else None,
        "original_due_at": assignment.original_due_at.isoformat() if assignment.original_due_at else None,
        "is_overdue": assignment.state == AssignmentState.ACTIVE
                      and is_overdue(due, paused=paused, now=timezone.now()),
        "clock_paused": paused,
        "can_extend": can_extend(assignment, user),
        "extensions": [{"id": e.pk, "previous_due_at": e.previous_due_at.isoformat(),
                        "due_at": e.due_at.isoformat(), "reason": e.reason if readable else None,
                        "system": e.system, "actor": e.actor_id if readable else None,
                        "created_at": e.created_at.isoformat()}
                       for e in assignment.extensions.all()],
    }
