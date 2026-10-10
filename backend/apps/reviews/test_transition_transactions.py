"""The adviser-first API commits routing and decisions as a unit (IR-260)."""

from unittest.mock import patch

from django.db import transaction
from rest_framework import status

from apps.audit.models import AuditEvent
from apps.notifications.models import Notification
from apps.reviews.models import RecordAssignment, Review, RoutingEvent
from core.enums import Party, PipelineStatus, RecordTypeName

from .test_decisions import DecisionTestBase


class TransitionTransactionTests(DecisionTestBase):
    def counts(self, record):
        return (
            list(RecordAssignment.objects.filter(record=record).values_list("party", "state")),
            Review.objects.filter(record=record).count(),
            RoutingEvent.objects.filter(record=record).count(),
            AuditEvent.objects.filter(record=record).count(),
            Notification.objects.filter(record=record).count(),
        )

    def test_accept_and_route_rolls_back_with_its_notifications(self):
        record = self.new_model(RecordTypeName.THESIS_RESEARCH)
        before = self.counts(record)
        with patch("apps.accounts.tasks.send_email_task.delay") as send_email:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with self.assertRaisesRegex(RuntimeError, "outer rollback"):
                    with transaction.atomic():
                        response = self.accept(record, [{"party": Party.ITSO}])
                        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
                        self.assertEqual(Notification.objects.filter(record=record).count(), before[-1])
                        raise RuntimeError("outer rollback")
            self.assertEqual(callbacks, [])
            send_email.assert_not_called()
        self.assertEqual(self.counts(record), before)
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)

    def test_publish_rolls_back_its_review_and_notification(self):
        record = self.at_adviser()
        before = self.counts(record)
        with patch("apps.accounts.tasks.send_email_task.delay") as send_email:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with self.assertRaisesRegex(RuntimeError, "outer rollback"):
                    with transaction.atomic():
                        response = self.decide(record, self.adviser, "publish")
                        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
                        self.assertEqual(Notification.objects.filter(record=record).count(), before[-1])
                        raise RuntimeError("outer rollback")
            self.assertEqual(callbacks, [])
            send_email.assert_not_called()
        self.assertEqual(self.counts(record), before)
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)
