"""Put the review clock where a verification run needs it (IR-631).

    python manage.py review_clock_for_testing --turnaround itso=5 --turnaround adviser=5
    python manage.py review_clock_for_testing --record 42 --party ierc --due-in-working-days -3
    python manage.py review_clock_for_testing --run-notifications

IR-631's coordination journey has to show a reminder and an Escalation, and
that nothing is decided when a Due date passes (ADR-043). On a real clock that
means waiting days. This command does the two things that would otherwise need
waiting or a screen the run cannot reach:

``--turnaround PARTY=DAYS``
    The Turnaround an administrator enters in Django admin. A party with none
    has no Due date at all, and ``seed_demo --accounts-only`` sets none. The
    run cannot use the admin screen itself: production settings check the
    CSRF origin against HTTPS, and nothing in the run terminates TLS.

``--record ID --party PARTY --due-in-working-days N``
    Moves the party's *active* assignment's Due date to the end of the Manila
    working day N working days from today (negative is the past), as if its
    turn had started that much earlier: ``due_at`` and ``original_due_at``
    together. This is not an Extension (an Extension only moves a date later,
    always with a reason, and is history a reader sees) and it writes none.
    Already-sent reminders keep their rows; a new Due date is a new key, so
    the moments for it are owed afresh, exactly as after an Extension.

``--run-notifications``
    One tick of the hourly beat job, now: ``run_deadline_notifications()``,
    the function ``apps.reviews.tasks.send_deadline_notifications`` calls.

Test data only. Refuses with ``DEBUG`` off unless ``--force``, as
``seed_demo`` does, because it rewrites a date the workflow fixed.
"""
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.reviews.deadlines import MANILA, end_of_day
from apps.reviews.models import Holiday, RecordAssignment, Turnaround
from apps.reviews.reminders import run_deadline_notifications
from core.enums import RETIRED_PARTIES, AssignmentState, Party


def _parties():
    return {p.value for p in Party if p not in RETIRED_PARTIES}


def working_day_offset(day, count, holidays):
    """The date `count` working days from `day`; negative counts go back.

    Zero is `day` itself. Weekends and holidays are skipped, as
    `deadlines.working_days_after` skips them going forward.
    """
    step = 1 if count > 0 else -1
    remaining = abs(count)
    while remaining:
        day += timedelta(days=step)
        if day.weekday() < 5 and day not in holidays:
            remaining -= 1
    return day


class Command(BaseCommand):
    help = "Set Turnarounds, move an active assignment's Due date, or run one reminder tick (test data only)."

    def add_arguments(self, parser):
        parser.add_argument("--turnaround", action="append", default=[], metavar="PARTY=DAYS")
        parser.add_argument("--record", type=int)
        parser.add_argument("--party")
        parser.add_argument("--due-in-working-days", type=int)
        parser.add_argument("--run-notifications", action="store_true")
        parser.add_argument("--force", action="store_true",
                            help="Run with DEBUG off. This rewrites workflow dates: test stacks only.")

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError("DEBUG is off. This rewrites workflow dates; pass --force on a test stack only.")

        moving = options["record"] is not None or options["party"] or options["due_in_working_days"] is not None
        if not (options["turnaround"] or moving or options["run_notifications"]):
            raise CommandError("Nothing to do: give --turnaround, --record/--party/--due-in-working-days, or --run-notifications.")

        for spec in options["turnaround"]:
            self._set_turnaround(spec)
        if moving:
            self._move_due_date(options["record"], options["party"], options["due_in_working_days"])
        if options["run_notifications"]:
            sent = run_deadline_notifications()
            self.stdout.write(f"deadline moments sent: {sent}")

    def _set_turnaround(self, spec):
        party, _, days = spec.partition("=")
        if party not in _parties() or not days.isdigit():
            raise CommandError(f"--turnaround wants PARTY=DAYS with PARTY one of {sorted(_parties())}, got {spec!r}.")
        Turnaround.objects.update_or_create(party=party, defaults={"working_days": int(days)})
        self.stdout.write(f"turnaround {party} = {int(days)} working days")

    @transaction.atomic
    def _move_due_date(self, record_id, party, offset):
        if record_id is None or not party or offset is None:
            raise CommandError("Moving a Due date needs --record, --party and --due-in-working-days together.")
        assignment = (RecordAssignment.objects.select_for_update()
                      .filter(record_id=record_id, party=party, state=AssignmentState.ACTIVE).first())
        if assignment is None:
            raise CommandError(f"Record {record_id} has no active {party} assignment.")
        if assignment.due_at is None:
            raise CommandError(
                f"Record {record_id}'s {party} assignment has no Due date: its party had no "
                "Turnaround when the turn started, and IRIS never supplies one."
            )
        holidays = set(Holiday.objects.values_list("date", flat=True))
        today = timezone.now().astimezone(MANILA).date()
        due_at = end_of_day(working_day_offset(today, offset, holidays))
        assignment.due_at = due_at
        assignment.original_due_at = due_at
        assignment.save(update_fields=["due_at", "original_due_at"])
        self.stdout.write(f"record {record_id} {party}: due {due_at.isoformat()}")
