"""
The Adviser alone decides a Proposal: accept, reject (Archived) or request a
revision (IR-271; ADR-032 §2).

At the REST seam IR-255 confirmed, on IR-270's `decide/` and its test base.
One class per acceptance criterion, then the decisions settled in the
2026-10-09 grilling (Jira comment 10589). A Proposal reaches the new model
through `routing.enter_at_adviser`; it is never routed (ADR-032 §2), so its
Adviser's seat is the only one it ever has.
"""

from django.urls import reverse
from rest_framework import status

from apps.documents.models import DocumentRequest
from apps.notifications.models import Notification
from apps.records.models import Record
from apps.reviews.models import RecordAssignment, Review
from core.enums import (
    AssignmentState,
    DocumentRequestState,
    Party,
    PipelineStatus,
    RecordTypeName,
    ReviewDecision,
    SeatState,
)

from .test_decisions import REASON, DecisionTestBase
from .test_my_reviews import MINE

PROPOSAL = RecordTypeName.PROPOSAL


class ProposalTestBase(DecisionTestBase):

    def proposal(self):
        """A new-model Proposal at its Adviser, the review opened."""
        return self.at_adviser(PROPOSAL)


# --- AC: accept ------------------------------------------------------------------------

class AcceptTests(ProposalTestBase):

    def test_the_adviser_accepts_and_it_rests_approved_with_no_rdco(self):
        record = self.proposal()

        self.decided(record, self.adviser, "accept", "A sound plan; proceed.")

        self.assertEqual(record.pipeline_status, PipelineStatus.APPROVED)
        self.assertFalse(RecordAssignment.objects.filter(record=record, party=Party.RDCO).exists())
        review = Review.objects.get(record=record, stage=Party.ADVISER)
        self.assertEqual(
            (review.status, review.comment), (ReviewDecision.APPROVED, "A sound plan; proceed."),
        )
        assignment = RecordAssignment.objects.get(record=record, party=Party.ADVISER)
        self.assertEqual(
            (assignment.state, assignment.closed_by_decision),
            (AssignmentState.COMPLETED, review),
        )
        self.assertEqual(assignment.seats.get().state, SeatState.DONE)

    def test_it_is_not_in_discover_and_reads_as_accepted(self):
        record = self.proposal()
        self.decided(record, self.adviser, "accept")

        self.assertFalse(self.listed(record, self.reader))
        self.assertFalse(self.readable(record, self.reader))
        self.assertNotIn(record, Record.objects.visible_to(self.reader))
        self.assertEqual(self.detail(record, self.owner)["workflow_state_label"], "Accepted")

    def test_my_reviews_files_it_under_accepted(self):
        record = self.proposal()
        self.decided(record, self.adviser, "accept")

        self.client.force_authenticate(self.adviser)
        accepted = self.client.get(MINE, {"tab": "done", "outcome": "accepted"}).data["rows"]
        self.assertEqual([r["record"] for r in accepted], [record.pk])

    def test_the_owner_is_told(self):
        record = self.proposal()
        with self.captureOnCommitCallbacks(execute=True):
            self.decided(record, self.adviser, "accept")
        note = Notification.objects.get(record=record, recipient=self.owner)
        self.assertIn("accepted", note.message)
        self.assertIn(record.title, note.message)

    def test_the_advisers_own_document_request_is_withdrawn(self):
        record = self.proposal()
        request = DocumentRequest.objects.create(
            record=record, party=Party.ADVISER, assignment=self.assignment(record, Party.ADVISER),
            requested_by=self.adviser, message="The signed endorsement form.",
        )

        self.decided(record, self.adviser, "accept")

        request.refresh_from_db()
        self.assertEqual(request.state, DocumentRequestState.WITHDRAWN)
        self.assertIsNotNone(request.closed_by_decision)


# --- AC: reject ------------------------------------------------------------------------

class RejectTests(ProposalTestBase):

    def test_rejected_reads_archived_and_a_later_resubmission_is_refused(self):
        record = self.proposal()

        self.decided(record, self.adviser, "reject", REASON)

        self.assertEqual(record.pipeline_status, PipelineStatus.REJECTED)
        self.assertEqual(self.detail(record, self.owner)["workflow_state_label"], "Archived")
        response = self.post(reverse("record-new-version", args=[record.pk]), self.owner, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.REJECTED)

    def test_a_rejection_needs_a_reason(self):
        record = self.proposal()
        response = self.decide(record, self.adviser, "reject", "")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# --- the outcomes belong to the record type ---------------------------------------------

class OutcomeTests(ProposalTestBase):

    def test_a_proposal_is_never_published_or_kept_unlisted(self):
        record = self.proposal()
        for outcome in ("publish", "keep_unlisted"):
            with self.subTest(outcome=outcome):
                response = self.decide(record, self.adviser, outcome)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("Proposal", response.data["detail"])
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)

    def test_a_thesis_is_not_accepted_as_a_proposal_is(self):
        record = self.at_adviser()
        response = self.decide(record, self.adviser, "accept")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)


# --- IR-272 hand-off: refused while a revision is open ---------------------------------

class RevisionOpenTests(ProposalTestBase):

    def test_accept_and_reject_wait_on_an_open_revision_request(self):
        record = self.proposal()
        self.asked(record, self.adviser)

        for outcome, comment in (("accept", ""), ("reject", REASON)):
            with self.subTest(outcome=outcome):
                response = self.decide(record, self.adviser, outcome, comment)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("Waiting on the author", response.data["detail"])
        self.assertIn("Waiting on the author", self.detail(record, self.adviser)["decision"]["blocked"])


# --- AC: refusals ----------------------------------------------------------------------

class RefusalTests(ProposalTestBase):

    def test_an_unassigned_adviser_is_refused_as_a_missing_record(self):
        record = self.proposal()
        response = self.decide(record, self.other_adviser, "accept", token="x")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_rdco_and_the_offices_are_refused(self):
        record = self.proposal()
        for user in (self.rdco, self.itso, self.ierc, self.ktto):
            with self.subTest(user=user.email):
                response = self.decide(record, user, "accept", token="x")
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)

    def test_the_owner_is_refused(self):
        record = self.proposal()
        response = self.decide(record, self.owner, "accept", token="x")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# --- what record detail tells Paper View -----------------------------------------------

class DetailFlagTests(ProposalTestBase):

    def test_the_adviser_is_offered_accept_and_reject(self):
        record = self.proposal()
        flag = self.detail(record, self.adviser)["decision"]
        self.assertEqual(flag["party"], Party.ADVISER)
        self.assertEqual(flag["outcomes"], ["accept", "reject"])
        self.assertIsNone(flag["blocked"])
        self.assertEqual(flag["author_hints"], [])
        self.assertTrue(flag["token"])

    def test_nobody_else_is_offered_a_decision(self):
        record = self.proposal()
        for user in (self.owner, self.rdco, self.itso):
            with self.subTest(user=user.email):
                self.assertEqual(self.detail(record, user)["decision"]["outcomes"], [])
