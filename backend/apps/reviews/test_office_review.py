"""
An office reviewer clears or records a finding; an office completes when all
its seats are done; RDCO opens only on the specialist path (IR-269).

ADR-032 §3-§4 and their 2026-10-08 Amendment, at the REST seam IR-255
confirmed. One class per acceptance criterion, then the decisions settled in
the 2026-10-08 grilling. Records reach the new model through
`routing.enter_at_adviser` and the Adviser's accept & route, as in
`test_routing.py`.
"""

from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.documents.models import DocumentRequest
from apps.notifications.models import Notification
from apps.reviews import seats
from apps.reviews.models import (
    RecordAssignment,
    RecordClearance,
    Review,
    ReviewerSeat,
    RoutingEvent,
)
from core.enums import (
    AssignmentState,
    ClearanceStatus,
    Party,
    PipelineStatus,
    RecordTypeName,
    ReviewDecision,
    RoleName,
    SeatSource,
    SeatState,
    TrackerPartyState,
    WorkflowState,
)

from .test_routing import RoutingTestBase
from .test_workflow_characterisation import make_user


def office_review_url(record):
    return reverse("record-office-review", args=[record.pk])


def tracker_url(record):
    return reverse("record-tracker", args=[record.pk])


def detail_url(record):
    return reverse("record-detail", args=[record.pk])


def add_reviewer_url(assignment):
    return reverse("assignment-add-reviewer", args=[assignment.pk])


def withdraw_url(seat):
    return reverse("seat-withdraw", args=[seat.pk])


CLEARED = str(ClearanceStatus.CLEARED.value)


