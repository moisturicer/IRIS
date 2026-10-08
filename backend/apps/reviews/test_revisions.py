"""
A reviewer asks for a revision against the version they reviewed, and the
party that asked may withdraw it (IR-272).

ADR-032 §5 and its 2026-10-08 Amendment, at the REST seam IR-255 confirmed.
One class per acceptance criterion, then the decisions settled in the
2026-10-08 grilling. Records reach the new model through
`routing.enter_at_adviser` and the Adviser's accept & route, as in
`test_routing.py` and `test_office_review.py`.
"""

from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.documents.models import DocumentRequest
from apps.notifications.models import Notification
from apps.records.models import RecordVersion
from apps.reviews.models import (
    RecordAssignment,
    RecordClearance,
    ResubmissionRequest,
    Review,
    ReviewerSeat,
)
from core.enums import (
    ClearanceStatus,
    Party,
    PipelineStatus,
    RecordTypeName,
    ResubmissionRequestState,
    ReviewDecision,
    SeatState,
    WorkflowState,
)

from .test_office_review import CLEARED, OfficeReviewTestBase, detail_url

REASON = "The consent form does not cover participants under 18."


def request_url(record):
    return reverse("record-request-revision", args=[record.pk])


def withdraw_url(record, request_id):
    return reverse("record-withdraw-revision-request", args=[record.pk, request_id])


class RevisionTestBase(OfficeReviewTestBase):

    def ask(self, record, as_user, reason=REASON):
        return self.post(request_url(record), as_user, {"reason": reason})

    def asked(self, record, as_user, reason=REASON):
        response = self.ask(record, as_user, reason)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return ResubmissionRequest.objects.filter(record=record).latest("pk")

    def withdraw(self, record, as_user, request_id):
        return self.post(withdraw_url(record, request_id), as_user, {})

    def adviser_seat(self, record, *, opened=True):
        seat = ReviewerSeat.objects.get(
            assignment__record=record, assignment__party=Party.ADVISER, reviewer=self.adviser,
        )
        if opened:
            seat.state = SeatState.IN_REVIEW
            seat.opened_at = timezone.now()
            seat.save(update_fields=["state", "opened_at"])
        return seat

    def detail(self, record, as_user):
        self.client.force_authenticate(as_user)
        response = self.client.get(detail_url(record))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    def open_requests(self, record):
        return ResubmissionRequest.objects.filter(
            record=record, state=ResubmissionRequestState.OPEN,
        )


# --- AC: the request is visible -----------------------------------------------------

