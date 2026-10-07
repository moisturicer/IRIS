"""
Reviewer seats, the office pool and coordinators (ADR-032 §4, §12; IR-415).

One test class per acceptance criterion of IR-415, at the REST seam IR-255
confirmed. The exception is the office completion rule: the act that finishes
a seat -- clearing, or recording a finding -- is IR-269's endpoint, so the rule
is pinned here through `seats.complete_seat()`, the one function that endpoint
will call, and IR-269 adds its own HTTP test on top.

Records are built in the state each case needs, with their assignments written
directly, rather than walked there through the legacy pipeline: what is under
test is the seat model, and a walk would test the pipeline as well. The two
cases that are *about* the pipeline -- the entry seat at submission and a
seat settling when the legacy pipeline closes an assignment -- use HTTP.
"""

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.records.models import Record, RecordOwner, RecordType
from apps.reviews import seats
from apps.reviews.models import (
    RecordAssignment,
    RecordClearance,
    ResubmissionRequest,
    Review,
    ReviewerSeat,
)
from core.enums import (
    AssignmentState,
    Office,
    Party,
    PipelineStatus,
    RecordTypeName,
    ResubmissionRequestState,
    ReviewDecision,
    RoleName,
    SeatSource,
    SeatState,
)

from .test_workflow_characterisation import SUBMIT_REVIEW, make_user


def claim_url(assignment):
    return reverse("assignment-claim", args=[assignment.pk])


def assign_url(assignment):
    return reverse("assignment-assign", args=[assignment.pk])


def add_url(assignment):
    return reverse("assignment-add-reviewer", args=[assignment.pk])


def open_url(seat):
    return reverse("seat-open", args=[seat.pk])


def reassign_url(seat):
    return reverse("seat-reassign", args=[seat.pk])


def withdraw_url(seat):
    return reverse("seat-withdraw", args=[seat.pk])