class OfficeReviewTestBase(RoutingTestBase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.ierc2 = make_user("office-ierc2@cit.edu", RoleName.IERC)
        cls.rdco2 = make_user("office-rdco2@cit.edu", RoleName.RDCO)
        cls.itso_coordinator = make_user("office-itso-coord@cit.edu", RoleName.ITSO)
        cls.itso_coordinator.is_office_coordinator = True
        cls.itso_coordinator.save(update_fields=["is_office_coordinator"])
        cls.stranger = make_user("office-stranger@cit.edu", RoleName.STUDENT)

    def routed(self, *parties, type_name=RecordTypeName.THESIS_RESEARCH):
        record = self.new_model(type_name)
        self.accepted_to(record, *parties)
        return record

    def assignment(self, record, party):
        return RecordAssignment.objects.get(
            record=record, party=party, state=AssignmentState.ACTIVE,
        )

    def opened_seat(self, record, party, reviewer):
        """`reviewer` claimed `party`'s review and opened it."""
        seat = self.seat(record, party, reviewer)
        seat.state = SeatState.IN_REVIEW
        seat.opened_at = timezone.now()
        seat.save(update_fields=["state", "opened_at"])
        return seat

    def review(self, record, as_user, outcome=CLEARED, comment=""):
        return self.post(
            office_review_url(record), as_user, {"outcome": outcome, "comment": comment},
        )

    def cleared(self, record, as_user, comment=""):
        response = self.review(record, as_user, CLEARED, comment)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response

    def found(self, record, as_user, comment="Consent forms do not cover minors."):
        response = self.review(record, as_user, "finding", comment)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response

    def clearance(self, record, office):
        return RecordClearance.objects.get(record=record, office=office).status

    def rows(self, payload):
        return {row["party"]: row for row in payload["parties"]}

    def tracker(self, record, as_user=None):
        self.client.force_authenticate(as_user or self.owner)
        return self.client.get(tracker_url(record)).data

    def rdco_assignments(self, record):
        return RecordAssignment.objects.filter(record=record, party=Party.RDCO)


# --- AC: clear, one seat ---------------------------------------------------------------

class ClearOneSeatTests(OfficeReviewTestBase):

    def test_an_itso_seat_holder_clears_and_itso_completes(self):
        record = self.routed(Party.ITSO, Party.IERC)
        seat = self.opened_seat(record, Party.ITSO, self.itso)

        response = self.cleared(record, self.itso, "No patentable mechanism.")

        seat.refresh_from_db()
        self.assertEqual(seat.state, SeatState.DONE)
        self.assertIsNotNone(seat.done_at)
        itso = RecordAssignment.objects.get(record=record, party=Party.ITSO)
        self.assertEqual(itso.state, AssignmentState.COMPLETED)
        self.assertEqual(self.clearance(record, Party.ITSO), ClearanceStatus.CLEARED)
        review = Review.objects.get(record=record, stage=Party.ITSO)
        self.assertEqual(
            (review.status, review.comment, review.assignment_id),
            (ReviewDecision.APPROVED, "No patentable mechanism.", itso.pk),
        )
        # It answers with the tracker, which shows ITSO completed.
        row = self.rows(response.data)[Party.ITSO]
        self.assertEqual(row["state"], TrackerPartyState.COMPLETED)
        self.assertEqual(row["outcome"], ClearanceStatus.CLEARED)

    def test_the_clearance_carries_the_office_outcome_only(self):
        """Each seat's verdict is its own Review (decided 2026-10-08)."""
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.cleared(record, self.itso, "Fine.")

        clearance = RecordClearance.objects.get(record=record, office=Party.ITSO)
        self.assertIsNone(clearance.reviewed_by)
        self.assertEqual(clearance.comment, "")

    def test_a_clearance_needs_no_comment(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.cleared(record, self.itso)
        self.assertEqual(self.clearance(record, Party.ITSO), ClearanceStatus.CLEARED)


# --- AC: two seats (the HTTP version of IR-415's AC1) ------------------------------------

class TwoSeatsTests(OfficeReviewTestBase):

    def test_two_seats_complete_only_when_both_are_done(self):
        record = self.routed(Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.opened_seat(record, Party.IERC, self.ierc2)

        self.cleared(record, self.ierc)
        ierc = RecordAssignment.objects.get(record=record, party=Party.IERC)
        self.assertEqual(ierc.state, AssignmentState.ACTIVE)
        self.assertEqual(self.clearance(record, Party.IERC), ClearanceStatus.PENDING)

        self.cleared(record, self.ierc2)
        ierc.refresh_from_db()
        self.assertEqual(ierc.state, AssignmentState.COMPLETED)
        self.assertEqual(self.clearance(record, Party.IERC), ClearanceStatus.CLEARED)

    def test_a_reviewer_whose_part_is_done_cannot_act_again(self):
        record = self.routed(Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.opened_seat(record, Party.IERC, self.ierc2)
        self.cleared(record, self.ierc)

        response = self.review(record, self.ierc, "finding", "Second thoughts.")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Review.objects.filter(record=record, stage=Party.IERC).count(), 1)


# --- AC: finding ---------------------------------------------------------------------------

class FindingTests(OfficeReviewTestBase):

    def test_a_finding_requires_a_comment(self):
        record = self.routed(Party.IERC)
        seat = self.opened_seat(record, Party.IERC, self.ierc)

        for blank in ("", "   "):
            response = self.review(record, self.ierc, "finding", blank)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        seat.refresh_from_db()
        self.assertEqual(seat.state, SeatState.IN_REVIEW)
        self.assertFalse(Review.objects.filter(record=record, stage=Party.IERC).exists())

    def test_one_finding_makes_the_office_not_cleared(self):
        record = self.routed(Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.opened_seat(record, Party.IERC, self.ierc2)

        self.found(record, self.ierc, "Consent forms do not cover minors.")
        response = self.cleared(record, self.ierc2)

        self.assertEqual(self.clearance(record, Party.IERC), ClearanceStatus.NOT_CLEARED)
        row = self.rows(response.data)[Party.IERC]
        self.assertEqual(row["outcome"], ClearanceStatus.NOT_CLEARED)
        # The finding shows on the tracker: the seat that recorded it, and its reason.
        self.assertCountEqual(
            [s["verdict"] for s in row["seats"]],
            [ReviewDecision.NEGATIVE_FINDING, ReviewDecision.APPROVED],
        )
        finding = [r for r in response.data["reviews"] if r["status"] == ReviewDecision.NEGATIVE_FINDING]
        self.assertEqual(finding[0]["comment"], "Consent forms do not cover minors.")


# --- AC: hand-back ---------------------------------------------------------------------------

class HandBackTests(OfficeReviewTestBase):

    def test_rdco_opens_only_once_both_offices_have_completed(self):
        record = self.routed(Party.ITSO, Party.IERC)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.opened_seat(record, Party.IERC, self.ierc)

        self.cleared(record, self.itso)
        self.assertFalse(self.rdco_assignments(record).exists())

        with self.captureOnCommitCallbacks(execute=True):
            response = self.cleared(record, self.ierc)

        rdco = self.rdco_assignments(record).get()
        self.assertEqual(rdco.state, AssignmentState.ACTIVE)
        self.assertFalse(rdco.seats.exists(), "RDCO's assignment is a pool")
        self.assertIsNone(rdco.opened_by)
        self.assertEqual(response.data["workflow_state"], WorkflowState.FINAL_REVIEW)

        # Nobody routed it: one movement with no actor, from IERC to RDCO.
        event = RoutingEvent.objects.get(record=record, to_party=Party.RDCO)
        self.assertEqual((event.actor, event.from_party), (None, Party.IERC))

        # RDCO's members hear it as a pool broadcast; the owners hear it too.
        self.assertTrue(Notification.objects.filter(
            record=record, broadcast_to_role__name=RoleName.RDCO,
        ).exists())
        self.assertTrue(Notification.objects.filter(
            record=record, recipient=self.owner, message__contains="RDCO",
        ).exists())

    def test_the_owners_hear_each_office_finish_and_no_single_verdict(self):
        record = self.routed(Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.opened_seat(record, Party.IERC, self.ierc2)

        with self.captureOnCommitCallbacks(execute=True):
            self.cleared(record, self.ierc)
        self.assertFalse(Notification.objects.filter(
            record=record, recipient=self.owner, message__contains="IERC finished",
        ).exists())

        with self.captureOnCommitCallbacks(execute=True):
            self.found(record, self.ierc2)
        self.assertTrue(Notification.objects.filter(
            record=record, recipient=self.owner, message__contains="IERC finished",
        ).exists())


# --- AC: no early or spurious hand-back ----------------------------------------------------

class NoSpuriousHandBackTests(OfficeReviewTestBase):

    def test_no_rdco_while_any_specialist_is_still_active(self):
        record = self.routed(Party.ITSO, Party.IERC, Party.KTTO)
        for party, user in ((Party.ITSO, self.itso), (Party.IERC, self.ierc)):
            self.opened_seat(record, party, user)
            self.cleared(record, user)

        self.assertEqual(self.active(record), {Party.KTTO})
        self.assertFalse(self.rdco_assignments(record).exists())

    def test_no_rdco_on_a_record_no_office_was_routed_to(self):
        record = self.new_model()

        self.assertFalse(self.rdco_assignments(record).exists())
        row = self.rows(self.tracker(record))[Party.RDCO]
        self.assertEqual(row["state"], TrackerPartyState.NOT_REQUIRED)
        self.assertEqual(row["state_label"], "Not required")

    def test_never_on_a_proposal(self):
        """
        A Proposal is never routed (IR-261 refuses it), so the only way an
        office could finish on one is a row nothing should write. Even then,
        the hand-back does not make RDCO the way into a Proposal.
        """
        record = self.new_model(RecordTypeName.PROPOSAL)
        assignment = RecordAssignment.objects.create(
            record=record, party=Party.ITSO, opened_at=timezone.now(),
        )
        seat = ReviewerSeat.objects.create(
            assignment=assignment, reviewer=self.itso, source=SeatSource.CLAIMED,
            state=SeatState.IN_REVIEW, opened_at=timezone.now(),
        )

        self.assertTrue(seats.complete_seat(seat, self.itso))

        self.assertFalse(self.rdco_assignments(record).exists())

    def test_rdco_already_holding_the_record_gets_no_second_assignment(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.cleared(record, self.itso)
        rdco = self.rdco_assignments(record).get()
        seats.claim(rdco, self.rdco)

        # RDCO sends it back to ITSO for another look, naming a reviewer.
        response = self.route(record, self.rdco, [{"party": Party.ITSO, "nominee": self.itso2.pk}])
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        seat = ReviewerSeat.objects.get(assignment__record=record, reviewer=self.itso2)
        seats.open_review(seat, self.itso2)

        with self.captureOnCommitCallbacks(execute=True):
            self.cleared(record, self.itso2)

        self.assertEqual(self.rdco_assignments(record).count(), 1)
        self.assertEqual(self.rdco_assignments(record).get().state, AssignmentState.ACTIVE)
        # RDCO's own seat holder hears that ITSO finished, not RDCO's whole pool.
        self.assertTrue(Notification.objects.filter(
            record=record, recipient=self.rdco, message__contains="ITSO finished",
        ).exists())
        self.assertFalse(Notification.objects.filter(
            record=record, broadcast_to_role__name=RoleName.RDCO,
            message__contains="ITSO finished",
        ).exists())


# --- AC: no reject ------------------------------------------------------------------------

class NoRejectTests(OfficeReviewTestBase):

    def test_an_office_cannot_reject_or_publish(self):
        record = self.routed(Party.ITSO)
        seat = self.opened_seat(record, Party.ITSO, self.itso)

        for outcome in (
            ReviewDecision.REJECTED, PipelineStatus.PUBLISHED, ReviewDecision.APPROVED,
            ReviewDecision.DECLINED, "", None, ["finding"],
        ):
            response = self.review(record, self.itso, outcome, "Not novel.")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, outcome)

        seat.refresh_from_db()
        self.assertEqual(seat.state, SeatState.IN_REVIEW)
        self.assertFalse(Review.objects.filter(record=record, stage=Party.ITSO).exists())
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)


# --- who may act, and refusals --------------------------------------------------------------

class RefusalTests(OfficeReviewTestBase):

    def test_who_comes_before_what(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)

        # An ITSO member who holds no seat, another office, the Adviser, an owner.
        for user in (self.itso2, self.ierc, self.adviser, self.owner):
            response = self.review(record, user, "nonsense")
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, user.email)

    def test_a_record_the_caller_cannot_see_is_a_404(self):
        record = self.routed(Party.ITSO)
        response = self.review(record, self.stranger)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_an_unopened_seat_is_refused(self):
        """`opened_at` is the time-on-task start, so it must be set (decided 2026-10-08)."""
        record = self.routed(Party.ITSO)
        seat = self.seat(record, Party.ITSO, self.itso)  # assigned, not opened

        response = self.review(record, self.itso)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Open the review", response.data["detail"])
        seat.refresh_from_db()
        self.assertEqual(seat.state, SeatState.ASSIGNED)

    def test_an_open_document_request_of_its_own_office_blocks_both_acts(self):
        record = self.routed(Party.IERC, Party.ITSO)
        self.opened_seat(record, Party.IERC, self.ierc)
        request = DocumentRequest.objects.create(
            record=record, party=Party.IERC, assignment=self.assignment(record, Party.IERC),
            requested_by=self.ierc, message="Signed consent forms, please.",
        )

        for outcome, comment in ((CLEARED, ""), ("finding", "The forms never came.")):
            response = self.review(record, self.ierc, outcome, comment)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, outcome)
            self.assertIn("Withdraw IERC's document request", response.data["detail"])
        self.assertFalse(Review.objects.filter(record=record, stage=Party.IERC).exists())

        # Another office's open request does not hold IERC back.
        request.party = Party.ITSO
        request.save(update_fields=["party"])
        self.cleared(record, self.ierc)

    def test_a_legacy_record_is_refused(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        record.pipeline_status = PipelineStatus.PARALLEL_REVIEW
        record.save(update_fields=["pipeline_status"])

        response = self.review(record, self.itso)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# --- the latest completed review round wins (decided 2026-10-08) ------------------------------

class LatestRoundWinsTests(OfficeReviewTestBase):

    def route_back_to_itso(self, record):
        rdco = self.rdco_assignments(record).get()
        seats.claim(rdco, self.rdco)
        response = self.route(record, self.rdco, [{"party": Party.ITSO, "nominee": self.itso2.pk}])
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        seat = ReviewerSeat.objects.get(assignment__record=record, reviewer=self.itso2)
        seats.open_review(seat, self.itso2)

    def test_itso_clears_is_routed_again_and_a_finding_makes_it_not_cleared(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.cleared(record, self.itso)
        self.route_back_to_itso(record)

        # While the new round runs, the earlier clearance stands, and says so.
        self.assertEqual(self.clearance(record, Party.ITSO), ClearanceStatus.CLEARED)
        row = self.rows(self.tracker(record))[Party.ITSO]
        self.assertEqual(row["state"], TrackerPartyState.ACTIVE)
        self.assertTrue(row["outcome_earlier"])
        self.assertEqual(row["outcome_label"], "Cleared (earlier review) · reviewing again")

        self.found(record, self.itso2, "The second claim reads on prior art.")

        self.assertEqual(self.clearance(record, Party.ITSO), ClearanceStatus.NOT_CLEARED)
        row = self.rows(self.tracker(record))[Party.ITSO]
        self.assertFalse(row["outcome_earlier"])

    def test_and_in_the_other_direction_a_new_clearance_replaces_a_finding(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.found(record, self.itso)
        self.assertEqual(self.clearance(record, Party.ITSO), ClearanceStatus.NOT_CLEARED)
        self.route_back_to_itso(record)

        self.cleared(record, self.itso2)

        self.assertEqual(self.clearance(record, Party.ITSO), ClearanceStatus.CLEARED)


# --- a coordinator's withdrawal completes an office the same way ------------------------------

class WithdrawalTests(OfficeReviewTestBase):

    def test_withdrawing_the_last_unfinished_seat_completes_and_hands_back(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        second = self.opened_seat(record, Party.ITSO, self.itso2)
        self.cleared(record, self.itso)

        response = self.post(withdraw_url(second), self.itso_coordinator, {})

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.clearance(record, Party.ITSO), ClearanceStatus.CLEARED)
        self.assertEqual(self.rdco_assignments(record).get().state, AssignmentState.ACTIVE)

    def test_an_office_whose_seats_were_all_withdrawn_returns_to_its_pool(self):
        record = self.routed(Party.ITSO)
        only = self.opened_seat(record, Party.ITSO, self.itso)

        self.post(withdraw_url(only), self.itso_coordinator, {})

        self.assertEqual(self.assignment(record, Party.ITSO).state, AssignmentState.ACTIVE)
        self.assertEqual(self.clearance(record, Party.ITSO), ClearanceStatus.PENDING)
        self.assertFalse(self.rdco_assignments(record).exists())
        self.assertTrue(self.rows(self.tracker(record))[Party.ITSO]["in_pool"])


# --- the party status strip ----------------------------------------------------------------

class StripTests(OfficeReviewTestBase):

    def test_rdco_reads_waiting_once_an_office_holds_the_record(self):
        record = self.routed(Party.ITSO)
        row = self.rows(self.tracker(record))[Party.RDCO]
        self.assertEqual(row["state"], TrackerPartyState.AWAITING)

    def test_a_pool_is_marked_and_a_seated_office_is_not(self):
        record = self.routed(Party.ITSO, Party.IERC)
        self.opened_seat(record, Party.ITSO, self.itso)

        rows = self.rows(self.tracker(record))
        self.assertFalse(rows[Party.ITSO]["in_pool"])
        self.assertTrue(rows[Party.IERC]["in_pool"])

    def test_seat_names_go_to_participants_only(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)

        for participant in (self.owner, self.itso, self.adviser):
            seats_row = self.rows(self.tracker(record, participant))[Party.ITSO]["seats"]
            self.assertEqual(len(seats_row), 1, participant.email)
            self.assertEqual(seats_row[0]["state"], SeatState.IN_REVIEW)

        # RDCO staff can see the record but have taken no part in its review.
        row = self.rows(self.tracker(record, self.rdco))[Party.ITSO]
        self.assertIsNone(row["seats"])


# --- what record detail offers --------------------------------------------------------------

class DetailFlagTests(OfficeReviewTestBase):

    def flag(self, record, user):
        self.client.force_authenticate(user)
        return self.client.get(detail_url(record)).data["office_review"]

    def test_a_seated_office_reviewer_is_offered_the_act(self):
        record = self.routed(Party.ITSO)
        seat = self.opened_seat(record, Party.ITSO, self.itso)

        flag = self.flag(record, self.itso)

        self.assertEqual(flag["party"], Party.ITSO)
        self.assertIsNone(flag["blocked"])
        self.assertEqual(flag["assignment"], seat.assignment_id)

    def test_an_unopened_seat_is_offered_but_blocked(self):
        record = self.routed(Party.ITSO)
        self.seat(record, Party.ITSO, self.itso)
        self.assertEqual(self.flag(record, self.itso)["blocked"], "Open the review first.")

    def test_nobody_else_is_offered_it(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        for user in (self.itso2, self.owner, self.adviser, self.rdco):
            self.assertIsNone(self.flag(record, user)["party"], user.email)


# --- the Add reviewer picklist ---------------------------------------------------------------

class AddReviewerOptionsTests(OfficeReviewTestBase):

    def test_a_seat_holder_sees_their_office_marked_by_who_is_seated(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.client.force_authenticate(self.itso)

        response = self.client.get(add_reviewer_url(self.assignment(record, Party.ITSO)))

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        members = {m["id"]: m["seated"] for m in response.data["members"]}
        self.assertEqual(members[self.itso.pk], True)
        self.assertEqual(members[self.itso2.pk], False)
        self.assertNotIn(self.ierc.pk, members)

    def test_anyone_not_seated_is_refused(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.client.force_authenticate(self.itso2)

        response = self.client.get(add_reviewer_url(self.assignment(record, Party.ITSO)))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
