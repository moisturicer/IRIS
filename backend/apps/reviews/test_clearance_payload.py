"""The clearance payload, end to end (IR-139).

`test_clearance_state.py` proves the rule. This proves the API actually says
it -- that `preserved` reaches the client, that `resubmission{}` reports what
survived, and that a review-queue row carries the office context which made
"a KTTO reviewer and an IERC reviewer see byte-identical rows" the defect
IR-143 describes.

Run:
    docker compose exec -T backend python manage.py test apps.reviews.test_clearance_payload
"""
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.records.models import Record, RecordOwner, RecordType
from apps.reviews.models import RecordClearance, Review
from apps.reviews.serializers import queue_rows


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


class QueueRowContextTests(APITestCase):
    """The rows an office sees -- IR-143's precondition."""

    def setUp(self):
        self.owner = make_user("owner-q139@cit.edu", "Student")
        self.record = Record.objects.create(
            title="Queue row record",
            record_type=RecordType.objects.first(),
            added_by=self.owner,
            pipeline_status="parallel_review",
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)
        RecordClearance.objects.create(record=self.record, office="ierc", status="pending")
        RecordClearance.objects.create(record=self.record, office="ktto", status="cleared")

    def test_a_row_states_which_office_the_viewer_would_be_clearing_for(self):
        """The fix for byte-identical rows: an IERC reviewer is told they are
        recording IERC's clearance, not approving the record."""
        row = queue_rows([self.record], viewer_office="ierc")[0]
        self.assertEqual(row["your_office"], "ierc")
        self.assertEqual(row["your_office_label"], "IERC")

    def test_two_offices_get_different_rows_for_the_same_record(self):
        """The defect IR-143 names, asserted directly."""
        ierc = queue_rows([self.record], viewer_office="ierc")[0]
        ktto = queue_rows([self.record], viewer_office="ktto")[0]
        self.assertNotEqual(ierc["your_office"], ktto["your_office"])
        self.assertNotEqual(ierc["peers"], ktto["peers"])

    def test_peers_exclude_the_viewers_own_office(self):
        peers = queue_rows([self.record], viewer_office="ierc")[0]["peers"]
        self.assertEqual([p["office"] for p in peers], ["ktto"])
        self.assertEqual(peers[0]["status_label"], "Cleared")

    def test_peers_never_carry_a_peer_comment(self):
        """A reviewer should see *that* a peer decided, not their reasoning --
        reading it first is what makes parallel clearances stop being
        independent."""
        RecordClearance.objects.filter(record=self.record, office="ktto").update(
            comment="KTTO's private reasoning"
        )
        for peer in queue_rows([self.record], viewer_office="ierc")[0]["peers"]:
            self.assertNotIn("comment", peer)

    def test_a_row_carries_stage_and_waiting_time(self):
        row = queue_rows([self.record], viewer_office="ierc")[0]
        self.assertEqual(row["stage"], "parallel_review")
        self.assertEqual(row["stage_label"], "Parallel Office Review")
        self.assertIsNotNone(row["waiting_since"])
        self.assertGreaterEqual(row["waiting_days"], 0)

    def test_a_resubmitted_record_is_marked_in_the_list(self):
        self.record.resubmission_count = 2
        self.record.last_resubmitted_at = timezone.now()
        self.record.save(update_fields=["resubmission_count", "last_resubmitted_at"])

        row = queue_rows([self.record], viewer_office="ierc")[0]
        self.assertTrue(row["resubmitted"])
        self.assertEqual(row["resubmission_count"], 2)

    def test_an_unreviewed_record_waits_from_submission(self):
        """With no decision yet there is no review to date the wait from, and
        falling back to 'now' would report every fresh queue as instant."""
        row = queue_rows([self.record], viewer_office="ierc")[0]
        self.assertEqual(row["waiting_since"], self.record.created_at.isoformat())