class RequestIsVisibleTests(RevisionTestBase):

    def test_ierc_asks_and_the_request_is_recorded_against_the_current_version(self):
        record = self.routed(Party.ITSO, Party.IERC)
        seat = self.opened_seat(record, Party.IERC, self.ierc)

        request = self.asked(record, self.ierc)

        self.assertEqual(request.state, ResubmissionRequestState.OPEN)
        self.assertEqual(request.party, Party.IERC)
        self.assertEqual(request.assignment, seat.assignment)
        self.assertEqual(request.requested_by, self.ierc)
        self.assertEqual(request.reason, REASON)
        # The seat holder's own review carries the request and its version.
        self.assertEqual(request.review.status, ReviewDecision.DECLINED)
        self.assertEqual(request.review.stage, Party.IERC)
        self.assertEqual(request.review.reviewed_by, self.ierc)
        current = RecordVersion.objects.filter(record=record).latest("number")
        self.assertEqual(request.review.version, current)

    def test_the_owner_sees_it_in_the_tracker_and_on_the_record(self):
        record = self.routed(Party.ITSO, Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)
        request = self.asked(record, self.ierc)

        tracker = self.tracker(record, self.owner)
        self.assertEqual(tracker["workflow_state"], WorkflowState.AWAITING_RESUBMISSION.value)
        [entry] = tracker["resubmissions"]
        self.assertEqual(
            (entry["id"], entry["party"], entry["state"], entry["reason"], entry["version"]),
            (request.pk, Party.IERC, ResubmissionRequestState.OPEN, REASON, 1),
        )
        self.assertEqual(entry["review"], request.review_id)

        # Record detail carries it for the owner's Action required.
        revision = self.detail(record, self.owner)["revision"]
        [shown] = revision["open"]
        self.assertEqual(
            (shown["id"], shown["party"], shown["label"], shown["reason"], shown["version"]),
            (request.pk, Party.IERC, "IERC", REASON, 1),
        )
        self.assertIsNone(revision["party"])  # the owner cannot ask

    def test_every_owner_is_notified_and_no_reviewer_is(self):
        record = self.routed(Party.ITSO, Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.opened_seat(record, Party.ITSO, self.itso)
        before = set(Notification.objects.values_list("pk", flat=True))

        with self.captureOnCommitCallbacks(execute=True):
            self.asked(record, self.ierc)

        new = Notification.objects.exclude(pk__in=before)
        self.assertEqual({n.recipient for n in new}, {self.owner})
        [notice] = new
        self.assertEqual(notice.notif_type.name, "Revision Requested")
        self.assertIn("IERC asked for a revision", notice.message)


# --- AC: concurrent requests ----------------------------------------------------------

class ConcurrentRequestTests(RevisionTestBase):

    def test_two_parties_each_hold_an_open_request_and_both_are_shown(self):
        record = self.routed(Party.ITSO, Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.opened_seat(record, Party.ITSO, self.itso)

        self.asked(record, self.ierc)
        self.asked(record, self.itso, "Describe the mechanism in claim form.")

        self.assertEqual(
            set(self.open_requests(record).values_list("party", flat=True)),
            {Party.IERC, Party.ITSO},
        )
        tracker = self.tracker(record, self.owner)
        self.assertEqual(
            {r["party"] for r in tracker["resubmissions"] if r["state"] == "open"},
            {Party.IERC, Party.ITSO},
        )
        self.assertEqual(
            {r["party"] for r in self.detail(record, self.owner)["revision"]["open"]},
            {Party.IERC, Party.ITSO},
        )
        rows = self.rows(tracker)
        self.assertTrue(rows[Party.IERC]["changes_requested"])
        self.assertTrue(rows[Party.ITSO]["changes_requested"])

    def test_a_party_asks_once_not_once_per_reviewer(self):
        """Decision 3: one open request per party, as ADR-022's party-not-person."""
        record = self.routed(Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.opened_seat(record, Party.IERC, self.ierc2)
        self.asked(record, self.ierc)

        response = self.ask(record, self.ierc2, "Also: the survey instrument.")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("A revision request from IERC is already open", response.data["detail"])
        self.assertEqual(self.open_requests(record).count(), 1)


# --- AC: blocked while open -------------------------------------------------------------

class BlockedWhileOpenTests(RevisionTestBase):

    def test_accept_and_route_is_refused_while_any_request_is_open(self):
        record = self.new_model()
        self.adviser_seat(record)
        self.asked(record, self.adviser)

        response = self.accept(record, [{"party": Party.ITSO}])

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Waiting on the author: Adviser asked for a revision", response.data["detail"])
        self.assertEqual(self.active(record), {Party.ADVISER})
        detail = self.detail(record, self.adviser)
        self.assertIn("Waiting on the author", detail["revision"]["decision_blocked"])

    def test_the_asking_office_may_neither_clear_nor_record_a_finding(self):
        """Decision 4: every seat of the asking office, not only the asker."""
        record = self.routed(Party.IERC, Party.ITSO)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.opened_seat(record, Party.IERC, self.ierc2)
        self.asked(record, self.ierc)

        for reviewer in (self.ierc, self.ierc2):
            for outcome, comment in ((CLEARED, ""), ("finding", "Minors are not covered.")):
                response = self.review(record, reviewer, outcome, comment)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, outcome)
                self.assertIn("IERC has asked the author for a revision", response.data["detail"])
        self.assertFalse(
            Review.objects.filter(record=record, stage=Party.IERC)
            .exclude(status=ReviewDecision.DECLINED).exists()
        )
        flags = self.detail(record, self.ierc2)["office_review"]
        self.assertIn("IERC has asked the author for a revision", flags["blocked"])

    def test_another_office_may_still_clear_and_record_findings(self):
        """Its outcome survives the new version (ADR-003), so nothing is gained by refusing it."""
        record = self.routed(Party.IERC, Party.ITSO, Party.KTTO)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.opened_seat(record, Party.KTTO, self.ktto)
        self.asked(record, self.ierc)

        self.cleared(record, self.itso, "No patentable mechanism.")
        self.found(record, self.ktto, "Licensing terms conflict with the sponsor's.")

        self.assertEqual(self.clearance(record, Party.ITSO), ClearanceStatus.CLEARED)
        self.assertEqual(self.clearance(record, Party.KTTO), ClearanceStatus.NOT_CLEARED)
        # IERC is still waiting on its revision, so RDCO has not opened.
        self.assertFalse(self.rdco_assignments(record).exists())

    def test_routing_and_document_requests_still_work(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.asked(record, self.itso)

        response = self.route(record, self.itso, [{"party": Party.IERC}])
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn(Party.IERC, self.active(record))

        self.client.force_authenticate(self.itso)
        response = self.client.post(
            reverse("record-document-requests", args=[record.pk]),
            {"message": "The invention disclosure form.", "items": [{"label": "Disclosure form"}]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(DocumentRequest.objects.filter(record=record, party=Party.ITSO).exists())


# --- AC: only the requester changes ------------------------------------------------------

class OnlyTheRequesterChangesTests(RevisionTestBase):

    def test_nothing_but_the_asking_party_reads_differently(self):
        record = self.routed(Party.ITSO, Party.IERC)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.cleared(record, self.itso)
        ierc_seat = self.opened_seat(record, Party.IERC, self.ierc)
        seats_before = dict(
            ReviewerSeat.objects.filter(assignment__record=record).values_list("pk", "state")
        )
        assignments_before = dict(
            RecordAssignment.objects.filter(record=record).values_list("pk", "state")
        )
        clearances_before = dict(
            RecordClearance.objects.filter(record=record).values_list("office", "status")
        )

        self.asked(record, self.ierc)

        self.assertEqual(
            dict(ReviewerSeat.objects.filter(assignment__record=record).values_list("pk", "state")),
            seats_before,
        )
        ierc_seat.refresh_from_db()
        self.assertEqual(ierc_seat.state, SeatState.IN_REVIEW)
        self.assertEqual(
            dict(RecordAssignment.objects.filter(record=record).values_list("pk", "state")),
            assignments_before,
        )
        # Decision 5: Changes requested is derived; no clearance is written.
        self.assertEqual(
            dict(RecordClearance.objects.filter(record=record).values_list("office", "status")),
            clearances_before,
        )
        rows = self.rows(self.tracker(record, self.owner))
        self.assertTrue(rows[Party.IERC]["changes_requested"])
        self.assertFalse(rows[Party.ITSO]["changes_requested"])
        self.assertEqual(rows[Party.ITSO]["outcome"], ClearanceStatus.CLEARED)

    def test_an_earlier_completed_round_still_stands_while_the_office_asks(self):
        """IR-269: the latest *completed* round wins, so asking writes no clearance."""
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.cleared(record, self.itso)
        # RDCO, opened by the hand-back, sends it back to ITSO for another look.
        self.opened_seat(record, Party.RDCO, self.rdco)
        response = self.route(record, self.rdco, [{"party": Party.ITSO}])
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.opened_seat(record, Party.ITSO, self.itso2)

        self.asked(record, self.itso2)

        self.assertEqual(self.clearance(record, Party.ITSO), ClearanceStatus.CLEARED)
        row = self.rows(self.tracker(record, self.owner))[Party.ITSO]
        self.assertTrue(row["changes_requested"])
        self.assertTrue(row["outcome_earlier"])


# --- AC: Adviser-stage revision ---------------------------------------------------------

class AdviserStageRevisionTests(RevisionTestBase):

    def assert_adviser_asked(self, record):
        seat = self.adviser_seat(record)
        request = self.asked(record, self.adviser)

        self.assertEqual(request.party, Party.ADVISER)
        seat.refresh_from_db()
        self.assertEqual(seat.state, SeatState.IN_REVIEW)
        self.assertEqual(self.active(record), {Party.ADVISER})
        self.assertEqual(
            self.tracker(record, self.owner)["workflow_state"],
            WorkflowState.AWAITING_RESUBMISSION.value,
        )
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)

    def test_on_a_thesis(self):
        self.assert_adviser_asked(self.new_model(RecordTypeName.THESIS_RESEARCH))

    def test_on_a_proposal(self):
        self.assert_adviser_asked(self.new_model(RecordTypeName.PROPOSAL))

    def test_rdco_may_ask_too(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.cleared(record, self.itso)
        self.opened_seat(record, Party.RDCO, self.rdco)

        request = self.asked(record, self.rdco)

        self.assertEqual(request.party, Party.RDCO)
        self.assertEqual(request.review.stage, Party.RDCO)


# --- AC: reason required --------------------------------------------------------------

class ReasonRequiredTests(RevisionTestBase):

    def test_a_blank_reason_is_refused_and_nothing_is_written(self):
        record = self.routed(Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)

        for reason in ("", "   ", None):
            response = self.ask(record, self.ierc, reason)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, reason)
            self.assertIn("Say what needs revising", response.data["detail"])
        self.assertFalse(ResubmissionRequest.objects.filter(record=record).exists())
        self.assertFalse(Review.objects.filter(record=record, stage=Party.IERC).exists())

    def test_the_reason_reaches_the_owner_exactly_as_written(self):
        """Plain text: stored and sent as typed, never as markup."""
        record = self.routed(Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)
        reason = "Section <b>3</b> & the appendix."

        self.asked(record, self.ierc, f"  {reason}\n")

        [shown] = self.detail(record, self.owner)["revision"]["open"]
        self.assertEqual(shown["reason"], reason)


# --- who may ask, and when -------------------------------------------------------------

class WhoMayAskTests(RevisionTestBase):

    def test_a_seat_must_be_opened_first(self):
        """Decision 2, IR-269's rule: the request is a review act."""
        record = self.routed(Party.IERC)
        self.seat(record, Party.IERC, self.ierc)

        self.assertEqual(self.detail(record, self.ierc)["revision"]["blocked"], "Open the review first.")
        response = self.ask(record, self.ierc)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Open the review first.")

    def test_a_reviewer_with_no_seat_here_is_refused(self):
        record = self.routed(Party.IERC)  # IERC's pool, unclaimed

        for caller in (self.ierc, self.itso, self.owner):
            response = self.ask(record, caller)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, caller.email)

    def test_a_record_the_caller_cannot_see_is_a_404(self):
        record = self.routed(Party.IERC)
        self.assertEqual(self.ask(record, self.stranger).status_code, status.HTTP_404_NOT_FOUND)

    def test_a_finished_seat_may_not_ask(self):
        record = self.routed(Party.ITSO, Party.IERC)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.cleared(record, self.itso)

        self.assertEqual(self.ask(record, self.itso).status_code, status.HTTP_403_FORBIDDEN)

    def test_a_legacy_record_uses_the_current_form(self):
        record = self.new_model()
        self.adviser_seat(record)
        record.pipeline_status = PipelineStatus.ADVISER_REVIEW
        record.save(update_fields=["pipeline_status"])

        response = self.ask(record, self.adviser)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("current review pipeline", response.data["detail"])
        self.assertIsNone(self.detail(record, self.adviser)["revision"]["party"])


# --- withdrawal (decision 7) ---------------------------------------------------------

class WithdrawTests(RevisionTestBase):

    def test_any_seat_holder_of_the_party_withdraws_and_the_record_moves_again(self):
        record = self.routed(Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.opened_seat(record, Party.IERC, self.ierc2)
        request = self.asked(record, self.ierc)
        self.assertEqual(
            self.detail(record, self.ierc2)["revision"]["withdrawable"], request.pk,
        )
        before = set(Notification.objects.values_list("pk", flat=True))

        with self.captureOnCommitCallbacks(execute=True):
            response = self.withdraw(record, self.ierc2, request.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        request.refresh_from_db()
        self.assertEqual(request.state, ResubmissionRequestState.WITHDRAWN)
        self.assertEqual(request.resolved_by, self.ierc2)
        self.assertIsNotNone(request.resolved_at)
        self.assertNotEqual(response.data["workflow_state"], WorkflowState.AWAITING_RESUBMISSION.value)
        notices = Notification.objects.exclude(pk__in=before)
        self.assertEqual({n.recipient for n in notices}, {self.owner})
        self.assertIn("IERC withdrew its revision request", notices.get().message)
        # IERC may finish its review again.
        self.cleared(record, self.ierc)

    def test_another_party_may_not_withdraw_it(self):
        record = self.routed(Party.IERC, Party.ITSO)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.opened_seat(record, Party.ITSO, self.itso)
        request = self.asked(record, self.ierc)

        for caller in (self.itso, self.owner, self.adviser):
            response = self.withdraw(record, caller, request.pk)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, caller.email)
        request.refresh_from_db()
        self.assertEqual(request.state, ResubmissionRequestState.OPEN)

    def test_only_an_open_request_and_only_on_this_record(self):
        record = self.routed(Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)
        request = self.asked(record, self.ierc)
        other = self.routed(Party.IERC)

        self.assertEqual(
            self.withdraw(other, self.ierc, request.pk).status_code, status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(self.withdraw(record, self.ierc, 999999).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.withdraw(record, self.ierc, request.pk).status_code, status.HTTP_200_OK)
        response = self.withdraw(record, self.ierc, request.pk)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Only an open revision request", response.data["detail"])

    def test_after_withdrawing_the_party_may_ask_again(self):
        record = self.routed(Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)
        first = self.asked(record, self.ierc)
        self.withdraw(record, self.ierc, first.pk)

        second = self.asked(record, self.ierc, "Only the assent form is missing.")

        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(self.open_requests(record).get(), second)
        self.assertEqual(self.detail(record, self.ierc)["revision"]["withdrawable"], second.pk)
