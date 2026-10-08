"""The clearance payload, end to end (IR-139).

`test_clearance_state.py` proves the rule. This proves the API actually says
it -- that `preserved` reaches the client and that `resubmission{}` reports
what survived. The review-queue rows these tests also covered were replaced by
My Reviews (IR-268), whose rows are tested in `test_my_reviews.py`.

Run:
    docker compose exec -T backend python manage.py test apps.reviews.test_clearance_payload
"""
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.records.models import Record, RecordOwner, RecordType
from apps.reviews.models import RecordClearance, Review


def make_user(email, role_name=None, **extra):
    role = Role.objects.get_or_create(name=role_name)[0] if role_name else None
    extra.setdefault("is_verified", True)
    return User.objects.create_user(
        email=email, password="pw12345!", first_name="Test", last_name="User",
        role=role, **extra,
    )


class ClearancePayloadTests(APITestCase):
    """What the record detail endpoint states about clearance."""

    def setUp(self):
        self.owner = make_user("owner-139@cit.edu", "Student")
        self.itso = make_user("itso-139@cit.edu", "ITSO")
        # Reference rows are seeded; creating them raises duplicate-pkey.
        self.record = Record.objects.create(
            title="Clearance payload record",
            record_type=RecordType.objects.first(),
            added_by=self.owner,
            pipeline_status="parallel_review",
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)

    def _detail(self):
        self.client.force_authenticate(self.owner)
        return self.client.get(f"/api/v1/records/{self.record.id}/").data

    def test_a_record_with_no_clearances_reports_an_empty_resubmission(self):
        """The shape must exist before anything has happened to it, or the UI
        needs a null branch for the ordinary case."""
        data = self._detail()
        self.assertEqual(data["clearances"], [])
        self.assertEqual(data["resubmission"]["count"], 0)
        self.assertIsNone(data["resubmission"]["last_resubmitted_at"])
        self.assertIsNone(data["resubmission"]["declining_office"])
        self.assertEqual(data["resubmission"]["offices_preserved"], [])

    def test_each_clearance_carries_a_status_label(self):
        """AC: no client-side status->English mapping remains."""
        RecordClearance.objects.create(record=self.record, office="itso", status="cleared")
        RecordClearance.objects.create(record=self.record, office="ierc", status="pending")

        by_office = {c["office"]: c for c in self._detail()["clearances"]}
        self.assertEqual(by_office["itso"]["status_label"], "Cleared")
        self.assertEqual(by_office["ierc"]["status_label"], "Pending")
        self.assertEqual(by_office["itso"]["office_label"], "ITSO")

    def test_nothing_is_preserved_before_a_resubmission(self):
        """A first-pass clearance was granted, not preserved. Reporting it as
        preserved would inflate the number the evaluation counts."""
        RecordClearance.objects.create(record=self.record, office="itso", status="cleared")

        data = self._detail()
        self.assertFalse(data["clearances"][0]["preserved"])
        self.assertEqual(data["resubmission"]["offices_preserved"], [])

    def test_a_clearance_that_survived_a_resubmission_is_preserved(self):
        """The contribution, stated by the API: IERC declined, ITSO's earlier
        clearance carried over rather than being reviewed again."""
        itso = RecordClearance.objects.create(
            record=self.record, office="itso", status="cleared"
        )
        RecordClearance.objects.create(record=self.record, office="ierc", status="pending")
        Review.objects.create(
            record=self.record, reviewed_by=self.itso, stage="ierc", status="declined",
        )
        # The resubmission happens after ITSO cleared.
        self.record.resubmission_count = 1
        self.record.last_resubmitted_at = timezone.now()
        self.record.save(update_fields=["resubmission_count", "last_resubmitted_at"])

        data = self._detail()
        by_office = {c["office"]: c for c in data["clearances"]}
        self.assertTrue(by_office["itso"]["preserved"])
        self.assertFalse(by_office["ierc"]["preserved"])
        self.assertEqual(data["resubmission"]["count"], 1)
        self.assertEqual(data["resubmission"]["declining_office"], "ierc")
        self.assertEqual(data["resubmission"]["offices_preserved"], ["itso"])
        self.assertIsNotNone(itso.updated_at)

    def test_a_sequential_decline_names_no_declining_office(self):
        """RDCO declining restarts everything -- there is no office whose
        clearance was spared, and naming one would imply otherwise."""
        Review.objects.create(
            record=self.record, reviewed_by=self.itso, stage="rdco_intake", status="declined",
        )
        self.record.resubmission_count = 1
        self.record.last_resubmitted_at = timezone.now()
        self.record.save(update_fields=["resubmission_count", "last_resubmitted_at"])

        self.assertIsNone(self._detail()["resubmission"]["declining_office"])


class ViewerOfficeTests(APITestCase):
    """Who the record detail says *you* are (IR-139/IR-143).

    The decision screen must state which office's clearance it records. That
    label is server-derived for the same reason `preserved` is: a client-side
    role->office table would be a second definition to keep in step with
    `ROLE_TO_OFFICE`, and it would drift.
    """

    def setUp(self):
        self.owner = make_user("owner-vo@cit.edu", "Student")
        self.itso = make_user("itso-vo@cit.edu", "ITSO")
        self.rdco = make_user("rdco-vo@cit.edu", "RDCO")
        self.record = Record.objects.create(
            title="Viewer office record",
            record_type=RecordType.objects.first(),
            added_by=self.owner,
            pipeline_status="parallel_review",
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)
        RecordClearance.objects.create(record=self.record, office="itso", status="pending")

    def _detail_as(self, user):
        self.client.force_authenticate(user)
        return self.client.get(f"/api/v1/records/{self.record.id}/").data

    def test_a_clearance_officer_is_told_which_office_they_clear_for(self):
        data = self._detail_as(self.itso)
        self.assertEqual(data["your_office"], "itso")
        self.assertEqual(data["your_office_label"], "ITSO")

    def test_a_sequential_reviewer_clears_for_no_office(self):
        """RDCO decides the record at its own stages; it holds no clearance row,
        so claiming an office would be false."""
        data = self._detail_as(self.rdco)
        self.assertIsNone(data["your_office"])
        self.assertIsNone(data["your_office_label"])

    def test_an_author_clears_for_no_office(self):
        data = self._detail_as(self.owner)
        self.assertIsNone(data["your_office"])

    def test_the_stage_label_comes_from_the_server(self):
        """AC: no client-side pipeline-key -> English mapping."""
        self.assertEqual(self._detail_as(self.owner)["stage_label"], "Parallel Office Review")
