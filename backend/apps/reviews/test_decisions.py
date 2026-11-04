"""
The Adviser sends a Thesis/Project to RDCO or rejects it; only RDCO publishes and
decides it (IR-270, ADR-047).

ADR-032 §3 and §11, ADR-021 §12, at the REST seam IR-255 confirmed. One class
per acceptance criterion, then the decisions settled in the 2026-10-09
grilling (Jira comment 10586). Records reach the new model through
`routing.enter_at_adviser` and the Adviser's accept & route, and RDCO through
the real hand-back, as in `test_office_review.py`.
"""

from django.urls import reverse
from django.utils import timezone
from rest_framework import status


from apps.ai.policy.records import decision_for_record
from apps.documents.models import DocumentRequest
from apps.notifications.models import Notification
from apps.records.models import Record
from apps.records.testing import released_embargo
from apps.reviews import seats
from apps.reviews.models import RecordAssignment, RecordClearance, Review, ReviewerSeat
from core.enums import (
    AssignmentState,
    ClearanceStatus,
    DocumentRequestState,
    Party,
    PipelineStatus,
    RecordTypeName,
    ReviewDecision,
    RoleName,
    SeatState,
)

from .test_my_reviews import MINE
from .test_revisions import RevisionTestBase
from .workflow_test_helpers import make_user

COMMENT = "Sound method; nothing here needs an office."
REASON = "The study duplicates a thesis already published in 2023."


def decide_url(record):
    return reverse("record-decide", args=[record.pk])


