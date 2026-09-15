"""
IR-256: the reviewer-directed routing tables, added beside the current pipeline.

This is the expand step of ADR-021's expand–contract sequence
(`docs/workflow_routing_architecture.md` §7). `RecordAssignment`, `RoutingEvent`
and `ResubmissionRequest` exist, and `Review` can point at the assignment it
was made under. **Nothing writes to them yet**: IR-257 dual-writes, and IR-260
makes them authoritative. So these tests pin two things only:

- **the constraints the tables carry.** At most one *active* assignment per
  Record and party, enforced by the database rather than by whichever service
  remembers to check;
- **that nothing behaves differently yet.** The new vocabulary values exist,
  but no endpoint accepts them.

The migration itself, applied over existing rows, is tested separately in
`test_workflow_tables_migration.py`.
"""

import uuid

from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.records.models import Record, RecordOwner, RecordType
from apps.reviews.models import RecordAssignment, ResubmissionRequest, Review, RoutingEvent
from core.enums import (
    AssignmentState,
    ClearanceStatus,
    Party,
    PipelineStatus,
    RecordTypeName,
    ResubmissionRequestState,
    ReviewDecision,
    ReviewStage,
    RoleName,
)


def _user(email, role_name=RoleName.RDCO):
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", first_name="Test",
        last_name="User", role=role, is_verified=True,
    )


def _record(owner, pipeline_status=PipelineStatus.RDCO_INTAKE):
    record = Record.objects.create(
        title="IR-256 tables",
        abstract="A" * 40,
        record_type=RecordType.objects.get(name=RecordTypeName.THESIS_RESEARCH),
        added_by=owner,
        pipeline_status=pipeline_status,
        requested_ierc=True,
    )
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    return record


class OneActiveAssignmentPerPartyTests(TestCase):
    """ADR-021 §8: "at most one active row per (record, party)"."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = _user("ir256-owner@cit.edu", RoleName.STUDENT)
        cls.rdco = _user("ir256-rdco@cit.edu")

    def setUp(self):
        self.record = _record(self.owner)

    def _assign(self, party, state=AssignmentState.ACTIVE, record=None):
        return RecordAssignment.objects.create(
            record=record or self.record, party=party, state=state, opened_by=self.rdco
        )

    def test_a_second_active_assignment_for_the_same_party_is_rejected(self):
        self._assign(Party.IERC)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self._assign(Party.IERC)

    def test_past_assignments_for_the_same_party_are_all_kept(self):
        self._assign(Party.IERC, AssignmentState.COMPLETED)
        self._assign(Party.IERC, AssignmentState.WITHDRAWN)
        self._assign(Party.IERC, AssignmentState.COMPLETED)

        self.assertEqual(
            RecordAssignment.objects.filter(record=self.record, party=Party.IERC).count(), 3
        )

    def test_a_party_can_be_active_again_after_its_last_assignment_closed(self):
        """A record rerouted back to an office opens a fresh assignment for it."""
        self._assign(Party.IERC, AssignmentState.COMPLETED)

        self._assign(Party.IERC)

        self.assertEqual(
            RecordAssignment.objects.filter(
                record=self.record, party=Party.IERC, state=AssignmentState.ACTIVE
            ).count(),
            1,
        )

    def test_different_parties_can_be_active_on_one_record_at_once(self):
        """Concurrent review: an Adviser and ITSO can hold a record together."""
        for party in (Party.INTAKE, Party.ADVISER, Party.ITSO, Party.IERC, Party.KTTO):
            self._assign(party)

        self.assertEqual(
            RecordAssignment.objects.filter(
                record=self.record, state=AssignmentState.ACTIVE
            ).count(),
            5,
        )

    def test_the_same_party_can_be_active_on_two_different_records(self):
        self._assign(Party.IERC)

        self._assign(Party.IERC, record=_record(self.owner))

        self.assertEqual(
            RecordAssignment.objects.filter(
                party=Party.IERC, state=AssignmentState.ACTIVE
            ).count(),
            2,
        )


class NewRowsLinkTogetherTests(TestCase):
    """The shape later tickets write into: a review under an assignment, and what hangs off it."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = _user("ir256-link-owner@cit.edu", RoleName.STUDENT)
        cls.ierc = _user("ir256-link-ierc@cit.edu", RoleName.IERC)

    def test_a_review_can_point_at_the_assignment_it_was_made_under(self):
        record = _record(self.owner, PipelineStatus.PARALLEL_REVIEW)
        assignment = RecordAssignment.objects.create(record=record, party=Party.IERC)

        review = Review.objects.create(
            record=record, reviewed_by=self.ierc, stage=ReviewStage.IERC,
            status=ReviewDecision.DECLINED, assignment=assignment,
        )
        request = ResubmissionRequest.objects.create(
            record=record, party=Party.IERC, assignment=assignment, review=review,
            requested_by=self.ierc, reason="Consent form missing.",
        )

        self.assertEqual(list(assignment.reviews.all()), [review])
        self.assertEqual(request.state, ResubmissionRequestState.OPEN)
        self.assertEqual(list(record.resubmission_requests.all()), [request])

    def test_an_existing_review_needs_no_assignment(self):
        """Every review written before IR-257 has none, so the link must be optional."""
        record = _record(self.owner, PipelineStatus.PARALLEL_REVIEW)

        review = Review.objects.create(
            record=record, reviewed_by=self.ierc, stage=ReviewStage.IERC,
            status=ReviewDecision.APPROVED,
        )

        self.assertIsNone(review.assignment)

    def test_routing_events_from_one_call_share_a_group(self):
        record = _record(self.owner)
        group = uuid.uuid4()

        for target in (Party.ITSO, Party.IERC):
            RoutingEvent.objects.create(
                record=record, actor=self.ierc, from_party=Party.INTAKE,
                to_party=target, reason="Needs both.", group_id=group,
            )

        self.assertEqual(
            set(record.routing_events.filter(group_id=group).values_list("to_party", flat=True)),
            {Party.ITSO, Party.IERC},
        )

    def test_a_routing_event_from_the_submitter_has_no_from_party(self):
        record = _record(self.owner)

        event = RoutingEvent.objects.create(
            record=record, actor=self.owner, to_party=Party.INTAKE, group_id=uuid.uuid4()
        )

        self.assertIsNone(event.from_party)


