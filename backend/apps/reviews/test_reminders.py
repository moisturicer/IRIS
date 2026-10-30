"""Reminders and escalation follow the assignment's due date (ADR-043 §7–§8)."""
import threading
from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase

from apps.audit.models import AuditEvent
from apps.documents.models import DocumentRequest
from apps.documents.requests import withdraw_request
from apps.notifications.models import Notification
from apps.records.models import Record, RecordType
from core.enums import (
    AssignmentState, Party, PipelineStatus, RecordTypeName, RoleName, SeatSource, SeatState,
)

from .deadlines import extend
from .models import (
    DeadlineMoment, Holiday, RecordAssignment, RecordClearance, ResubmissionRequest,
    Review, ReviewerSeat, Turnaround,
)
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


class EscalationTests(SeatTestBase):
    """
    §7's Escalation: an overdue office assignment tells that office's
    coordinators, and nothing is decided. ITSO is due Tuesday 30 March.
    """

    def setUp(self):
        Turnaround.objects.create(party=Party.ITSO, working_days=3)
        self.record = self.make_record(adviser=self.adviser)
        self.itso_assignment = RecordAssignment.objects.create(
            record=self.record, party=Party.ITSO, opened_at=at(3, 25),
        )

    def sent(self, user):
        return list(Notification.objects.filter(recipient=user)
                    .values_list("notif_type__name", flat=True))

    def test_first_working_day_overdue_tells_the_coordinator_once(self):
        self.seat(self.itso_assignment, self.itso)
        run_deadline_notifications(at(3, 30, 23))
        for when in (at(3, 31), at(3, 31, 15), at(4, 1)):
            run_deadline_notifications(when)
        self.assertEqual(self.sent(self.itso_coordinator), ["Review Overdue"])
        note = Notification.objects.get(recipient=self.itso_coordinator)
        self.assertEqual(note.record, self.record)
        self.assertEqual(
            note.message,
            f'ITSO review of "{self.record.title}" is 1 working day overdue. '
            f"Reviewer: {self.itso.get_full_name()}.",
        )

    def test_repeats_every_five_working_days_and_catches_up_only_latest(self):
        self.seat(self.itso_assignment, self.itso)
        for when in (at(3, 31), at(4, 2), at(4, 5), at(4, 6), at(4, 7), at(4, 7, 15)):
            run_deadline_notifications(when)
        self.assertEqual(self.sent(self.itso_coordinator), ["Review Overdue"] * 2)
        self.assertEqual(list(DeadlineMoment.objects.filter(kind="escalation")
                              .order_by("step").values_list("step", flat=True)), [0, 1])
        # The scheduler missed steps 2 and 3; it owes only step 4 now.
        run_deadline_notifications(at(4, 28))
        run_deadline_notifications(at(4, 28, 15))
        self.assertEqual(self.sent(self.itso_coordinator), ["Review Overdue"] * 3)
        self.assertEqual(list(DeadlineMoment.objects.filter(kind="escalation")
                              .order_by("step").values_list("step", flat=True)), [0, 1, 4])

    def test_unclaimed_pool_notifies_all_active_coordinators_only(self):
        self.itso2.is_office_coordinator = True
        self.itso2.save(update_fields=["is_office_coordinator"])
        run_deadline_notifications(at(3, 31))
        self.assertEqual(self.sent(self.itso_coordinator), ["Review Overdue"])
        self.assertEqual(self.sent(self.itso2), ["Review Overdue"])
        self.assertEqual(self.sent(self.itso), [])
        self.assertEqual(self.sent(self.ierc_coordinator), [])
        self.assertIn("Reviewer: unclaimed.", Notification.objects.get(recipient=self.itso2).message)

    def test_missing_coordinator_warns_and_falls_back_to_rdco_coordinators(self):
        self.itso_coordinator.is_active = False
        self.itso_coordinator.save(update_fields=["is_active"])
        coordinator = make_user("escalation-rdco@cit.edu", RoleName.RDCO)
        coordinator.is_office_coordinator = True
        coordinator.save(update_fields=["is_office_coordinator"])
        with self.assertLogs("apps.reviews.reminders", "WARNING") as logs:
            run_deadline_notifications(at(3, 31))
        self.assertIn("escalating to RDCO", logs.output[0])
        self.assertEqual(self.sent(coordinator), ["Review Overdue"])
        self.assertEqual(self.sent(self.rdco), [])
        self.assertEqual(self.sent(self.itso_coordinator), [])

    def test_missing_rdco_coordinator_logs_without_recursion(self):
        self.itso_assignment.state = AssignmentState.COMPLETED
        self.itso_assignment.save(update_fields=["state"])
        Turnaround.objects.create(party=Party.RDCO, working_days=3)
        RecordAssignment.objects.create(record=self.record, party=Party.RDCO, opened_at=at(3, 25))
        with self.assertLogs("apps.reviews.reminders", "WARNING"):
            run_deadline_notifications(at(3, 31))
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(AuditEvent.objects.filter(event_type=AuditEvent.ASSIGNMENT_ESCALATED).count(), 1)

    def test_adviser_never_escalates(self):
        self.itso_assignment.state = AssignmentState.COMPLETED
        self.itso_assignment.save(update_fields=["state"])
        Turnaround.objects.create(party=Party.ADVISER, working_days=3)
        RecordAssignment.objects.create(record=self.record, party=Party.ADVISER, opened_at=at(3, 25))
        for when in (at(3, 31), at(4, 7)):
            self.assertEqual(run_deadline_notifications(when), 0)
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(DeadlineMoment.objects.count(), 0)

    def test_extension_rearms_escalation(self):
        run_deadline_notifications(at(3, 31))
        extend(self.itso_assignment, self.itso_coordinator,
               due_at=datetime(2027, 4, 6, 23, 59, tzinfo=MANILA), reason="Office closure")
        run_deadline_notifications(at(4, 7))
        run_deadline_notifications(at(4, 7, 15))
        self.assertEqual(self.sent(self.itso_coordinator), ["Review Overdue"] * 2)

    def test_weekends_and_holidays_do_not_advance_escalation(self):
        Holiday.objects.create(date=date(2027, 3, 31), name="Campus closure")
        run_deadline_notifications(at(3, 31))
        self.assertEqual(self.sent(self.itso_coordinator), [])
        for when in (at(4, 1), at(4, 3), at(4, 4), at(4, 7)):
            run_deadline_notifications(when)
        self.assertEqual(self.sent(self.itso_coordinator), ["Review Overdue"])
        run_deadline_notifications(at(4, 8))
        self.assertEqual(self.sent(self.itso_coordinator), ["Review Overdue"] * 2)

    def test_paused_completed_and_undated_assignments_do_not_escalate(self):
        DocumentRequest.objects.create(record=self.record, assignment=self.itso_assignment,
                                       party=Party.ITSO, message="Consent form")
        RecordAssignment.objects.create(record=self.record, party=Party.IERC, opened_at=at(3, 25))
        self.assertEqual(run_deadline_notifications(at(3, 31)), 0)
        self.itso_assignment.state = AssignmentState.COMPLETED
        self.itso_assignment.save(update_fields=["state"])
        self.assertEqual(run_deadline_notifications(at(4, 7)), 0)
        self.assertEqual(Notification.objects.count(), 0)

    def test_escalation_records_audit_without_changing_workflow_or_clearances_or_seats(self):
        self.seat(self.itso_assignment, self.itso)
        RecordClearance.objects.create(record=self.record, office=Party.ITSO)
        RecordClearance.objects.create(record=self.record, office=Party.IERC, status="cleared")
        record_before = Record.objects.values().get(pk=self.record.pk)
        assignment_before = RecordAssignment.objects.values().get(pk=self.itso_assignment.pk)
        seats_before = list(ReviewerSeat.objects.values())
        clearances_before = list(RecordClearance.objects.values())
        run_deadline_notifications(at(3, 31))
        run_deadline_notifications(at(3, 31, 15))
        event = AuditEvent.objects.get(event_type=AuditEvent.ASSIGNMENT_ESCALATED)
        self.assertIsNone(event.user)
        self.assertEqual(event.record, self.record)
        self.assertEqual(event.metadata, {
            "assignment": self.itso_assignment.pk, "party": "itso",
            "due_at": self.itso_assignment.due_at.astimezone(ZoneInfo("UTC")).isoformat(),
            "step": 0, "overdue_working_days": 1, "recipients": [self.itso_coordinator.pk],
        })
        self.assertEqual(Record.objects.values().get(pk=self.record.pk), record_before)
        self.assertEqual(RecordAssignment.objects.values().get(pk=self.itso_assignment.pk), assignment_before)
        self.assertEqual(list(ReviewerSeat.objects.values()), seats_before)
        self.assertEqual(list(RecordClearance.objects.values()), clearances_before)

    def test_audit_failure_rolls_back_moment_and_allows_retry(self):
        with patch.object(AuditEvent.objects, "create", side_effect=RuntimeError("audit unavailable")), \
                self.assertLogs("apps.reviews.reminders", "ERROR"):
            self.assertEqual(run_deadline_notifications(at(3, 31)), 0)
        self.assertEqual(DeadlineMoment.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(run_deadline_notifications(at(3, 31)), 1)
        self.assertEqual(self.sent(self.itso_coordinator), ["Review Overdue"])

    def test_revision_request_suppresses_escalation(self):
        review = Review.objects.create(record=self.record, reviewed_by=self.itso, stage=Party.ITSO,
                                        status="declined", assignment=self.itso_assignment)
        ResubmissionRequest.objects.create(record=self.record, assignment=self.itso_assignment,
                                           party=Party.ITSO, requested_by=self.itso, reason="Revise", review=review)
        self.assertEqual(run_deadline_notifications(at(3, 31)), 0)
        self.assertEqual(Notification.objects.count(), 0)

    def test_document_pause_moves_date_and_rearms_escalation(self):
        run_deadline_notifications(at(3, 31))
        with patch("django.utils.timezone.now", return_value=at(3, 31)):
            request = DocumentRequest.objects.create(record=self.record, assignment=self.itso_assignment,
                                                     party=Party.ITSO, message="Consent form")
        self.assertEqual(run_deadline_notifications(at(4, 1)), 0)
        with patch("django.utils.timezone.now", return_value=at(4, 1)):
            withdraw_request(request, self.itso)
        self.itso_assignment.refresh_from_db()
        self.assertEqual(self.itso_assignment.due_at, datetime(2027, 3, 31, 23, 59, tzinfo=MANILA))
        run_deadline_notifications(at(4, 1))
        self.assertEqual(self.sent(self.itso_coordinator), ["Review Overdue"] * 2)

    def test_unreadable_record_is_not_named_in_escalation(self):
        # The visibility policy is the database boundary. Office staff can
        # currently see everything; exercise a narrowed policy as §7 requires.
        with patch.object(Record.objects, "visible_to", return_value=Record.objects.none()):
            run_deadline_notifications(at(3, 31))
        self.assertEqual(Notification.objects.count(), 0)
        event = AuditEvent.objects.get(event_type=AuditEvent.ASSIGNMENT_ESCALATED)
        self.assertEqual(event.metadata["recipients"], [])


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
        self.simultaneous_runs(at(3, 26), escalation=False)

    def test_two_simultaneous_escalations_write_one_notification_and_audit(self):
        self.simultaneous_runs(at(3, 31), escalation=True)

    def simultaneous_runs(self, when, *, escalation):
        Turnaround.objects.create(party=Party.ITSO, working_days=3)
        owner = make_user("race-owner@cit.edu", RoleName.STUDENT)
        reviewer = make_user("race-itso@cit.edu", RoleName.ITSO)
        if escalation:
            reviewer.is_office_coordinator = True
            reviewer.save(update_fields=["is_office_coordinator"])
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
                results.append(run_deadline_notifications(when))
            finally:
                connection.close()

        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), [0, 1])
        self.assertEqual(Notification.objects.filter(recipient=reviewer).count(), 1)
        if escalation:
            self.assertEqual(AuditEvent.objects.filter(event_type=AuditEvent.ASSIGNMENT_ESCALATED).count(), 1)
