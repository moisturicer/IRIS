"""
IR-762: a request whose paper deadline passes is deleted, and its Adviser is
told once (ADR-050 decision 9, as amended 2026-11-15).
"""
from datetime import date, datetime, timezone as dt_timezone
from unittest.mock import patch

from django.test import TestCase

from apps.notifications.models import Notification

from .models import Opportunity
from .tasks import remove_lapsed_requests
from .tests import make_opportunity, make_user

#: 00:30 on 2026-11-16 in Manila, while it is still the 15th in UTC.
JUST_AFTER_MIDNIGHT_16TH_MANILA = datetime(2026, 11, 15, 16, 30, tzinfo=dt_timezone.utc)


def nov(day):
    return date(2026, 11, day)


class RemoveLapsedRequestsTests(TestCase):
    def setUp(self):
        self.adviser = make_user("adviser@cit.edu", "Adviser")
        clock = patch("django.utils.timezone.now", return_value=JUST_AFTER_MIDNIGHT_16TH_MANILA)
        clock.start()
        self.addCleanup(clock.stop)

    def call(self, title, due, status, **extra):
        return make_opportunity(title=title, due_date=due, status=status, posted_by=self.adviser, **extra)

    def lapse_notices(self):
        return list(
            Notification.objects.filter(recipient=self.adviser, notif_type__name="Call Request Lapsed")
            .values_list("message", flat=True)
        )

    def test_waiting_and_rejected_requests_past_their_deadline_are_deleted(self):
        self.call("Waiting, due the 15th", nov(15), "pending")
        self.call("Rejected, due the 15th", nov(15), "rejected", review_reason="Broken link")
        self.call("Waiting, due the 16th", nov(16), "pending")
        self.call("Confirmed, due the 15th", nov(15), "confirmed", start_date=nov(20))

        with self.captureOnCommitCallbacks(execute=True):
            removed = remove_lapsed_requests()

        self.assertEqual(removed, 2)
        self.assertEqual(
            set(Opportunity.objects.values_list("title", flat=True)),
            {"Waiting, due the 16th", "Confirmed, due the 15th"},
        )
        self.assertEqual(sorted(self.lapse_notices()), [
            'Your call "Rejected, due the 15th" was removed because its paper deadline '
            "passed before it was confirmed. You may post a new one.",
            'Your call "Waiting, due the 15th" was removed because its paper deadline '
            "passed before it was confirmed. You may post a new one.",
        ])

    def test_a_second_run_sends_no_second_notice(self):
        self.call("Waiting, due the 15th", nov(15), "pending")
        with self.captureOnCommitCallbacks(execute=True):
            remove_lapsed_requests()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(remove_lapsed_requests(), 0)
        self.assertEqual(len(self.lapse_notices()), 1)

    def test_a_request_whose_poster_is_gone_is_deleted_with_no_notice(self):
        make_opportunity(title="Orphan", due_date=nov(15), status="pending", posted_by=None)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(remove_lapsed_requests(), 1)
        self.assertFalse(Notification.objects.filter(notif_type__name="Call Request Lapsed").exists())


class ScheduleTests(TestCase):
    def test_beat_runs_it_daily_just_after_midnight_in_manila(self):
        from django.conf import settings

        from config.celery import app

        entry = settings.CELERY_BEAT_SCHEDULE["lapsed-call-requests"]
        self.assertEqual(entry["task"], "apps.opportunities.tasks.remove_lapsed_requests")
        self.assertIn(entry["task"], app.tasks)
        self.assertEqual(str(app.timezone), "Asia/Manila")
        self.assertEqual((entry["schedule"].hour, entry["schedule"].minute), ({0}, {15}))