class VocabularyIsAddedBesideTheOldTests(TestCase):
    """ADR-021 §8's values exist, and none of the values they replace has gone."""

    def test_the_new_values_are_stored_as_the_adr_names_them(self):
        self.assertEqual(PipelineStatus.IN_REVIEW, "in_review")
        self.assertEqual(Party.INTAKE, "intake")
        self.assertEqual(ReviewDecision.NEGATIVE_FINDING, "negative_finding")
        self.assertEqual(ClearanceStatus.NOT_CLEARED, "not_cleared")

    def test_party_is_the_review_stage_vocabulary(self):
        """ADR-021 §1: no new enum, `Party` is `ReviewStage`."""
        self.assertIs(Party, ReviewStage)

    def test_the_old_values_stay_until_the_contract_step(self):
        self.assertEqual(ReviewStage.RDCO_INTAKE, "rdco_intake")
        self.assertEqual(ReviewDecision.DECLINED, "declined")
        self.assertEqual(ClearanceStatus.REJECTED, "rejected")
        for value in (
            "adviser_review", "rdco_intake", "itso_review",
            "parallel_review", "rdco_review", "declined",
        ):
            self.assertIn(value, PipelineStatus.values)

    def test_an_assignment_party_is_never_rdco_intake(self):
        """ADR-021 §2: `rdco_intake` is a stored Review value, never a party's identity."""
        parties = {value for value, _ in RecordAssignment._meta.get_field("party").choices}

        self.assertEqual(parties, {"intake", "adviser", "itso", "ierc", "ktto", "rdco"})

    def test_the_new_tables_take_their_states_from_the_enums(self):
        self.assertEqual(
            list(RecordAssignment._meta.get_field("state").choices), list(AssignmentState.choices)
        )
        self.assertEqual(
            list(ResubmissionRequest._meta.get_field("state").choices),
            list(ResubmissionRequestState.choices),
        )

    def test_the_new_clearance_status_fits_its_column(self):
        field_length = Review._meta.get_field("status").max_length
        self.assertLessEqual(len(ReviewDecision.NEGATIVE_FINDING), field_length)

        from apps.reviews.models import RecordClearance

        self.assertLessEqual(
            len(ClearanceStatus.NOT_CLEARED),
            RecordClearance._meta.get_field("status").max_length,
        )


class NoEndpointAcceptsTheNewValuesYetTests(APITestCase):
    """
    Expand means nothing behaves differently. `ReviewWriteSerializer` validated
    `status` against every `ReviewDecision` value, so adding `negative_finding`
    to the enum would have made `/reviews/submit/` accept it and route it down
    the decline branch.
    """

    @classmethod
    def setUpTestData(cls):
        cls.owner = _user("ir256-api-owner@cit.edu", RoleName.STUDENT)
        cls.rdco = _user("ir256-api-rdco@cit.edu")

    def test_a_negative_finding_cannot_be_submitted_before_its_behaviour_exists(self):
        record = _record(self.owner)
        self.client.force_authenticate(self.rdco)

        response = self.client.post(
            "/api/v1/reviews/submit/",
            {"record_id": record.pk, "status": "negative_finding", "comment": "x"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("status", response.data)
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, "rdco_intake")
        self.assertFalse(Review.objects.filter(record=record).exists())