class SeatTestBase(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = make_user("seat-owner@cit.edu", RoleName.STUDENT)
        cls.stranger = make_user("seat-stranger@cit.edu", RoleName.STUDENT)
        cls.adviser = make_user("seat-adviser@cit.edu", RoleName.ADVISER)
        cls.other_adviser = make_user("seat-adviser2@cit.edu", RoleName.ADVISER)
        cls.itso = make_user("seat-itso@cit.edu", RoleName.ITSO)
        cls.itso2 = make_user("seat-itso2@cit.edu", RoleName.ITSO)
        cls.itso_coordinator = make_user("seat-itso-coord@cit.edu", RoleName.ITSO)
        cls.itso_coordinator.is_office_coordinator = True
        cls.itso_coordinator.save(update_fields=["is_office_coordinator"])
        cls.ierc = make_user("seat-ierc@cit.edu", RoleName.IERC)
        cls.ierc2 = make_user("seat-ierc2@cit.edu", RoleName.IERC)
        cls.ierc_coordinator = make_user("seat-ierc-coord@cit.edu", RoleName.IERC)
        cls.ierc_coordinator.is_office_coordinator = True
        cls.ierc_coordinator.save(update_fields=["is_office_coordinator"])
        cls.rdco = make_user("seat-rdco@cit.edu", RoleName.RDCO)

    def make_record(self, type_name=RecordTypeName.THESIS_RESEARCH,
                    pipeline_status=PipelineStatus.ITSO_REVIEW, **extra):
        record = Record.objects.create(
            title=f"Seats {type_name}",
            abstract="A" * 40,
            record_type=RecordType.objects.get_or_create(name=type_name)[0],
            added_by=self.owner,
            pipeline_status=pipeline_status,
            **extra,
        )
        RecordOwner.objects.create(record=record, user=self.owner, is_primary=True)
        return record

    def assignment(self, record, party):
        return RecordAssignment.objects.create(record=record, party=party)

    def seat(self, assignment, reviewer, state=SeatState.ASSIGNED, source=SeatSource.CLAIMED):
        return ReviewerSeat.objects.create(
            assignment=assignment, reviewer=reviewer, state=state, source=source,
        )

    def post(self, url, as_user, body=None):
        self.client.force_authenticate(as_user)
        return self.client.post(url, body or {}, format="json")

    def live_seats(self, assignment):
        return {
            (s.reviewer_id, s.state, s.source)
            for s in assignment.seats.exclude(state=SeatState.WITHDRAWN)
        }


# --- entry seat, and the pool --------------------------------------------------

class EntrySeatAndPoolTests(SeatTestBase):
    """The Adviser enters seated; an office enters as a pool (ADR-032 §4)."""

    def test_submitting_a_proposal_seats_its_adviser(self):
        record = self.make_record(
            RecordTypeName.PROPOSAL, PipelineStatus.DRAFT, adviser=self.adviser,
        )
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            reverse("record-submit", args=[record.pk]), {"dpa_accepted": True}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        assignment = RecordAssignment.objects.get(
            record=record, party=Party.ADVISER, state=AssignmentState.ACTIVE,
        )
        self.assertEqual(
            self.live_seats(assignment),
            {(self.adviser.pk, SeatState.ASSIGNED, SeatSource.ENTRY)},
        )

    def test_an_office_the_record_is_routed_to_is_a_pool(self):
        """RDCO's legacy intake approval routes to ITSO: ITSO holds it, nobody is seated."""
        record = self.make_record(
            pipeline_status=PipelineStatus.RDCO_INTAKE, requested_itso=True,
        )
        self.assignment(record, Party.INTAKE)
        self.client.force_authenticate(self.rdco)
        response = self.client.post(
            SUBMIT_REVIEW,
            {"record_id": record.pk, "status": ReviewDecision.APPROVED, "comment": ""},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        itso = RecordAssignment.objects.get(
            record=record, party=Party.ITSO, state=AssignmentState.ACTIVE,
        )
        self.assertFalse(itso.seats.exists())

    def test_the_legacy_pipeline_closing_the_advisers_turn_finishes_the_entry_seat(self):
        """The Adviser approves through today's form: their seat is done, not left open."""
        record = self.make_record(
            RecordTypeName.PROPOSAL, PipelineStatus.DRAFT, adviser=self.adviser,
        )
        self.client.force_authenticate(self.owner)
        self.client.post(
            reverse("record-submit", args=[record.pk]), {"dpa_accepted": True}, format="json",
        )
        self.client.force_authenticate(self.adviser)
        response = self.client.post(
            SUBMIT_REVIEW,
            {"record_id": record.pk, "status": ReviewDecision.APPROVED, "comment": "Fine."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        seat = ReviewerSeat.objects.get(assignment__record=record, reviewer=self.adviser)
        self.assertEqual(seat.state, SeatState.DONE)
        self.assertIsNotNone(seat.done_at)

    def test_an_office_member_who_decides_straight_from_the_pool_is_left_a_done_seat(self):
        """
        The legacy pipeline lets ITSO clear without claiming. That reviewer
        still took part, so they keep Review and Files afterwards (AC9).
        """
        record = self.make_record(pipeline_status=PipelineStatus.ITSO_REVIEW, requested_itso=True)
        RecordClearance.objects.create(record=record, office=Office.ITSO)
        self.assignment(record, Party.ITSO)
        self.client.force_authenticate(self.itso)
        response = self.client.post(
            SUBMIT_REVIEW,
            {"record_id": record.pk, "status": ReviewDecision.APPROVED, "comment": "Clear."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        seat = ReviewerSeat.objects.get(assignment__record=record, reviewer=self.itso)
        self.assertEqual((seat.state, seat.source), (SeatState.DONE, SeatSource.CLAIMED))
        detail = self.client.get(reverse("record-detail", args=[record.pk])).data
        self.assertTrue(detail["is_participant"])
        # Nobody else at ITSO is made a participant by it.
        self.client.force_authenticate(self.itso2)
        self.assertFalse(self.client.get(reverse("record-detail", args=[record.pk])).data["is_participant"])


# --- claim -----------------------------------------------------------------------

class ClaimTests(SeatTestBase):

    def setUp(self):
        self.record = self.make_record()
        self.pool = self.assignment(self.record, Party.ITSO)

    def test_a_member_of_the_office_claims_from_its_pool(self):
        response = self.post(claim_url(self.pool), self.itso)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["source"], SeatSource.CLAIMED)
        self.assertEqual(response.data["state"], SeatState.ASSIGNED)
        self.assertEqual(
            self.live_seats(self.pool), {(self.itso.pk, SeatState.ASSIGNED, SeatSource.CLAIMED)},
        )

    def test_a_member_of_another_office_cannot_claim(self):
        response = self.post(claim_url(self.pool), self.ierc)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.assertFalse(self.pool.seats.exists())

    def test_an_owner_cannot_claim_their_own_record(self):
        response = self.post(claim_url(self.pool), self.owner)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_claimed_record_is_not_claimed_twice(self):
        self.post(claim_url(self.pool), self.itso)
        response = self.post(claim_url(self.pool), self.itso2)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(len(self.live_seats(self.pool)), 1)

    def test_a_closed_assignment_cannot_be_claimed(self):
        self.pool.state = AssignmentState.COMPLETED
        self.pool.save(update_fields=["state"])
        response = self.post(claim_url(self.pool), self.itso)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_record_the_caller_cannot_see_is_a_404(self):
        """A student who does not own it cannot even learn the assignment exists."""
        response = self.post(claim_url(self.pool), self.stranger)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_a_missing_assignment_is_a_404(self):
        response = self.post(reverse("assignment-claim", args=[999999]), self.itso)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# --- assign, reassign, withdraw ---------------------------------------------------

class CoordinatorTests(SeatTestBase):

    def setUp(self):
        self.record = self.make_record()
        self.pool = self.assignment(self.record, Party.ITSO)

    def test_a_coordinator_assigns_a_member_of_their_office(self):
        response = self.post(assign_url(self.pool), self.itso_coordinator, {"reviewer": self.itso.pk})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        seat = ReviewerSeat.objects.get(pk=response.data["id"])
        self.assertEqual(
            (seat.reviewer, seat.source, seat.assigned_by),
            (self.itso, SeatSource.ASSIGNED, self.itso_coordinator),
        )

    def test_a_non_coordinator_cannot_assign(self):
        response = self.post(assign_url(self.pool), self.itso2, {"reviewer": self.itso.pk})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.assertFalse(self.pool.seats.exists())

    def test_a_coordinator_cannot_assign_outside_their_own_office(self):
        response = self.post(assign_url(self.pool), self.ierc_coordinator, {"reviewer": self.itso.pk})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.assertFalse(self.pool.seats.exists())

    def test_a_coordinator_cannot_seat_another_offices_member(self):
        response = self.post(assign_url(self.pool), self.itso_coordinator, {"reviewer": self.ierc.pk})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_nobody_is_seated_twice(self):
        self.seat(self.pool, self.itso)
        response = self.post(assign_url(self.pool), self.itso_coordinator, {"reviewer": self.itso.pk})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_an_assignment_can_hold_several_seats(self):
        self.seat(self.pool, self.itso)
        response = self.post(assign_url(self.pool), self.itso_coordinator, {"reviewer": self.itso2.pk})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual({r for r, *_ in self.live_seats(self.pool)}, {self.itso.pk, self.itso2.pk})

    def test_a_coordinator_reassigns_a_seat(self):
        seat = self.seat(self.pool, self.itso, state=SeatState.IN_REVIEW)
        response = self.post(reassign_url(seat), self.itso_coordinator, {"reviewer": self.itso2.pk})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        seat.refresh_from_db()
        self.assertEqual(seat.state, SeatState.WITHDRAWN)
        self.assertEqual(
            self.live_seats(self.pool), {(self.itso2.pk, SeatState.ASSIGNED, SeatSource.ASSIGNED)},
        )

    def test_a_non_coordinator_cannot_reassign_or_withdraw(self):
        seat = self.seat(self.pool, self.itso)
        self.assertEqual(
            self.post(reassign_url(seat), self.itso2, {"reviewer": self.itso2.pk}).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.post(withdraw_url(seat), self.itso2).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.post(withdraw_url(seat), self.ierc_coordinator).status_code, status.HTTP_403_FORBIDDEN,
        )
        seat.refresh_from_db()
        self.assertEqual(seat.state, SeatState.ASSIGNED)

    def test_a_coordinator_withdraws_a_seat_and_the_record_returns_to_the_pool(self):
        seat = self.seat(self.pool, self.itso)
        response = self.post(withdraw_url(seat), self.itso_coordinator)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["state"], SeatState.WITHDRAWN)
        self.assertEqual(self.live_seats(self.pool), set())
        # Withdrawn is history, not a block: the pool can be claimed again.
        self.assertEqual(self.post(claim_url(self.pool), self.itso).status_code, status.HTTP_201_CREATED)

    def test_a_finished_seat_cannot_be_withdrawn(self):
        seat = self.seat(self.pool, self.itso, state=SeatState.DONE)
        response = self.post(withdraw_url(seat), self.itso_coordinator)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_assign_needs_a_reviewer(self):
        response = self.post(assign_url(self.pool), self.itso_coordinator, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# --- open review --------------------------------------------------------------

class OpenReviewTests(SeatTestBase):

    def setUp(self):
        self.record = self.make_record()
        self.assignment_ = self.assignment(self.record, Party.ITSO)
        self.seat_ = self.seat(self.assignment_, self.itso)

    def test_open_review_moves_the_seat_to_in_review_and_stamps_opened_at(self):
        before = timezone.now()
        response = self.post(open_url(self.seat_), self.itso)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.seat_.refresh_from_db()
        self.assertEqual(self.seat_.state, SeatState.IN_REVIEW)
        self.assertIsNotNone(self.seat_.opened_at)
        self.assertGreaterEqual(self.seat_.opened_at, before)

    def test_opening_twice_keeps_the_first_start(self):
        self.post(open_url(self.seat_), self.itso)
        self.seat_.refresh_from_db()
        first = self.seat_.opened_at

        response = self.post(open_url(self.seat_), self.itso)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.seat_.refresh_from_db()
        self.assertEqual(self.seat_.opened_at, first)

    def test_only_the_seat_holder_opens_it(self):
        response = self.post(open_url(self.seat_), self.itso2)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.seat_.refresh_from_db()
        self.assertEqual(self.seat_.state, SeatState.ASSIGNED)

    def test_a_withdrawn_seat_cannot_be_opened(self):
        self.seat_.state = SeatState.WITHDRAWN
        self.seat_.save(update_fields=["state"])
        response = self.post(open_url(self.seat_), self.itso)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# --- add reviewer -------------------------------------------------------------------

class AddReviewerTests(SeatTestBase):

    def setUp(self):
        self.record = self.make_record()
        self.assignment_ = self.assignment(self.record, Party.ITSO)
        self.seat(self.assignment_, self.itso, state=SeatState.IN_REVIEW)

    def test_a_seat_holder_adds_a_colleague_from_their_own_office(self):
        response = self.post(add_url(self.assignment_), self.itso, {"reviewer": self.itso2.pk})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertIn((self.itso2.pk, SeatState.ASSIGNED, SeatSource.ADDED), self.live_seats(self.assignment_))

    def test_adding_a_reviewer_from_another_office_is_refused(self):
        """That is routing, a separate act: no IERC seat, and no IERC assignment."""
        response = self.post(add_url(self.assignment_), self.itso, {"reviewer": self.ierc.pk})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertNotIn(self.ierc.pk, {r for r, *_ in self.live_seats(self.assignment_)})
        self.assertFalse(
            RecordAssignment.objects.filter(record=self.record, party=Party.IERC).exists()
        )

    def test_someone_without_a_seat_cannot_add(self):
        response = self.post(add_url(self.assignment_), self.itso2, {"reviewer": self.itso_coordinator.pk})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_finished_seat_holder_no_longer_adds(self):
        ReviewerSeat.objects.filter(reviewer=self.itso).update(state=SeatState.DONE)
        response = self.post(add_url(self.assignment_), self.itso, {"reviewer": self.itso2.pk})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_the_adviser_has_no_office_to_add_from(self):
        record = self.make_record(
            RecordTypeName.PROPOSAL, PipelineStatus.ADVISER_REVIEW, adviser=self.adviser,
        )
        adviser = self.assignment(record, Party.ADVISER)
        self.seat(adviser, self.adviser, source=SeatSource.ENTRY)

        response = self.post(add_url(adviser), self.adviser, {"reviewer": self.other_adviser.pk})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)


# --- nominate (called by routing, IR-261) -------------------------------------------

class NominateTests(SeatTestBase):

    def test_a_nominee_is_seated_with_the_nominated_source(self):
        assignment = self.assignment(self.make_record(), Party.ITSO)
        seat = seats.nominate(assignment, self.adviser, self.itso)
        self.assertEqual((seat.source, seat.assigned_by), (SeatSource.NOMINATED, self.adviser))

    def test_a_nominee_outside_the_office_is_refused(self):
        assignment = self.assignment(self.make_record(), Party.ITSO)
        with self.assertRaises(seats.SeatError):
            seats.nominate(assignment, self.adviser, self.ierc)


# --- the office completion rule ---------------------------------------------------

class OfficeCompletionTests(SeatTestBase):
    """
    ADR-032 §12: "An office assignment with two seats does not complete until
    both are `done`." Driven through `complete_seat()`; see the module note.
    """

    def setUp(self):
        self.record = self.make_record(pipeline_status=PipelineStatus.IN_REVIEW)
        self.ierc_assignment = self.assignment(self.record, Party.IERC)
        self.first = self.seat(self.ierc_assignment, self.ierc, state=SeatState.IN_REVIEW)
        self.second = self.seat(self.ierc_assignment, self.ierc2, state=SeatState.IN_REVIEW)

    def state(self):
        self.ierc_assignment.refresh_from_db()
        return self.ierc_assignment.state

    def test_two_seats_complete_only_when_both_are_done(self):
        self.assertFalse(seats.complete_seat(self.first, self.ierc))
        self.assertEqual(self.state(), AssignmentState.ACTIVE)

        self.assertTrue(seats.complete_seat(self.second, self.ierc2))
        self.assertEqual(self.state(), AssignmentState.COMPLETED)

    def test_a_withdrawn_seat_does_not_hold_the_office_open(self):
        seats.complete_seat(self.first, self.ierc)
        response = self.post(withdraw_url(self.second), self.ierc_coordinator)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.state(), AssignmentState.COMPLETED)

    def test_an_open_resubmission_request_holds_the_office_open(self):
        review = Review.objects.create(
            record=self.record, reviewed_by=self.ierc, stage=Party.IERC,
            status=ReviewDecision.DECLINED, comment="Consent form missing.",
        )
        ResubmissionRequest.objects.create(
            record=self.record, party=Party.IERC, assignment=self.ierc_assignment,
            review=review, state=ResubmissionRequestState.OPEN,
        )
        seats.complete_seat(self.first, self.ierc)
        seats.complete_seat(self.second, self.ierc2)

        self.assertEqual(self.state(), AssignmentState.ACTIVE)

    def test_a_pool_is_never_complete(self):
        pool = self.assignment(self.record, Party.KTTO)
        self.assertFalse(seats.office_complete(pool))

    def test_on_the_legacy_pipeline_the_pipeline_still_decides(self):
        """Until IR-260, `shadow.sync()` owns a legacy record's assignments."""
        self.record.pipeline_status = PipelineStatus.PARALLEL_REVIEW
        self.record.save(update_fields=["pipeline_status"])

        seats.complete_seat(self.first, self.ierc)
        seats.complete_seat(self.second, self.ierc2)

        self.assertEqual(self.state(), AssignmentState.ACTIVE)


# --- review_access --------------------------------------------------------------

class ReviewAccessTests(SeatTestBase):
    """B3, built once in its seat-based form (decided 2026-10-07)."""

    def access(self, user):
        self.client.force_authenticate(user)
        response = self.client.get(reverse("user-me"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data["review_access"]

    def test_an_adviser_holding_no_seat_has_no_reviews(self):
        self.assertEqual(
            self.access(self.adviser),
            {"my_reviews": False, "offices": [], "is_coordinator": False},
        )

    def test_an_adviser_with_an_entry_seat_on_a_submitted_record_has_reviews(self):
        record = self.make_record(
            RecordTypeName.PROPOSAL, PipelineStatus.ADVISER_REVIEW, adviser=self.adviser,
        )
        self.seat(self.assignment(record, Party.ADVISER), self.adviser, source=SeatSource.ENTRY)

        self.assertTrue(self.access(self.adviser)["my_reviews"])

    def test_an_office_member_with_no_seat_has_reviews_for_the_pool(self):
        self.assertEqual(
            self.access(self.itso),
            {"my_reviews": True, "offices": [Party.ITSO], "is_coordinator": False},
        )

    def test_a_student_has_no_reviews(self):
        self.assertEqual(
            self.access(self.owner),
            {"my_reviews": False, "offices": [], "is_coordinator": False},
        )

    def test_is_coordinator_follows_the_user_flag(self):
        self.assertTrue(self.access(self.itso_coordinator)["is_coordinator"])
        self.assertFalse(self.access(self.itso)["is_coordinator"])

    def test_the_flag_means_nothing_without_an_office(self):
        self.owner.is_office_coordinator = True
        self.owner.save(update_fields=["is_office_coordinator"])
        self.assertFalse(self.access(self.owner)["is_coordinator"])

    def test_sign_in_carries_it_and_other_users_payloads_never_do(self):
        response = self.client.post(
            reverse("auth-login"),
            {"email": self.itso.email, "password": "TestPass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data["user"]["review_access"]["my_reviews"])

        self.client.force_authenticate(self.owner)
        advisers = self.client.get(reverse("user-advisers")).data
        rows = advisers["results"] if isinstance(advisers, dict) else advisers
        self.assertTrue(rows)
        self.assertTrue(all("review_access" not in row for row in rows))


# --- granting the coordinator flag -------------------------------------------------

class CoordinatorGrantTests(SeatTestBase):

    def grant(self, as_user, target, value=True):
        self.client.force_authenticate(as_user)
        return self.client.patch(
            reverse("user-coordinator", args=[target.pk]),
            {"is_office_coordinator": value}, format="json",
        )

    def test_an_administrator_grants_and_revokes_it(self):
        response = self.grant(self.rdco, self.itso2)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.itso2.refresh_from_db()
        self.assertTrue(self.itso2.is_office_coordinator)

        self.grant(self.rdco, self.itso2, value=False)
        self.itso2.refresh_from_db()
        self.assertFalse(self.itso2.is_office_coordinator)

    def test_nobody_else_grants_it(self):
        self.assertEqual(self.grant(self.itso_coordinator, self.itso2).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.grant(self.itso2, self.itso2).status_code, status.HTTP_403_FORBIDDEN)

    def test_a_user_with_no_office_cannot_be_made_a_coordinator(self):
        self.assertEqual(self.grant(self.rdco, self.adviser).status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_role_change_drops_the_grant(self):
        """An ITSO coordinator moved to IERC is not thereby an IERC coordinator."""
        self.grant(self.rdco, self.itso2)
        self.client.force_authenticate(self.rdco)
        response = self.client.patch(
            reverse("user-change-role", args=[self.itso2.pk]),
            {"role_name": RoleName.IERC}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.itso2.refresh_from_db()
        self.assertFalse(self.itso2.is_office_coordinator)

    def test_users_cannot_grant_it_to_themselves_through_me(self):
        self.client.force_authenticate(self.itso2)
        self.client.patch(reverse("user-me"), {"is_office_coordinator": True}, format="json")
        self.itso2.refresh_from_db()
        self.assertFalse(self.itso2.is_office_coordinator)


# --- participation: a past seat holder keeps Review and Files ---------------------

class ParticipationTests(SeatTestBase):
    """IR-411's gap, closed here: `is_record_participant` counts anyone who has
    ever held a seat, so a reviewer whose part is done keeps the sections."""

    def detail(self, record, as_user):
        self.client.force_authenticate(as_user)
        response = self.client.get(reverse("record-detail", args=[record.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    def test_a_past_seat_holder_is_still_a_participant(self):
        record = self.make_record(pipeline_status=PipelineStatus.IN_REVIEW)
        assignment = self.assignment(record, Party.ITSO)
        seat = self.seat(assignment, self.itso, state=SeatState.IN_REVIEW)
        seats.complete_seat(seat, self.itso)
        assignment.refresh_from_db()
        self.assertEqual(assignment.state, AssignmentState.COMPLETED)

        data = self.detail(record, self.itso)

        self.assertTrue(data["is_participant"])
        # Nothing left to act on, which is exactly the case IR-411 lost.
        self.assertEqual(data["can_act"], [])
        self.assertEqual(data["can_request_document"], [])
        self.assertEqual(
            [(s["party"], s["state"]) for s in data["my_seats"]], [(Party.ITSO, SeatState.DONE)],
        )

    def test_an_office_member_who_never_held_a_seat_is_not(self):
        record = self.make_record(pipeline_status=PipelineStatus.IN_REVIEW)
        self.assignment(record, Party.ITSO)

        data = self.detail(record, self.itso2)

        self.assertFalse(data["is_participant"])
        self.assertEqual(data["my_seats"], [])

    def test_an_owner_is_one(self):
        record = self.make_record()
        self.assertTrue(self.detail(record, self.owner)["is_participant"])

    def test_my_seats_lists_only_the_viewers_own(self):
        record = self.make_record()
        assignment = self.assignment(record, Party.ITSO)
        self.seat(assignment, self.itso)
        self.seat(assignment, self.itso2)

        seats_seen = self.detail(record, self.itso)["my_seats"]

        self.assertEqual([s["reviewer"] for s in seats_seen], [self.itso.pk])
