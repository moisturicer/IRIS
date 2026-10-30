"""
Assignment reminders and overdue escalation (ADR-043 §7–§8, IR-620–IR-621).

The hourly beat task calls `run_deadline_notifications`, which asks the
database what is owed now. An assignment owes at most one moment at a time,
the latest, so after downtime a superseded moment is skipped rather than
sent late. The `DeadlineMoment` ledger's unique key is the idempotency.

Nothing here decides, clears, routes or withdraws: it only writes
notifications, the ledger and escalation audit events.
"""
import logging
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.notifications.services import notify_deadline
from core.enums import AssignmentState, Party, ResubmissionRequestState, SeatState
from core.permissions import OFFICE_PARTY_BY_ROLE, is_office_coordinator

from .deadlines import overdue_working_days, working_days_between
from .models import DeadlineMoment, Holiday, RecordAssignment

logger = logging.getLogger(__name__)

MANILA = ZoneInfo("Asia/Manila")
Kind = DeadlineMoment.Kind

#: Notification type and wording per reminder kind.
REMINDERS = {
    Kind.DUE_SOON: ("Review Due Soon", '{party} review of "{title}" is due on {due}.'),
    Kind.DUE_TODAY: ("Review Due Today", '{party} review of "{title}" is due today.'),
    Kind.ESCALATION: ("Review Overdue",
                      '{party} review of "{title}" is {days} overdue. Reviewer: {reviewers}.'),
}


def current_moment(due_at, now, holidays):
    """The one moment owed now as (kind, step), or None."""
    today = now.astimezone(MANILA).date()
    due = due_at.astimezone(MANILA).date()
    if now > due_at:
        overdue = overdue_working_days(due_at, now, holidays)
        return (Kind.ESCALATION, (overdue - 1) // 5) if overdue else None
    if today >= due:
        return Kind.DUE_TODAY, 0
    if working_days_between(today, due, holidays) <= 2:
        return Kind.DUE_SOON, 0
    return None


def _coordinators(party):
    from apps.accounts.models import User

    roles = [role for role, office in OFFICE_PARTY_BY_ROLE.items() if office == party]
    users = User.objects.filter(is_active=True, is_office_coordinator=True,
                                role__name__in=roles).order_by("pk")
    return [user for user in users if is_office_coordinator(user, party)]


def _reminder_recipients(assignment):
    """Seat holders not done; for a pool with no live Seat, its coordinators."""
    live = [s for s in assignment.seats.all() if s.state != SeatState.WITHDRAWN]
    if live:
        return [s.reviewer for s in live if s.state != SeatState.DONE and s.reviewer]
    if assignment.party == Party.ADVISER:
        adviser = assignment.record.adviser
        return [adviser] if adviser else []
    return _coordinators(assignment.party)


def _readable(record, users):
    """§7: every recipient passes the one visibility predicate first."""
    from apps.records.models import Record

    return [u for u in users if Record.objects.visible_to(u).filter(pk=record.pk).exists()]


def _paused(assignment):
    return bool(assignment.document_pause_started_at) or assignment.resubmission_requests.filter(
        state=ResubmissionRequestState.OPEN).exists()


def _reviewer_names(assignment):
    names = [s.reviewer.get_full_name() or s.reviewer.email for s in assignment.seats.all()
             if s.state not in (SeatState.WITHDRAWN, SeatState.DONE) and s.reviewer]
    return ", ".join(names) or "unclaimed"


def _escalation_recipients(assignment):
    coordinators = _coordinators(assignment.party)
    if coordinators:
        return coordinators
    logger.warning("No coordinator for %s assignment %s; escalating to RDCO coordinators",
                   assignment.party, assignment.pk)
    return _coordinators(Party.RDCO) if assignment.party != Party.RDCO else []


@transaction.atomic
def _send(pk, record_id, due_at, kind, step, overdue=0):
    # Workflow lock order: record, then assignment. Recheck under the lock, so
    # a completion, withdrawal or Extension that just committed wins.
    from apps.records.models import Record

    Record.objects.select_for_update().get(pk=record_id)
    assignment = (RecordAssignment.objects.select_for_update(of=("self",))
                  .select_related("record", "record__adviser").get(pk=pk))
    if assignment.state != AssignmentState.ACTIVE or assignment.due_at != due_at or _paused(assignment):
        return 0
    if kind == Kind.ESCALATION and assignment.party == Party.ADVISER:
        return 0
    try:
        with transaction.atomic():
            DeadlineMoment.objects.create(assignment=assignment, due_at=due_at, kind=kind, step=step)
    except IntegrityError:
        return 0
    record = assignment.record
    type_name, template = REMINDERS[kind]
    message = template.format(party=Party(assignment.party).label, title=record.title,
                              due=f"{due_at.astimezone(MANILA):%a %d %b %Y}",
                              days=f"{overdue} working day{'s' * (overdue != 1)}",
                              reviewers=_reviewer_names(assignment) if overdue else "")
    recipients = (_escalation_recipients(assignment) if kind == Kind.ESCALATION
                  else _reminder_recipients(assignment))
    recipients = _readable(record, recipients)
    if kind == Kind.ESCALATION:
        from apps.audit.workflow import assignment_escalated

        assignment_escalated(assignment, step=step, overdue=overdue, recipients=recipients)
    for user in recipients:
        notify_deadline(record, user, type_name=type_name, message=message)
    return 1


def run_deadline_notifications(now=None):
    """Send every moment owed at `now`. Returns how many moments were sent."""
    now = now or timezone.now()
    holidays = set(Holiday.objects.values_list("date", flat=True))
    candidates = (RecordAssignment.objects
                  .filter(state=AssignmentState.ACTIVE, due_at__isnull=False,
                          document_pause_started_at__isnull=True)
                  .exclude(resubmission_requests__state=ResubmissionRequestState.OPEN)
                  .values_list("pk", "record_id", "due_at"))
    sent = 0
    for pk, record_id, due_at in candidates:
        moment = current_moment(due_at, now, holidays)
        if moment is None:
            continue
        try:
            sent += _send(pk, record_id, due_at, *moment,
                          overdue=overdue_working_days(due_at, now, holidays))
        except Exception:
            logger.exception("Deadline moment %s failed for assignment %s", moment[0], pk)
    return sent
