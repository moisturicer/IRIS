"""`review_clock_for_testing` puts the clock where IR-631's run needs it.

What it must not do matters as much as what it does: moving a Due date is not
an Extension, so it writes no Extension row, and it touches only an *active*
assignment, the one a reminder or Escalation would be about. The reminder tick
is the beat job's own function, so a reminder sent here is the one beat sends.
"""
from datetime import date, datetime
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError

from apps.notifications.models import Notification
from core.enums import AssignmentState, Party

from .deadlines import MANILA
from .management.commands.review_clock_for_testing import working_day_offset
from .models import DeadlineMoment, Extension, RecordAssignment, Turnaround
from .test_seats import SeatTestBase


def run(*args, force=True):
    out = StringIO()
    call_command("review_clock_for_testing", *args, *(["--force"] if force else []), stdout=out)
    return out.getvalue()


class WorkingDayOffsetTests(SeatTestBase):
    def test_counts_back_over_a_weekend_and_a_holiday(self):
        # Wed 2027-03-10; back three working days skips the weekend and Mon's holiday.
        holidays = {date(2027, 3, 8)}
        self.assertEqual(working_day_offset(date(2027, 3, 10), -3, holidays), date(2027, 3, 4))

    def test_zero_is_the_same_day_and_forward_matches_going_forward(self):
        self.assertEqual(working_day_offset(date(2027, 3, 10), 0, set()), date(2027, 3, 10))
        self.assertEqual(working_day_offset(date(2027, 3, 12), 1, set()), date(2027, 3, 15))


class ReviewClockForTestingTests(SeatTestBase):
    def setUp(self):
        Turnaround.objects.create(party=Party.ITSO, working_days=5)
        self.record = self.make_record(adviser=self.adviser)
        self.assignment = RecordAssignment.objects.create(record=self.record, party=Party.ITSO)

    def test_refuses_with_debug_off_without_force(self):
        with self.assertRaises(CommandError):
            run("--turnaround", "itso=3", force=False)

    def test_sets_a_turnaround_as_an_administrator_would(self):
        run("--turnaround", "ierc=7", "--turnaround", "itso=2")
        self.assertEqual(Turnaround.objects.get(party=Party.IERC).working_days, 7)
        self.assertEqual(Turnaround.objects.get(party=Party.ITSO).working_days, 2)

    def test_refuses_a_retired_or_unknown_party(self):
        for spec in ("intake=5", "registrar=5", "itso=five"):
            with self.subTest(spec=spec), self.assertRaises(CommandError):
                run("--turnaround", spec)

    def test_moves_the_active_due_date_into_the_past_without_an_extension(self):
        run("--record", str(self.record.pk), "--party", "itso", "--due-in-working-days", "-2")
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.due_at, self.assignment.original_due_at)
        self.assertEqual(self.assignment.due_at.astimezone(MANILA).hour, 23)
        self.assertLess(self.assignment.due_at, self.assignment.opened_at)
        self.assertFalse(Extension.objects.exists())

    def test_refuses_a_party_with_no_active_assignment(self):
        self.assignment.state = AssignmentState.COMPLETED
        self.assignment.save(update_fields=["state"])
        with self.assertRaises(CommandError):
            run("--record", str(self.record.pk), "--party", "itso", "--due-in-working-days", "-2")

    def test_refuses_an_assignment_with_no_due_date(self):
        RecordAssignment.objects.filter(pk=self.assignment.pk).update(due_at=None, original_due_at=None)
        with self.assertRaisesMessage(CommandError, "no Due date"):
            run("--record", str(self.record.pk), "--party", "itso", "--due-in-working-days", "-2")

    def test_moving_needs_all_three_arguments(self):
        with self.assertRaises(CommandError):
            run("--record", str(self.record.pk), "--due-in-working-days", "-2")

    def test_the_tick_is_the_beat_jobs_function(self):
        with patch(
            "apps.reviews.management.commands.review_clock_for_testing.run_deadline_notifications",
            return_value=4,
        ) as tick:
            self.assertIn("deadline moments sent: 4", run("--run-notifications"))
        tick.assert_called_once_with()

    def test_an_overdue_tick_escalates_and_decides_nothing(self):
        # A Wednesday, pinned: an Escalation is owed only once a whole working
        # day has passed, so on a weekend "one working day ago" is not overdue
        # yet -- correct, and the reason the run itself moves dates by -2.
        wednesday = datetime(2027, 3, 10, 12, 0, tzinfo=MANILA)
        status_before = self.record.pipeline_status
        with patch("django.utils.timezone.now", return_value=wednesday):
            run("--record", str(self.record.pk), "--party", "itso", "--due-in-working-days", "-1")
            run("--run-notifications")
        self.assertTrue(DeadlineMoment.objects.filter(
            assignment=self.assignment, kind=DeadlineMoment.Kind.ESCALATION,
        ).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.itso_coordinator).exists())
        self.record.refresh_from_db()
        self.assignment.refresh_from_db()
        self.assertEqual(self.record.pipeline_status, status_before)
        self.assertEqual(self.assignment.state, AssignmentState.ACTIVE)
