"""Reminders and escalation follow the assignment's due date (ADR-043 §7–§8)."""
import threading
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase

from apps.documents.models import DocumentRequest
from apps.notifications.models import Notification
from apps.records.models import Record, RecordType
from core.enums import (
    AssignmentState, Party, PipelineStatus, RecordTypeName, RoleName, SeatSource, SeatState,
)

from .deadlines import extend
from .models import DeadlineMoment, RecordAssignment, ReviewerSeat, Turnaround
from .reminders import run_deadline_notifications
from .test_seats import SeatTestBase
from .workflow_test_helpers import make_user

MANILA = ZoneInfo("Asia/Manila")


def at(month, day, hour=9):
    return datetime(2027, month, day, hour, tzinfo=MANILA)


class ReminderTests(SeatTestBase):
    """ITSO's Turnaround is 3, opened Thursday 25 March: due Tuesday 30 March."""

    def setUp(self):
        Turnaround.objects.create(party=Party.ITSO, working_days=3)
        self.record = self.make_record(adviser=self.adviser)
        self.itso_assignment = RecordAssignment.objects.create(
            record=self.record, party=Party.ITSO, opened_at=at(3, 25),
        )

    def sent(self, user):
        return list(Notification.objects.filter(recipient=user)
                    .values_list("notif_type__name", flat=True))

    def test_seat_holder_is_told_two_working_days_before(self):
        self.seat(self.itso_assignment, self.itso)
        run_deadline_notifications(at(3, 25))
        self.assertEqual(self.sent(self.itso), [])
        run_deadline_notifications(at(3, 26))
        self.assertEqual(self.sent(self.itso), ["Review Due Soon"])

    def test_due_today_follows_and_each_moment_is_sent_once(self):
        self.seat(self.itso_assignment, self.itso)
        for when in (at(3, 26), at(3, 26, 10), at(3, 29), at(3, 30), at(3, 30, 23)):
            run_deadline_notifications(when)
        self.assertEqual(sorted(self.sent(self.itso)), ["Review Due Soon", "Review Due Today"])
        self.assertEqual(DeadlineMoment.objects.count(), 2)

    def test_unclaimed_pool_goes_to_coordinators_and_a_later_claim_is_not_told_again(self):
        run_deadline_notifications(at(3, 26))
        self.assertEqual(self.sent(self.itso_coordinator), ["Review Due Soon"])
        self.assertEqual(self.sent(self.ierc_coordinator), [])
        self.seat(self.itso_assignment, self.itso)
        run_deadline_notifications(at(3, 29))
        self.assertEqual(self.sent(self.itso), [])
        run_deadline_notifications(at(3, 30))
        self.assertEqual(self.sent(self.itso), ["Review Due Today"])

    def test_done_withdrawn_and_completed_get_nothing(self):
        self.seat(self.itso_assignment, self.itso, state=SeatState.DONE)
        self.seat(self.itso_assignment, self.itso2, state=SeatState.WITHDRAWN)
        run_deadline_notifications(at(3, 26))
        self.assertEqual(Notification.objects.count(), 0)
        self.itso_assignment.state = AssignmentState.COMPLETED
        self.itso_assignment.save(update_fields=["state"])
        run_deadline_notifications(at(3, 30))
        self.assertEqual(Notification.objects.count(), 0)

    def test_catch_up_skips_a_superseded_reminder(self):
        self.seat(self.itso_assignment, self.itso)
        run_deadline_notifications(at(3, 30))
        self.assertEqual(self.sent(self.itso), ["Review Due Today"])

    def test_extension_rearms_both_reminders(self):
        self.seat(self.itso_assignment, self.itso)
        run_deadline_notifications(at(3, 26))
        extend(self.itso_assignment, self.itso_coordinator,
               due_at=datetime(2027, 4, 6, 23, 59, tzinfo=MANILA), reason="Office closure")
        run_deadline_notifications(at(3, 30))
        self.assertEqual(self.sent(self.itso), ["Review Due Soon"])
        run_deadline_notifications(at(4, 2))
        run_deadline_notifications(at(4, 6))
        self.assertEqual(sorted(self.sent(self.itso)),
                         ["Review Due Soon", "Review Due Soon", "Review Due Today"])

    def test_paused_clock_gets_nothing(self):
        self.seat(self.itso_assignment, self.itso)
        DocumentRequest.objects.create(record=self.record, assignment=self.itso_assignment,
                                       party=Party.ITSO, message="Consent form")
        run_deadline_notifications(at(3, 26))
        self.assertEqual(self.sent(self.itso), [])

    def test_party_with_no_turnaround_has_no_reminder(self):
        ierc = RecordAssignment.objects.create(record=self.record, party=Party.IERC,
                                               opened_at=at(3, 25))
        self.seat(ierc, self.ierc)
        for day in (26, 29, 30, 31):
            run_deadline_notifications(at(3, day))
        self.assertEqual(self.sent(self.ierc), [])

    def test_adviser_assignment_reminds_the_adviser(self):
        Turnaround.objects.create(party=Party.ADVISER, working_days=3)
        RecordAssignment.objects.create(record=self.record, party=Party.ADVISER,
                                        opened_at=at(3, 25))
        run_deadline_notifications(at(3, 26))
        self.assertEqual(self.sent(self.adviser), ["Review Due Soon"])

    def test_a_recipient_who_cannot_read_the_record_is_skipped(self):
        Turnaround.objects.create(party=Party.ADVISER, working_days=3)
        adviser = RecordAssignment.objects.create(record=self.record, party=Party.ADVISER,
                                                  opened_at=at(3, 25))
        self.seat(adviser, self.other_adviser)
        run_deadline_notifications(at(3, 26))
        self.assertEqual(self.sent(self.other_adviser), [])

    def test_a_failed_notification_is_logged_and_the_batch_continues(self):
        self.seat(self.itso_assignment, self.itso)
        other = self.make_record(adviser=self.adviser)
        second = RecordAssignment.objects.create(record=other, party=Party.ITSO, opened_at=at(3, 25))
        self.seat(second, self.itso2)
        real_create = Notification.objects.create

        def fail_for_itso(**kwargs):
            if kwargs["recipient"] == self.itso:
                raise RuntimeError("delivery failed")
            return real_create(**kwargs)

        with patch.object(Notification.objects, "create", side_effect=fail_for_itso), \
                self.assertLogs("apps.notifications.services", "ERROR"):
            self.assertEqual(run_deadline_notifications(at(3, 26)), 2)
        self.assertEqual(self.sent(self.itso2), ["Review Due Soon"])


