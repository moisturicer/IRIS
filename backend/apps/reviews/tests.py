"""
Tests for apps.reviews.services — the sequential/clearance state machine.

Run with (see apps/records/tests.py docstring for why the dotted path matters):
    docker compose exec -T backend python manage.py test apps.reviews.tests

Covers ADR-016 (Proposed): conditional parallel-office routing. Before this,
approve_record() created a hardcoded clearance set per record_type
(Project -> ITSO+KTTO, Thesis/Research -> IERC+KTTO). These tests lock in the
new behaviour: the office set comes from what the submitter (and, eventually,
RDCO) actually requested, and the pipeline status computed from what's real
rather than assumed from the type alone.
"""
from django.test import TestCase

from apps.accounts.models import Role, User
from apps.records.models import Record, RecordOwner, RecordType
from .models import RecordClearance
from .services import approve_record, submit_clearance


def make_user(email, role_name):
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="pw12345!", first_name="Test", last_name="User",
        role=role, is_verified=True,
    )


class ApproveRecordConditionalOfficesTests(TestCase):
    def setUp(self):
        self.thesis  = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        self.project = RecordType.objects.get_or_create(name="Project")[0]
        self.owner   = make_user("owner@cit.edu", "Student")
        self.rdco    = make_user("rdco@cit.edu", "RDCO")

    def _record(self, record_type, **flags):
        record = Record.objects.create(
            title="A" * 10, abstract="B" * 40, record_type=record_type,
            added_by=self.owner, pipeline_status="rdco_intake", **flags,
        )
        RecordOwner.objects.create(record=record, user=self.owner, is_primary=True)
        return record

    def offices(self, record):
        return set(RecordClearance.objects.filter(record=record).values_list("office", flat=True))

    def test_thesis_requesting_only_ktto(self):
        record = self._record(self.thesis, requested_ktto=True)
        approve_record(record, self.rdco)
        record.refresh_from_db()
        self.assertEqual(self.offices(record), {"ktto"})
        self.assertEqual(record.pipeline_status, "parallel_review")

    def test_thesis_requesting_nothing_skips_straight_to_rdco_review(self):
        record = self._record(self.thesis)
        approve_record(record, self.rdco)
        record.refresh_from_db()
        self.assertEqual(self.offices(record), set())
        self.assertEqual(record.pipeline_status, "rdco_review")

    def test_thesis_requesting_itso_is_ignored(self):
        """Thesis/Research structurally never routes through ITSO."""
        record = self._record(self.thesis, requested_itso=True, requested_ktto=True)
        approve_record(record, self.rdco)
        record.refresh_from_db()
        self.assertEqual(self.offices(record), {"ktto"})
        self.assertEqual(record.pipeline_status, "parallel_review")

    def test_project_requesting_itso_only_then_clearing_it_goes_straight_to_rdco_review(self):
        record = self._record(self.project, requested_itso=True)
        approve_record(record, self.rdco)
        record.refresh_from_db()
        self.assertEqual(self.offices(record), {"itso"})
        self.assertEqual(record.pipeline_status, "itso_review")

        itso_user = make_user("itso@cit.edu", "ITSO")
        submit_clearance(record, itso_user, "itso", "approved")
        record.refresh_from_db()
        # Neither IERC nor KTTO was requested -- nothing left pending.
        self.assertEqual(self.offices(record), {"itso"})
        self.assertEqual(record.pipeline_status, "rdco_review")

    def test_project_requesting_itso_and_ktto_clearing_itso_leaves_ktto_pending(self):
        record = self._record(self.project, requested_itso=True, requested_ktto=True)
        approve_record(record, self.rdco)
        record.refresh_from_db()
        self.assertEqual(self.offices(record), {"itso", "ktto"})
        self.assertEqual(record.pipeline_status, "itso_review")

        itso_user = make_user("itso2@cit.edu", "ITSO")
        submit_clearance(record, itso_user, "itso", "approved")
        record.refresh_from_db()
        # IERC was never requested, so clearing ITSO must NOT create one --
        # that was the old unconditional behaviour this replaces.
        self.assertEqual(self.offices(record), {"itso", "ktto"})
        self.assertEqual(record.pipeline_status, "parallel_review")

    def test_project_skipping_itso_entirely_goes_straight_to_parallel_review(self):
        record = self._record(self.project, requested_ierc=True, requested_ktto=True)
        approve_record(record, self.rdco)
        record.refresh_from_db()
        self.assertEqual(self.offices(record), {"ierc", "ktto"})
        # itso_review would be a stage with nothing to review -- skip it.
        self.assertEqual(record.pipeline_status, "parallel_review")
