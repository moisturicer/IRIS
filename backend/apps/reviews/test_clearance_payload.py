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
            pipeline_status="in_review",
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

    def test_a_revision_asked_by_a_party_that_clears_nothing_names_no_office(self):
        """The Adviser, RDCO and the retired intake hold no clearance row, so a
        revision they asked for spares no office's clearance, and naming one
        would imply otherwise. (IR-274 replaced `rdco_intake` here with the
        one surviving spelling, `intake`, and added the other two.)"""
        self.record.resubmission_count = 1
        self.record.last_resubmitted_at = timezone.now()
        self.record.save(update_fields=["resubmission_count", "last_resubmitted_at"])
        for stage in ("adviser", "rdco", "intake"):
            with self.subTest(stage=stage):
                Review.objects.create(
                    record=self.record, reviewed_by=self.itso, stage=stage, status="declined",
                )
                self.assertIsNone(self._detail()["resubmission"]["declining_office"])


class StageLabelTests(APITestCase):
    """
    The status label comes from the server (IR-143).

    **Retired here by IR-274: `ViewerOfficeTests`.** They pinned `your_office`
    and `your_office_label`, which told the fixed pipeline's reviewer form
    (`EvaluationPage`) which office's clearance it would record. The form and
    both fields were deleted with the pipeline; an office reviewer now acts
    from a seat, and record detail's `office_review` says as which party
    (`test_office_review.py`).
    """

    def setUp(self):
        self.owner = make_user("owner-vo@cit.edu", "Student")
        self.record = Record.objects.create(
            title="Viewer office record",
            record_type=RecordType.objects.first(),
            added_by=self.owner,
            pipeline_status="in_review",
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)

    def test_the_stage_label_comes_from_the_server(self):
        """AC: no client-side pipeline-key -> English mapping."""
        self.client.force_authenticate(self.owner)
        data = self.client.get(f"/api/v1/records/{self.record.id}/").data
        self.assertEqual(data["stage_label"], "In Review")
        self.assertNotIn("your_office", data)
        self.assertNotIn("your_office_label", data)