class DecisionTestBase(RevisionTestBase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.other_adviser = make_user("decide-adviser2@cit.edu", RoleName.ADVISER)
        cls.reader = make_user("decide-reader@cit.edu", RoleName.STUDENT)

    def token(self, record, as_user):
        return self.detail(record, as_user)["decision"]["token"]

    def decide(self, record, as_user, outcome, comment="", token=None, *, release=True):
        if outcome == "publish" and release and token is None:
            # Every paper starts embargoed and an embargoed paper is never
            # published (IR-882), so release it as its Adviser would have during
            # review. `release=False` keeps it held, for the embargo's own tests.
            released_embargo(record.pk)
        if token is None:
            self.client.force_authenticate(as_user)
            response = self.client.get(reverse("record-detail", args=[record.pk]))
            token = (
                (response.data.get("decision") or {}).get("token")
                if response.status_code == status.HTTP_200_OK else None
            ) or "none"
        return self.post(
            decide_url(record), as_user,
            {"outcome": outcome, "comment": comment, "token": token},
        )

    def decided(self, record, as_user, outcome, comment=""):
        response = self.decide(record, as_user, outcome, comment)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        record.refresh_from_db()
        return response

    def publish_via_rdco(self, record, comment=""):
        """The only way to publish: the Adviser sends it to RDCO, which publishes it (ADR-047)."""
        self.accepted_to(record, Party.RDCO)
        self.opened_seat(record, Party.RDCO, self.rdco)
        return self.decided(record, self.rdco, "publish", comment)

    def at_adviser(self, type_name=RecordTypeName.THESIS_RESEARCH, **extra):
        """A new-model record, its Adviser's seat opened."""
        record = self.new_model(type_name, **extra)
        self.adviser_seat(record)
        return record

    def at_rdco(self):
        """
        A specialist-path Thesis RDCO holds: ITSO cleared it, the hand-back
        opened RDCO's pool, and `self.rdco` claimed and opened it.
        """
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.cleared(record, self.itso)
        rdco = RecordAssignment.objects.get(
            record=record, party=Party.RDCO, state=AssignmentState.ACTIVE,
        )
        seat = rdco.seats.get(reviewer=self.rdco)
        seats.open_review(seat, self.rdco)
        return record

    def listed(self, record, as_user):
        self.client.force_authenticate(as_user)
        response = self.client.get(reverse("record-list"), {"page_size": 100})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        return record.pk in {row["id"] for row in rows}

    def readable(self, record, as_user):
        self.client.force_authenticate(as_user)
        return self.client.get(reverse("record-detail", args=[record.pk])).status_code == 200


# --- AC: only RDCO publishes (ADR-047 §5) -------------------------------------------------

class OnlyRdcoPublishesTests(DecisionTestBase):

    def test_the_adviser_may_not_publish_a_thesis_or_project(self):
        for type_name in (RecordTypeName.THESIS_RESEARCH, RecordTypeName.PROJECT):
            with self.subTest(type_name):
                record = self.at_adviser(type_name)

                response = self.decide(record, self.adviser, "publish")

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("RDCO", response.data["detail"])
                record.refresh_from_db()
                self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)
                self.assertFalse(Review.objects.filter(record=record, stage=Party.ADVISER).exists())

    def test_the_adviser_is_offered_send_and_reject_never_publish(self):
        record = self.at_adviser()
        detail = self.detail(record, self.adviser)

        self.assertEqual(detail["decision"]["outcomes"], ["reject"])
        self.assertIn("send_to_rdco", detail["capabilities"])
        self.assertIn("reject", detail["capabilities"])
        self.assertNotIn("accept_publish", detail["capabilities"])

    def test_rdco_publishes_once_the_adviser_sends_it(self):
        record = self.at_adviser()

        self.publish_via_rdco(record, COMMENT)

        self.assertEqual(record.pipeline_status, PipelineStatus.PUBLISHED)
        review = Review.objects.get(record=record, stage=Party.RDCO)
        self.assertEqual(
            (review.status, review.reviewed_by, review.comment),
            (ReviewDecision.APPROVED, self.rdco, COMMENT),
        )
        rdco = RecordAssignment.objects.get(record=record, party=Party.RDCO)
        self.assertEqual(rdco.state, AssignmentState.COMPLETED)
        self.assertEqual(rdco.closed_by_decision, review)
        adviser = RecordAssignment.objects.get(record=record, party=Party.ADVISER)
        self.assertEqual(adviser.state, AssignmentState.COMPLETED)

    def test_any_signed_in_user_finds_it_in_discover_and_can_open_it(self):
        record = self.at_adviser()
        self.assertFalse(self.listed(record, self.reader))

        self.publish_via_rdco(record)

        self.assertTrue(self.listed(record, self.reader))
        self.assertTrue(self.readable(record, self.reader))
        # Ask IRIS retrieves through the one visibility predicate (CLAUDE.md).
        self.assertIn(record, Record.objects.visible_to(self.reader))

    def test_a_comment_is_optional(self):
        record = self.at_adviser()
        self.publish_via_rdco(record)
        self.assertEqual(Review.objects.get(record=record, stage=Party.RDCO).comment, "")

    def test_my_reviews_files_it_under_published(self):
        """IR-268's hand-off (Jira comment 10581)."""
        record = self.at_adviser()
        self.publish_via_rdco(record)

        self.client.force_authenticate(self.rdco)
        published = self.client.get(MINE, {"tab": "done", "outcome": "published"}).data["rows"]
        accepted = self.client.get(MINE, {"tab": "done", "outcome": "accepted"}).data["rows"]
        self.assertEqual([r["record"] for r in published], [record.pk])
        self.assertEqual(accepted, [])


# --- AC: the Adviser rejects -----------------------------------------------------------

class AdviserRejectsTests(DecisionTestBase):

    def test_rejected_archived_and_the_owner_is_told_why(self):
        record = self.at_adviser()

        with self.captureOnCommitCallbacks(execute=True):
            self.decided(record, self.adviser, "reject", REASON)

        self.assertEqual(record.pipeline_status, PipelineStatus.REJECTED)
        review = Review.objects.get(record=record, stage=Party.ADVISER)
        self.assertEqual((review.status, review.comment), (ReviewDecision.REJECTED, REASON))
        note = Notification.objects.get(record=record, recipient=self.owner)
        self.assertIn("rejected", note.message)
        self.assertIn(REASON, note.message)
        self.assertFalse(self.listed(record, self.reader))
        self.assertFalse(self.readable(record, self.reader))

    def test_readers_are_shown_it_as_archived(self):
        record = self.at_adviser()
        self.decided(record, self.adviser, "reject", REASON)
        self.assertEqual(self.detail(record, self.owner)["workflow_state_label"], "Archived")

    def test_a_rejection_needs_a_reason(self):
        record = self.at_adviser()

        response = self.decide(record, self.adviser, "reject", "   ")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)
        self.assertFalse(Review.objects.filter(record=record, stage=Party.ADVISER).exists())

    def test_the_adviser_cannot_keep_a_record_unlisted(self):
        record = self.at_adviser()
        response = self.decide(record, self.adviser, "keep_unlisted")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("RDCO", response.data["detail"])


