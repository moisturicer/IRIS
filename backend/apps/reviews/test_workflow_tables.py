"""
IR-256: reviewer-directed routing table constraints retained after IR-260.

These tests pin the schema invariants carried through the cutover:

- **the constraints the tables carry.** At most one *active* assignment per
  Record and party, enforced by the database rather than by whichever service
  remembers to check;
- **the vocabulary fits its columns.**

The migration itself, applied over existing rows, is tested separately in
`test_workflow_tables_migration.py`.
"""

import uuid

from django.db import IntegrityError, transaction
from django.db.models import RestrictedError
from django.test import TestCase

from apps.accounts.models import Role, User
from apps.records.models import Record, RecordOwner, RecordType
from apps.reviews.models import (
    RecordAssignment,
    RecordClearance,
    ResubmissionRequest,
    Review,
    RoutingEvent,
)
from core.enums import (
    ASSIGNABLE_PARTIES,
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


def _record(owner, pipeline_status=PipelineStatus.IN_REVIEW):
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

    def test_the_database_refuses_an_active_assignment_to_intake(self):
        """IR-274 (ADR-032 §13): the retired party is history; its closed rows stay."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._assign(Party.INTAKE)
        for state in (AssignmentState.COMPLETED, AssignmentState.WITHDRAWN):
            with self.subTest(state=state):
                self.assertEqual(self._assign(Party.INTAKE, state).party, Party.INTAKE)

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
        """
        Concurrent review: an Adviser and ITSO can hold a record together.
        IR-274: RDCO replaces the retired Intake here, which may no longer be
        active (`test_the_database_refuses_an_active_assignment_to_intake`).
        """
        for party in (Party.ADVISER, Party.ITSO, Party.IERC, Party.KTTO, Party.RDCO):
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
        record = _record(self.owner, PipelineStatus.IN_REVIEW)
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

    def test_a_request_keeps_its_review_from_being_deleted_alone(self):
        """No workflow action deletes request history (architecture §5), so its review cannot go first."""
        record = _record(self.owner, PipelineStatus.IN_REVIEW)
        review = Review.objects.create(
            record=record, reviewed_by=self.ierc, stage=ReviewStage.IERC,
            status=ReviewDecision.DECLINED,
        )
        ResubmissionRequest.objects.create(record=record, party=Party.IERC, review=review)

        with self.assertRaises(RestrictedError):
            review.delete()

        record.delete()
        self.assertFalse(ResubmissionRequest.objects.exists())

    def test_an_existing_review_needs_no_assignment(self):
        """Every review written before IR-257 has none, so the link must be optional."""
        record = _record(self.owner, PipelineStatus.IN_REVIEW)

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

    def test_the_contract_step_removed_the_old_values(self):
        """
        Inverted deliberately by IR-274, the contract step this test was
        waiting for: it asserted the old values *stayed* until then. The fixed
        pipeline's statuses and `rdco_intake` are gone; the decision and
        clearance values that older rows still hold are kept as history.
        """
        self.assertNotIn("rdco_intake", ReviewStage.values)
        self.assertEqual(ReviewDecision.DECLINED, "declined")
        self.assertEqual(ClearanceStatus.REJECTED, "rejected")
        for value in (
            "adviser_review", "rdco_intake", "itso_review",
            "parallel_review", "rdco_review", "declined",
        ):
            self.assertNotIn(value, PipelineStatus.values)

    def test_intake_is_history_and_never_assignable(self):
        """ADR-032 §13: old rows keep `intake`; nothing new may hold it."""
        self.assertIn(Party.INTAKE, Party.values)
        self.assertNotIn(Party.INTAKE, ASSIGNABLE_PARTIES)

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

    def test_the_new_decision_and_clearance_values_fit_their_columns(self):
        self.assertLessEqual(
            len(ReviewDecision.NEGATIVE_FINDING), Review._meta.get_field("status").max_length
        )
        self.assertLessEqual(
            len(ClearanceStatus.NOT_CLEARED),
            RecordClearance._meta.get_field("status").max_length,
        )