class BeatScheduleTests(SimpleTestCase):
    def test_beat_runs_the_deadline_task_hourly_on_a_registered_name(self):
        from celery.schedules import crontab

        from config.celery import app

        entry = settings.CELERY_BEAT_SCHEDULE["deadline-notifications"]
        app.loader.import_default_modules()
        self.assertIn(entry["task"], app.tasks)
        self.assertEqual(entry["schedule"], crontab(minute=0))


class ConcurrentRunTests(TransactionTestCase):
    """Two beat instances firing together send one notification (§8)."""

    def test_two_simultaneous_runs_send_once(self):
        Turnaround.objects.create(party=Party.ITSO, working_days=3)
        owner = make_user("race-owner@cit.edu", RoleName.STUDENT)
        reviewer = make_user("race-itso@cit.edu", RoleName.ITSO)
        record = Record.objects.create(
            title="Race", abstract="A" * 40, added_by=owner,
            record_type=RecordType.objects.get_or_create(name=RecordTypeName.THESIS_RESEARCH)[0],
            pipeline_status=PipelineStatus.IN_REVIEW,
        )
        assignment = RecordAssignment.objects.create(record=record, party=Party.ITSO,
                                                     opened_at=at(3, 25))
        ReviewerSeat.objects.create(assignment=assignment, reviewer=reviewer,
                                    source=SeatSource.CLAIMED)
        barrier = threading.Barrier(2)
        results = []

        def run():
            try:
                barrier.wait()
                results.append(run_deadline_notifications(at(3, 26)))
            finally:
                connection.close()

        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), [0, 1])
        self.assertEqual(Notification.objects.filter(recipient=reviewer).count(), 1)