# --- AC: the Adviser cannot decide after sending to RDCO --------------------------------------

class AfterRoutingTests(DecisionTestBase):

    def test_once_sent_to_rdco_the_adviser_may_not_reject(self):
        record = self.routed(Party.ITSO)

        response = self.decide(record, self.adviser, "reject", REASON)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("RDCO", response.data["detail"])
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)


# --- AC: RDCO's outcomes ---------------------------------------------------------------

class RdcoOutcomeTests(DecisionTestBase):

    def test_publish_lists_it(self):
        record = self.at_rdco()

        self.decided(record, self.rdco, "publish")

        self.assertEqual(record.pipeline_status, PipelineStatus.PUBLISHED)
        self.assertTrue(self.listed(record, self.reader))
        rdco = RecordAssignment.objects.get(record=record, party=Party.RDCO)
        self.assertEqual(rdco.state, AssignmentState.COMPLETED)

    def test_keep_unlisted_is_out_of_discover_but_its_participants_open_it(self):
        record = self.at_rdco()

        self.decided(record, self.rdco, "keep_unlisted", "Patent filing pending.")

        self.assertEqual(record.pipeline_status, PipelineStatus.COMPLETED)
        self.assertEqual(self.detail(record, self.owner)["workflow_state_label"], "Unlisted")
        self.assertFalse(self.listed(record, self.reader))
        self.assertFalse(self.readable(record, self.reader))
        self.assertNotIn(record, Record.objects.visible_to(self.reader))  # Ask IRIS too
        for participant in (self.owner, self.adviser, self.itso, self.rdco):
            with self.subTest(participant=participant.email):
                self.assertTrue(self.readable(record, participant))
        # My Reviews reads it as accepted, not published.
        self.client.force_authenticate(self.rdco)
        [row] = self.client.get(MINE, {"tab": "done"}).data["rows"]
        self.assertEqual(row["outcome"], "accepted")

    def test_reject_ends_the_workflow(self):
        record = self.at_rdco()

        self.decided(record, self.rdco, "reject", REASON)

        self.assertEqual(record.pipeline_status, PipelineStatus.REJECTED)
        self.assertFalse(
            RecordAssignment.objects.filter(record=record, state=AssignmentState.ACTIVE).exists()
        )
        review = Review.objects.get(record=record, stage=Party.RDCO)
        self.assertEqual(review.status, ReviewDecision.REJECTED)


# --- AC: a decision closes the record's open work ---------------------------------------

