"""The calendar and Manila boundary run without a database or a wall clock."""
from datetime import datetime, timezone as utc_timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from .deadlines import MANILA, deadline_payload, start_clock, working_days_after


class DeadlineCalendarTests(SimpleTestCase):
    def test_count_starts_after_opening_day_skips_weekend_and_holiday(self):
        opening = datetime(2027, 3, 25, tzinfo=MANILA).date()
        holiday = datetime(2027, 3, 26, tzinfo=MANILA).date()
        with patch("apps.reviews.deadlines.Holiday.objects.values_list", return_value=[holiday]):
            self.assertEqual(working_days_after(opening, 2).isoformat(), "2027-03-30")

    def test_utc_opening_is_counted_from_manila_date(self):
        opening = datetime(2027, 3, 25, 18, tzinfo=utc_timezone.utc)  # Friday in Manila
        assignment = SimpleNamespace(party="itso", pk=None)
        with patch("apps.reviews.deadlines.Turnaround.objects.filter") as config, \
             patch("apps.reviews.deadlines.Holiday.objects.values_list", return_value=[]):
            config.return_value.values_list.return_value.first.return_value = 1
            start_clock(assignment, opening)
        self.assertEqual(assignment.due_at.isoformat(), "2027-03-29T23:59:00+08:00")

    def test_no_turnaround_means_no_deadline(self):
        assignment = SimpleNamespace(party="itso", pk=None)
        with patch("apps.reviews.deadlines.Turnaround.objects.filter") as config:
            config.return_value.values_list.return_value.first.return_value = None
            start_clock(assignment, datetime(2027, 3, 25, tzinfo=MANILA))
        self.assertIsNone(assignment.due_at)
        self.assertIsNone(assignment.original_due_at)

    def test_due_at_2359_not_in_the_due_morning_and_pauses_suppress_overdue(self):
        due = datetime(2027, 3, 26, 23, 59, tzinfo=MANILA)
        assignment = SimpleNamespace(
            due_at=due, original_due_at=due, state="active", party="itso",
            document_pause_started_at=None, resubmission_requests=Mock(), extensions=Mock(),
        )
        assignment.resubmission_requests.filter.return_value.exists.return_value = False
        assignment.extensions.all.return_value = []
        for when, overdue in [(due.replace(hour=8), False), (due, False), (due.replace(second=1), True)]:
            with patch("apps.reviews.deadlines.timezone.now", return_value=when):
                self.assertEqual(deadline_payload(assignment)["is_overdue"], overdue)
        assignment.document_pause_started_at = due
        with patch("apps.reviews.deadlines.timezone.now", return_value=due.replace(second=1)):
            self.assertFalse(deadline_payload(assignment)["is_overdue"])
