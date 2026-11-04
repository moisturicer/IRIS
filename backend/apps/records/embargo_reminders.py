"""
Embargo reminders (ADR-052 decision 9, IR-814).

The daily beat task calls `run_embargo_reminders`, which asks the database what
is owed. On an embargo's review date the owners and the Adviser are told
in-app, then every 5 working days until someone extends or releases it. A paper
owes at most one reminder at a time, the latest, so after downtime a superseded
one is skipped rather than sent late. The `EmbargoReminder` ledger's unique key
is the idempotency, as `DeadlineMoment`'s is for review deadlines. The row is
written before the notices, so a reminder is sent at most once: if every notice
for a step fails, that step is lost rather than sent twice, as ADR-043's are.

Nothing here changes an embargo: the date is a reminder, and only a person ends
one. It writes notifications and the ledger, and nothing else.
"""
import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.notifications.services import notify_embargo_review
from apps.reviews.deadlines import MANILA, working_days_between
from apps.reviews.models import Holiday
from core.enums import EmbargoState, PipelineStatus

from .models import EmbargoReminder, Record

logger = logging.getLogger(__name__)

TYPE_NAME = "Embargo Review"
EVERY_WORKING_DAYS = 5


def owed_step(until, today, holidays):
    """The one reminder owed `today` as (step, working days since the date), or None before it."""
    if today < until:
        return None
    waited = working_days_between(until, today, holidays)
    return waited // EVERY_WORKING_DAYS, waited


def _message(record, step, waited):
    due = f"{record.embargoed_until:%a %d %b %Y}"
    if step == 0:
        when = f"has reached its review date, {due}"
    else:
        when = f"passed its review date, {due}, {waited} working days ago"
    return (f'The embargo on "{record.title}" {when}. It stays in place until someone '
            "extends or releases it.")


def _recipients(record):
    """The active owners and the Adviser, each able to see the paper (§9)."""
    people = [owner.user for owner in record.owners.select_related("user").order_by("pk")]
    if record.adviser is not None:
        people.append(record.adviser)
    seen, told = set(), []
    for user in people:
        if user.pk in seen or not user.is_active:
            continue
        seen.add(user.pk)
        if Record.objects.visible_to(user).filter(pk=record.pk).exists():
            told.append(user)
    return told


@transaction.atomic
def _send(record_id, set_at, until, step, waited):
    # Recheck under the lock, so an extend or release that just committed wins.
    record = (Record.objects.select_for_update(of=("self",)).select_related("adviser")
              .filter(pk=record_id).first())
    if (record is None or record.pipeline_status == PipelineStatus.DRAFT
            or record.embargo_state != EmbargoState.ACTIVE
            or record.embargo_answered_at != set_at or record.embargoed_until != until):
        return 0
    try:
        with transaction.atomic():
            EmbargoReminder.objects.create(record=record, embargo_set_at=set_at, step=step)
    except IntegrityError:
        return 0
    message = _message(record, step, waited)
    for user in _recipients(record):
        notify_embargo_review(record, user, type_name=TYPE_NAME, message=message)
    return 1


def run_embargo_reminders(now=None):
    """Send every reminder owed at `now`. Returns how many papers were reminded."""
    now = now or timezone.now()
    today = now.astimezone(MANILA).date()
    holidays = set(Holiday.objects.values_list("date", flat=True))
    candidates = (
        Record.objects
        .exclude(pipeline_status=PipelineStatus.DRAFT)
        .filter(embargo_answered_at__isnull=False, embargoed_until__isnull=False,
                embargo_released_at__isnull=True, embargoed_until__lte=today)
        .values_list("pk", "embargo_answered_at", "embargoed_until")
    )
    sent = 0
    for pk, set_at, until in candidates:
        owed = owed_step(until, today, holidays)
        if owed is None:
            continue
        step, waited = owed
        try:
            sent += _send(pk, set_at, until, step, waited)
        except Exception:
            logger.exception("Embargo reminder step %s failed for record %s", step, pk)
    return sent