class OpenWorkClosesTests(DecisionTestBase):

    def busy_rdco(self):
        """
        RDCO holds the record with a second seat, and has sent it to IERC, whose
        reviewer has opened it and asked the owner for a document.
        """
        record = self.at_rdco()
        rdco = RecordAssignment.objects.get(
            record=record, party=Party.RDCO, state=AssignmentState.ACTIVE,
        )
        seats.add_reviewer(rdco, self.rdco, self.rdco2)
        response = self.route(record, self.rdco, [{"party": Party.IERC}])
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.opened_seat(record, Party.IERC, self.ierc)
        request = DocumentRequest.objects.create(
            record=record, party=Party.IERC, assignment=self.assignment(record, Party.IERC),
            requested_by=self.ierc, message="Signed consent forms, please.",
        )
        return record, request

    def test_every_other_assignment_seat_and_request_is_withdrawn(self):
        record, request = self.busy_rdco()

        self.decided(record, self.rdco, "publish")

        review = Review.objects.get(record=record, stage=Party.RDCO)
        ierc = RecordAssignment.objects.get(record=record, party=Party.IERC)
        self.assertEqual(
            (ierc.state, ierc.closed_by, ierc.closed_by_decision),
            (AssignmentState.WITHDRAWN, self.rdco, review),
        )
        self.assertEqual(ierc.seats.get().state, SeatState.WITHDRAWN)
        request.refresh_from_db()
        self.assertEqual(
            (request.state, request.closed_by_decision), (DocumentRequestState.WITHDRAWN, review),
        )
        self.assertIsNotNone(request.closed_at)
        # RDCO's own assignment completes; its second, unfinished seat is withdrawn.
        rdco = RecordAssignment.objects.get(record=record, party=Party.RDCO)
        self.assertEqual((rdco.state, rdco.closed_by_decision), (AssignmentState.COMPLETED, review))
        states = dict(rdco.seats.values_list("reviewer", "state"))
        self.assertEqual(
            states, {self.rdco.pk: SeatState.DONE, self.rdco2.pk: SeatState.WITHDRAWN},
        )

    def test_a_withdrawn_round_leaves_the_clearance_as_it_was(self):
        record, _ = self.busy_rdco()
        before = RecordClearance.objects.get(record=record, office=Party.IERC).status

        self.decided(record, self.rdco, "publish")

        self.assertEqual(self.clearance(record, Party.IERC), before)
        self.assertEqual(self.clearance(record, Party.ITSO), ClearanceStatus.CLEARED)

    def test_the_tracker_keeps_all_of_it(self):
        record, _ = self.busy_rdco()
        self.decided(record, self.rdco, "publish")

        tracker = self.tracker(record, self.owner)
        ierc = self.rows(tracker)[Party.IERC]
        self.assertEqual(ierc["state"], AssignmentState.WITHDRAWN)
        self.assertEqual(ierc["withdrawn_by_decision"], "RDCO published the record")
        self.assertEqual(
            [(s["reviewer_name"], s["state"]) for s in ierc["seats"]],
            [(self.ierc.get_full_name(), SeatState.WITHDRAWN)],
        )
        # IR-685: the sidebar shows what cut the seat short, in the server's words.
        self.assertEqual(ierc["seats"][0]["state_label"], "Closed by the Decision")
        # RDCO's own turn: the decider's seat done, the colleague's withdrawn.
        self.assertEqual(
            [s["state"] for s in self.rows(tracker)[Party.RDCO]["seats"]],
            [SeatState.DONE, SeatState.WITHDRAWN],
        )
        [document] = tracker["document_requests"]
        self.assertEqual(document["state"], DocumentRequestState.WITHDRAWN)
        # Who reviewed is still participants-only: a reader of the published
        # paper sees the outcome, not the names.
        reader_view = self.rows(self.tracker(record, self.reader))[Party.IERC]
        self.assertEqual(reader_view["withdrawn_by_decision"], "RDCO published the record")
        self.assertIsNone(reader_view["seats"])

    def test_a_seat_a_coordinator_withdrew_earlier_stays_out_of_the_tracker(self):
        """Code review: only the seats the Decision itself withdrew are its history."""
        record, _ = self.busy_rdco()
        earlier = ReviewerSeat.objects.create(
            assignment=self.assignment(record, Party.IERC), reviewer=self.ierc2,
            state=SeatState.WITHDRAWN,  # as `seats.withdraw` leaves it
        )

        self.decided(record, self.rdco, "publish")

        earlier.refresh_from_db()
        self.assertIsNone(earlier.closed_by_decision)
        ierc_seats = self.rows(self.tracker(record, self.owner))[Party.IERC]["seats"]
        self.assertEqual(len(ierc_seats), 1)
        cut = ReviewerSeat.objects.get(assignment__record=record, reviewer=self.ierc)
        self.assertEqual(cut.closed_by_decision, Review.objects.get(record=record, stage=Party.RDCO))

    def test_a_document_request_racing_the_decision_is_refused_after_it(self):
        """
        Code review: `create_request` re-checks, under the record lock a Decision
        also takes, that its party still holds the record.
        """
        from apps.documents import requests as document_requests

        record, _ = self.busy_rdco()
        self.decided(record, self.rdco, "publish")

        with self.assertRaises(document_requests.NotAHolder):
            document_requests.create_request(
                record, self.ierc, party=Party.IERC, message="One more form.", specs=[],
            )
        self.assertFalse(
            DocumentRequest.objects.filter(record=record, state=DocumentRequestState.OPEN).exists()
        )

    def test_the_owners_and_the_reviewers_cut_off_are_told(self):
        record, _ = self.busy_rdco()
        before = set(Notification.objects.values_list("pk", flat=True))

        with self.captureOnCommitCallbacks(execute=True):
            self.decided(record, self.rdco, "publish")

        new = Notification.objects.exclude(pk__in=before).filter(record=record)
        self.assertEqual({n.recipient for n in new}, {self.owner, self.ierc, self.rdco2})
        self.assertEqual(new.filter(recipient=self.owner).count(), 1)
        self.assertIn("document request", new.get(recipient=self.owner).message)

    def test_the_deciders_own_document_request_is_withdrawn_not_refused(self):
        record = self.at_adviser()
        request = DocumentRequest.objects.create(
            record=record, party=Party.ADVISER, assignment=self.assignment(record, Party.ADVISER),
            requested_by=self.adviser, message="The signed approval sheet.",
        )

        self.decided(record, self.adviser, "reject", REASON)

        request.refresh_from_db()
        self.assertEqual(request.state, DocumentRequestState.WITHDRAWN)


