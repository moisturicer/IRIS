"""IR-138: HTTP decisions commit as a unit and notify only after commit.

Database assertions observe durable workflow state. Failure injection at a
database write is deliberate: HTTP has no way to request a mid-transition error.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from time import monotonic
from unittest.mock import patch

from django.db import connections, transaction
from django.db.models.signals import post_save
from rest_framework.test import APIClient, APITransactionTestCase

from apps.audit.models import AuditEvent
from apps.notifications.models import Notification
from apps.records.models import Record, RecordOwner, RecordType
from apps.reviews.models import RecordClearance, Review
from apps.reviews import shadow
from apps.reviews.test_shadow_assignments import shadow_rows
from apps.reviews.test_workflow_characterisation import (
    SUBMIT_REVIEW, WorkflowCharacterisationBase, make_user,
)
from core.enums import (
    ClearanceStatus, Office, PipelineStatus, RecordTypeName, ReviewDecision, RoleName,
)


class TransitionNotificationTests(WorkflowCharacterisationBase):
    def test_review_notifies_only_after_the_enclosing_transaction_commits(self):
        record = self.make_record(
            RecordTypeName.PROPOSAL,
            pipeline_status=PipelineStatus.ADVISER_REVIEW,
            adviser=self.adviser,
        )
        before = Notification.objects.count()
        with patch("apps.accounts.tasks.send_email_task.delay") as send_email:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with transaction.atomic():
                    response = self.review(record, self.adviser, ReviewDecision.APPROVED)
                    self.assertEqual(response.status_code, 201, response.data)
                    self.assertEqual(Notification.objects.count(), before)
                    send_email.assert_not_called()
            self.assertTrue(callbacks)
            self.assertGreater(Notification.objects.count(), before)
            self.assertTrue(send_email.called)

    def prepared_action(self, action):
        record = self.make_record(
            RecordTypeName.PROPOSAL,
            pipeline_status=PipelineStatus.ADVISER_REVIEW,
            adviser=self.adviser,
        )
        if action == "resubmit":
            self.assertEqual(
                self.review(record, self.adviser, ReviewDecision.DECLINED).status_code,
                201,
            )
            # Only the timestamp/existence is relevant to the resubmit guard;
            # avoid writing an upload file to the developer's media directory.
            from apps.documents.models import RecordUpload, UploadSlot
            slot = UploadSlot.objects.create(name="Revised", record_type=record.record_type)
            RecordUpload.objects.create(
                record=record, slot=slot, file="tests/revised.pdf", uploaded_by=self.owner,
            )
            return record, lambda: self.resubmit(record), 200
        if action.startswith("clearance"):
            record.pipeline_status = PipelineStatus.PARALLEL_REVIEW
            record.record_type = self.record_type(RecordTypeName.PROJECT)
            record.save()
            RecordClearance.objects.create(record=record, office=Office.KTTO)
            decision = (
                ReviewDecision.DECLINED if action == "clearance_decline"
                else ReviewDecision.APPROVED
            )
            return record, lambda: self.review(record, self.ktto, decision), 201
        return record, lambda: self.review(record, self.adviser, action), 201

    def test_each_action_defers_notification_until_commit(self):
        for action in ("declined", "rejected", "clearance", "clearance_decline", "resubmit"):
            with self.subTest(action=action):
                record, act, expected = self.prepared_action(action)
                before = Notification.objects.count()
                with patch("apps.accounts.tasks.send_email_task.delay") as send_email:
                    with self.captureOnCommitCallbacks(execute=True) as callbacks:
                        response = act()
                        self.assertEqual(response.status_code, expected, response.data)
                        self.assertEqual(Notification.objects.count(), before)
                        send_email.assert_not_called()
                    self.assertTrue(callbacks)
                    self.assertGreater(Notification.objects.count(), before)
                    self.assertTrue(send_email.called)

    def test_outer_rollback_discards_every_action_and_its_notifications(self):
        for action in ("approved", "declined", "rejected", "clearance", "resubmit"):
            with self.subTest(action=action):
                record, act, expected = self.prepared_action(action)
                before = self.persisted_state(record)
                with patch("apps.accounts.tasks.send_email_task.delay") as send_email:
                    with self.captureOnCommitCallbacks(execute=True) as callbacks:
                        with self.assertRaisesRegex(RuntimeError, "outer rollback"):
                            with transaction.atomic():
                                response = act()
                                self.assertEqual(response.status_code, expected, response.data)
                                raise RuntimeError("outer rollback")
                    self.assertEqual(callbacks, [])
                    send_email.assert_not_called()
                self.assertEqual(self.persisted_state(record), before)

    def persisted_state(self, record):
        return (
            Record.objects.filter(pk=record.pk).values().get(),
            list(Review.objects.filter(record=record).values()),
            list(RecordClearance.objects.filter(record=record).values()),
            shadow_rows(),
            list(AuditEvent.objects.values()),
            list(Notification.objects.values()),
        )

    def test_failure_after_transition_writes_rolls_back_every_action(self):
        sync = shadow.sync

        def fail_after_writes(*args, **kwargs):
            sync(*args, **kwargs)
            raise RuntimeError("failed routing write")

        for action in ("approved", "declined", "rejected", "clearance", "resubmit"):
            with self.subTest(action=action):
                record, act, _ = self.prepared_action(action)
                before = self.persisted_state(record)
                with patch("apps.accounts.tasks.send_email_task.delay") as send_email:
                    with self.captureOnCommitCallbacks(execute=True) as callbacks:
                        with patch(
                            "apps.reviews.shadow.sync", side_effect=fail_after_writes,
                        ):
                            with self.assertRaisesRegex(RuntimeError, "failed routing"):
                                act()
                    self.assertEqual(callbacks, [])
                    send_email.assert_not_called()
                self.assertEqual(self.persisted_state(record), before)

    def test_failure_between_clearance_inserts_leaves_neither_office(self):
        record = self.make_record(
            RecordTypeName.PROJECT, pipeline_status=PipelineStatus.RDCO_INTAKE,
            requested_ierc=True, requested_ktto=True,
        )
        before = self.persisted_state(record)

        def fail_after_first_clearance(sender, instance, created, **kwargs):
            if created and instance.record_id == record.pk:
                raise RuntimeError("first clearance inserted")

        post_save.connect(fail_after_first_clearance, sender=RecordClearance)
        try:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with self.assertRaisesRegex(RuntimeError, "first clearance"):
                    self.review(record, self.rdco, ReviewDecision.APPROVED)
            self.assertEqual(callbacks, [])
        finally:
            post_save.disconnect(fail_after_first_clearance, sender=RecordClearance)
        self.assertEqual(self.persisted_state(record), before)


class ConcurrentDecisionTests(APITransactionTestCase):
    """Independent PostgreSQL connections, with both HTTP requests in flight.

    TransactionTestCase is essential: TestCase hides fixtures in an uncommitted
    transaction. Synchronize the initial HTTP reads, not the service internals.
    """

    def setUp(self):
        self.owner = make_user("atomic-owner@cit.edu", RoleName.STUDENT)
        self.ierc = make_user("atomic-ierc@cit.edu", RoleName.IERC)
        self.ktto = make_user("atomic-ktto@cit.edu", RoleName.KTTO)
        self.record = Record.objects.create(
            title="Concurrent office decisions", abstract="A" * 40,
            added_by=self.owner,
            record_type=RecordType.objects.get_or_create(name=RecordTypeName.PROJECT)[0],
            pipeline_status=PipelineStatus.PARALLEL_REVIEW,
            requested_ierc=True, requested_ktto=True,
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)
        for office in (Office.IERC, Office.KTTO):
            RecordClearance.objects.create(record=self.record, office=office)

    def decisions_together(self, users):
        barrier = Barrier(2, timeout=15)

        def decide(user):
            connection = connections["default"]
            synchronized = False

            def synchronize_read(execute, sql, params, many, context):
                nonlocal synchronized
                result = execute(sql, params, many, context)
                if not synchronized and sql.startswith("SELECT") and 'FROM "records_record"' in sql:
                    synchronized = True
                    barrier.wait()
                return result

            try:
                client = APIClient()
                client.force_authenticate(user)
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '10s'")
                with connection.execute_wrapper(synchronize_read):
                    response = client.post(SUBMIT_REVIEW, {
                        "record_id": self.record.pk, "status": ReviewDecision.APPROVED,
                    }, format="json")
                return response.status_code
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(decide, user) for user in users]
            return sorted(future.result(timeout=30) for future in futures)

    def test_two_offices_clear_without_losing_the_final_advance(self):
        self.assertEqual(self.decisions_together([self.ierc, self.ktto]), [201, 201])
        self.record.refresh_from_db()
        self.assertEqual(self.record.pipeline_status, PipelineStatus.RDCO_REVIEW)
        self.assertEqual(Review.objects.filter(record=self.record).count(), 2)
        self.assertEqual(
            list(RecordClearance.objects.filter(record=self.record).values_list("status", flat=True)),
            [ClearanceStatus.CLEARED, ClearanceStatus.CLEARED],
        )

    def test_duplicate_office_decisions_record_only_one_review(self):
        self.assertEqual(self.decisions_together([self.ierc, self.ierc]), [201, 400])
        self.assertEqual(Review.objects.filter(record=self.record).count(), 1)
        self.record.refresh_from_db()
        self.assertEqual(self.record.pipeline_status, PipelineStatus.PARALLEL_REVIEW)

    def test_decision_waits_for_record_lock_then_rechecks_the_stage(self):
        read = Event()
        backend_pid = []

        def decide():
            connection = connections["default"]

            def signal_read(execute, sql, params, many, context):
                result = execute(sql, params, many, context)
                if sql.startswith("SELECT") and 'FROM "records_record"' in sql:
                    read.set()
                return result

            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '10s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    backend_pid.append(cursor.fetchone()[0])
                client = APIClient()
                client.force_authenticate(self.ierc)
                with connection.execute_wrapper(signal_read):
                    return client.post(SUBMIT_REVIEW, {
                        "record_id": self.record.pk, "status": ReviewDecision.APPROVED,
                    }, format="json").status_code
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                Record.objects.select_for_update().get(pk=self.record.pk)
                future = pool.submit(decide)
                self.assertTrue(read.wait(5), "HTTP request did not read the record")
                deadline = monotonic() + 5
                blocked = False
                while monotonic() < deadline and not future.done():
                    with connections["default"].cursor() as cursor:
                        cursor.execute(
                            "SELECT pg_backend_pid() = ANY(pg_blocking_pids(%s))",
                            [backend_pid[0]],
                        )
                        blocked = cursor.fetchone()[0]
                    if blocked:
                        break
                    Event().wait(0.01)
                self.assertTrue(blocked, "Decision did not wait for the record lock")
                Record.objects.filter(pk=self.record.pk).update(
                    pipeline_status=PipelineStatus.DECLINED,
                )
            self.assertEqual(future.result(timeout=15), 400)
        self.assertFalse(Review.objects.filter(record=self.record).exists())
        self.assertEqual(
            RecordClearance.objects.filter(
                record=self.record, status=ClearanceStatus.PENDING,
            ).count(), 2,
        )
