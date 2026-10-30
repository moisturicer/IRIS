"""IR-473: the document-access PIN ceremony is gone, and its history is not.

IR-635 made PIN generation respect Record visibility. IR-473 removes the
ceremony instead, because verifying a PIN unlocked nothing. These tests
replace IR-635's, which exercised the endpoint that no longer exists.
"""
import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import NoReverseMatch, reverse
from rest_framework.test import APITestCase

from apps.audit.models import AuditEvent
from apps.records.models import Record, RecordOwner
from apps.tests.test_authorization_matrix import make_user


@pytest.mark.db_required
class PinRemovedTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = make_user("pin-owner@cit.edu", "Student")
        cls.record = Record.objects.create(title="Former PIN canary", pipeline_status="draft")
        RecordOwner.objects.create(record=cls.record, user=cls.owner, is_primary=True)

    def test_both_routes_are_gone(self):
        self.client.force_authenticate(self.owner)
        for path, body in (
            ("/api/v1/reviews/pin/generate/", {"record_id": self.record.pk}),
            ("/api/v1/reviews/pin/verify/", {"record_id": self.record.pk, "pin": "ABC123"}),
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, body, format="json").status_code, 404)
        for name in ("pin-generate", "pin-verify"):
            with self.subTest(name=name), self.assertRaises(NoReverseMatch):
                reverse(name)

    def test_audit_rows_of_the_pin_types_still_display(self):
        for event_type, label in (
            (AuditEvent.PIN_GENERATED, "PIN Generated"),
            (AuditEvent.PIN_VERIFIED, "PIN Verified"),
        ):
            with self.subTest(event_type=event_type):
                event = AuditEvent.objects.create(
                    event_type=event_type, user=self.owner, record=self.record,
                )
                event.refresh_from_db()
                self.assertEqual(event.get_event_type_display(), label)


_BEFORE = [("reviews", "0019_merge_deadline_moment_and_seat_reassignment")]
_AFTER = [("reviews", "0020_delete_recordauthpin")]


@pytest.mark.db_required
@pytest.mark.django_db(transaction=True)
def test_the_table_drops_over_existing_pin_rows():
    """The migration applies to a database that still holds PINs."""
    executor = MigrationExecutor(connection)
    old_apps = executor.loader.project_state(_BEFORE).apps
    executor.migrate(_BEFORE)
    try:
        owner = make_user("pin-migration@cit.edu", "Student")
        record = Record.objects.create(title="Had PINs", pipeline_status="draft")
        OldPin = old_apps.get_model("reviews", "RecordAuthPin")
        OldPin.objects.create(record_id=record.pk, user_id=owner.pk, email=owner.email, pin="ABC123")
        OldPin.objects.create(
            record_id=record.pk, user_id=owner.pk, email=owner.email, pin="XYZ789", is_used=True,
        )
        assert "reviews_recordauthpin" in connection.introspection.table_names()

        executor = MigrationExecutor(connection)
        executor.migrate(_AFTER)

        assert "reviews_recordauthpin" not in connection.introspection.table_names()
        assert Record.objects.filter(pk=record.pk).exists()
    finally:
        call_command("migrate", verbosity=0)