# --- AC: refused while a revision is open ------------------------------------------------

class RevisionOpenTests(DecisionTestBase):

    def test_rdco_can_decide_over_its_own_open_revision_request(self):
        record = self.at_rdco()
        request = self.asked(record, self.rdco)
        response = self.decide(record, self.rdco, "publish")
        self.assertEqual(response.status_code, 200, response.data)
        request.refresh_from_db()
        self.assertEqual(request.state, "withdrawn")
        self.assertIsNotNone(request.closed_by_decision_id)


# --- AC: refusals ------------------------------------------------------------------------

class RefusalTests(DecisionTestBase):

    def test_offices_are_refused(self):
        record = self.routed(Party.ITSO, Party.IERC)
        self.opened_seat(record, Party.ITSO, self.itso)

        response = self.decide(record, self.itso, "publish")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_an_adviser_who_is_not_the_records_adviser_is_refused(self):
        """
        Refused as a missing record: another Adviser cannot see an unpublished
        record at all, so the API never confirms it exists (IR-153).
        """
        record = self.at_adviser()
        response = self.decide(record, self.other_adviser, "publish", token="x")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_an_rdco_member_without_a_seat_must_claim_first(self):
        record = self.at_rdco()
        response = self.decide(record, self.rdco2, "publish")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Claim", response.data["detail"])

    def test_the_adviser_may_not_decide_an_rdco_held_record(self):
        record = self.at_rdco()
        response = self.decide(record, self.adviser, "publish")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_the_owner_is_refused(self):
        record = self.at_adviser()
        response = self.decide(record, self.owner, "publish")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_an_unopened_seat_is_refused(self):
        record = self.new_model()
        response = self.decide(record, self.adviser, "reject", REASON)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Open the review first", response.data["detail"])

    def test_an_unknown_outcome_is_refused(self):
        record = self.at_adviser()
        response = self.decide(record, self.adviser, "approve")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_proposal_is_refused(self):
        record = self.at_adviser(RecordTypeName.PROPOSAL)
        response = self.decide(record, self.adviser, "publish")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)

    def test_a_record_not_in_review_is_refused(self):
        """IR-274: this was asked of a record still holding a fixed-pipeline status. Those statuses are gone; the refusal they exercised -- a record not in review -- is asked of a draft record instead."""
        record = self.make_record()
        self.assertEqual(record.pipeline_status, PipelineStatus.DRAFT)
        response = self.decide(record, self.adviser, "publish", token="x")
        self.assertIn(
            response.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN),
        )
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.DRAFT)

    def test_a_decided_record_cannot_be_decided_again(self):
        record = self.at_adviser()
        token = self.token(record, self.adviser)
        self.decided(record, self.adviser, "reject", REASON)

        response = self.decide(record, self.adviser, "reject", REASON, token=token)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.REJECTED)


# --- decision 11: a stale dialog never decides into a changed state ----------------------

class StaleTests(DecisionTestBase):

    def test_a_missing_token_is_refused(self):
        record = self.at_adviser()
        self.client.force_authenticate(self.adviser)
        response = self.client.post(decide_url(record), {"outcome": "publish"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_record_that_moved_is_a_409_describing_what_it_would_now_close(self):
        record = self.at_rdco()
        released_embargo(record.pk)
        token = self.token(record, self.rdco)
        # While RDCO's dialog is open, RDCO's colleague sends it to IERC.
        seats.add_reviewer(
            RecordAssignment.objects.get(record=record, party=Party.RDCO, state=AssignmentState.ACTIVE),
            self.rdco, self.rdco2,
        )
        seats.open_review(
            ReviewerSeat.objects.get(assignment__record=record, reviewer=self.rdco2), self.rdco2,
        )
        self.assertEqual(self.route(record, self.rdco2, [{"party": Party.IERC}]).status_code, 200)

        response = self.decide(record, self.rdco, "publish", token=token)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("changed", response.data["detail"])
        closes = response.data["decision"]["closes"]
        self.assertIn(Party.IERC, [a["party"] for a in closes["assignments"]])
        self.assertNotEqual(response.data["decision"]["token"], token)
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)
        self.assertFalse(Review.objects.filter(record=record, stage=Party.RDCO).exists())

    def test_a_document_request_opened_meanwhile_also_counts(self):
        record = self.at_adviser()
        token = self.token(record, self.adviser)
        DocumentRequest.objects.create(
            record=record, party=Party.ADVISER, assignment=self.assignment(record, Party.ADVISER),
            requested_by=self.adviser, message="The approval sheet.",
        )
        response = self.decide(record, self.adviser, "reject", REASON, token=token)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)


# --- decision 10: what record detail tells Paper View ------------------------------------

class DetailFlagTests(DecisionTestBase):

    def flag(self, record, user):
        return self.detail(record, user)["decision"]

    def test_the_adviser_is_offered_only_reject_with_the_authors_hints(self):
        record = self.at_adviser(is_ip=True)

        flag = self.flag(record, self.adviser)

        self.assertEqual(flag["outcomes"], ["reject"])
        self.assertEqual(flag["party"], Party.ADVISER)
        self.assertIsNone(flag["blocked"])
        self.assertTrue(flag["token"])
        self.assertEqual(flag["closes"], {"assignments": [], "document_requests": 0, "revision_requests": [], "findings": []})
        self.assertEqual(flag["author_hints"], ["The author flagged possible intellectual property."])

    def test_rdco_is_offered_all_three_and_told_what_closes(self):
        record = self.at_rdco()
        released_embargo(record.pk)  # an embargoed paper offers no publish (IR-882)
        seats.add_reviewer(
            RecordAssignment.objects.get(record=record, party=Party.RDCO, state=AssignmentState.ACTIVE),
            self.rdco, self.rdco2,
        )

        flag = self.flag(record, self.rdco)

        self.assertEqual(flag["outcomes"], ["publish", "keep_unlisted", "reject"])
        self.assertEqual(flag["author_hints"], [])
        self.assertEqual(
            flag["closes"]["assignments"],
            [{
                "party": Party.RDCO, "label": seats._label(Party.RDCO),
                "holders": [self.rdco2.get_full_name()],
            }],
        )

    def test_an_unopened_seat_is_offered_but_blocked(self):
        record = self.new_model()
        flag = self.flag(record, self.adviser)
        self.assertEqual(flag["outcomes"], ["reject"])
        self.assertEqual(flag["blocked"], "Open the review first.")

    def test_an_open_revision_request_blocks_with_its_reason(self):
        record = self.at_adviser()
        self.asked(record, self.adviser)
        self.assertIn("Waiting on the author", self.flag(record, self.adviser)["blocked"])

    def test_nobody_else_is_offered_a_decision(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        for user in (self.owner, self.itso, self.adviser):
            with self.subTest(user=user.email):
                flag = self.flag(record, user)
                self.assertEqual(flag["outcomes"], [])
                self.assertIsNone(flag["token"])
                self.assertIsNone(flag["closes"])


# --- ADR-052 decision 14 as amended: an embargo stops publishing (IR-818, IR-882) --------

class EmbargoAtDecisionTests(DecisionTestBase):
    """
    Every paper starts embargoed, and RDCO publishes only a released one. While it
    is held, RDCO keeps it unlisted or rejects it, and is told to release it first.
    """

    UNTIL = "2099-01-01"

    def dated(self, record):
        Record.objects.filter(pk=record.pk).update(
            embargo_date_set_at=timezone.now(), embargoed_until=self.UNTIL,
            dpa_accepted_at=timezone.now(),
        )
        record.refresh_from_db()
        return record

    def test_rdco_s_flags_carry_the_embargo(self):
        record = self.dated(self.at_rdco())

        flag = self.detail(record, self.rdco)["decision"]

        self.assertEqual(flag["embargo"], {"state": "active", "until": self.UNTIL})

    def test_the_adviser_s_flags_carry_none(self):
        record = self.dated(self.at_adviser())

        self.assertIsNone(self.detail(record, self.adviser)["decision"]["embargo"])

    def test_a_viewer_who_decides_nothing_is_told_nothing(self):
        record = self.dated(self.at_rdco())

        self.assertIsNone(self.detail(record, self.itso)["decision"]["embargo"])

    def test_an_embargoed_paper_offers_no_publish(self):
        for name, prepare in {"undated": lambda r: r, "dated": self.dated}.items():
            with self.subTest(name):
                record = prepare(self.at_rdco())

                flag = self.detail(record, self.rdco)["decision"]

                self.assertEqual(flag["outcomes"], ["keep_unlisted", "reject"])

    def test_publishing_an_embargoed_paper_is_refused_and_says_why(self):
        cases = {"undated": (lambda r: r, "Under embargo. Release"),
                 "dated": (self.dated, "Under embargo until 01 Jan 2099. Release")}
        for name, (prepare, words) in cases.items():
            with self.subTest(name):
                record = prepare(self.at_rdco())

                response = self.decide(record, self.rdco, "publish", release=False)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
                self.assertIn(words, response.data["detail"])
                record.refresh_from_db()
                self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)
                self.assertFalse(Review.objects.filter(record=record, reviewed_by=self.rdco).exists())

    def test_rdco_can_keep_it_unlisted_or_reject_it_while_embargoed(self):
        expected = {
            "keep_unlisted": PipelineStatus.COMPLETED,
            "reject": PipelineStatus.REJECTED,
        }
        for outcome, pipeline in expected.items():
            with self.subTest(outcome=outcome):
                record = self.dated(self.at_rdco())

                self.decided(record, self.rdco, outcome, REASON)

                self.assertEqual(record.pipeline_status, pipeline)
                self.assertTrue(record.is_embargoed)

    def test_once_released_rdco_publishes_it(self):
        for releaser in ("adviser", "rdco"):
            with self.subTest(releaser=releaser):
                record = self.dated(self.at_rdco())
                released = self.post(
                    reverse("record-embargo-release", args=[record.pk]), getattr(self, releaser), {},
                )
                self.assertEqual(released.status_code, status.HTTP_200_OK, released.data)

                self.assertIn("publish", self.detail(record, self.rdco)["decision"]["outcomes"])
                self.decided(record, self.rdco, "publish")

                self.assertEqual(record.pipeline_status, PipelineStatus.PUBLISHED)
                self.assertEqual(decision_for_record(record).reasons, ())

    def test_an_embargo_set_while_the_dialog_is_open_makes_it_stale(self):
        record = self.at_rdco()
        released_embargo(record.pk)
        token = self.token(record, self.rdco)
        self.assertEqual(self.detail(record, self.rdco)["decision"]["embargo"]["state"], "released")

        set_ = self.post(
            reverse("record-embargo-set", args=[record.pk]), self.adviser,
            {"embargoed_until": self.UNTIL},
        )
        self.assertEqual(set_.status_code, status.HTTP_200_OK, set_.data)
        response = self.decide(record, self.rdco, "keep_unlisted", token=token)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["decision"]["embargo"], {"state": "active", "until": self.UNTIL})
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)
