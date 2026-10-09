"""
The Adviser accepts & publishes or rejects a Thesis/Project; RDCO decides
specialist-path records (IR-270).

ADR-032 §3 and §11, ADR-021 §12, at the REST seam IR-255 confirmed. One class
per acceptance criterion, then the decisions settled in the 2026-10-09
grilling (Jira comment 10586). Records reach the new model through
`routing.enter_at_adviser` and the Adviser's accept & route, and RDCO through
the real hand-back, as in `test_office_review.py`.
"""

from django.urls import reverse
from rest_framework import status

from apps.documents.models import DocumentRequest
from apps.notifications.models import Notification
from apps.records.models import Record
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
from .test_workflow_characterisation import make_user

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

    def decide(self, record, as_user, outcome, comment="", token=None):
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
        seat = seats.claim(rdco, self.rdco)
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


# --- AC: the Adviser publishes ------------------------------------------------------

class AdviserPublishesTests(DecisionTestBase):

    def test_published_and_no_rdco_assignment_was_ever_created(self):
        record = self.at_adviser()

        self.decided(record, self.adviser, "publish", COMMENT)

        self.assertEqual(record.pipeline_status, PipelineStatus.PUBLISHED)
        self.assertFalse(RecordAssignment.objects.filter(record=record, party=Party.RDCO).exists())
        review = Review.objects.get(record=record, stage=Party.ADVISER)
        self.assertEqual(
            (review.status, review.reviewed_by, review.comment),
            (ReviewDecision.APPROVED, self.adviser, COMMENT),
        )
        self.assertEqual(review.version.number, 1)
        assignment = RecordAssignment.objects.get(record=record, party=Party.ADVISER)
        self.assertEqual(assignment.state, AssignmentState.COMPLETED)
        self.assertEqual(assignment.closed_by_decision, review)
        self.assertEqual(assignment.seats.get().state, SeatState.DONE)

    def test_any_signed_in_user_finds_it_in_discover_and_can_open_it(self):
        record = self.at_adviser()
        self.assertFalse(self.listed(record, self.reader))

        self.decided(record, self.adviser, "publish")

        self.assertTrue(self.listed(record, self.reader))
        self.assertTrue(self.readable(record, self.reader))
        # Ask IRIS retrieves through the one visibility predicate (CLAUDE.md).
        self.assertIn(record, Record.objects.visible_to(self.reader))

    def test_a_comment_is_optional(self):
        record = self.at_adviser()
        self.decided(record, self.adviser, "publish")
        self.assertEqual(Review.objects.get(record=record, stage=Party.ADVISER).comment, "")

    def test_my_reviews_files_it_under_published(self):
        """IR-268's hand-off (Jira comment 10581)."""
        record = self.at_adviser()
        self.decided(record, self.adviser, "publish")

        self.client.force_authenticate(self.adviser)
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


# --- AC: the Adviser cannot publish after routing --------------------------------------

class AfterRoutingTests(DecisionTestBase):

    def test_once_accepted_and_routed_the_adviser_may_not_publish(self):
        record = self.routed(Party.ITSO)

        response = self.decide(record, self.adviser, "publish")

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

        self.decided(record, self.adviser, "publish")

        request.refresh_from_db()
        self.assertEqual(request.state, DocumentRequestState.WITHDRAWN)


# --- AC: refused while a revision is open ------------------------------------------------

class RevisionOpenTests(DecisionTestBase):

    def test_deciding_with_an_open_revision_request_is_refused_and_explained(self):
        record = self.at_rdco()
        self.asked(record, self.rdco)

        for outcome, comment in (("publish", ""), ("keep_unlisted", ""), ("reject", REASON)):
            with self.subTest(outcome=outcome):
                response = self.decide(record, self.rdco, outcome, comment)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("Waiting on the author", response.data["detail"])
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)


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
        response = self.decide(record, self.adviser, "publish")
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

    def test_a_legacy_record_is_refused(self):
        record = self.make_record()
        record.pipeline_status = PipelineStatus.ADVISER_REVIEW
        record.save(update_fields=["pipeline_status"])
        response = self.decide(record, self.adviser, "publish", token="x")
        self.assertIn(
            response.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN),
        )
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.ADVISER_REVIEW)

    def test_a_decided_record_cannot_be_decided_again(self):
        record = self.at_adviser()
        token = self.token(record, self.adviser)
        self.decided(record, self.adviser, "publish")

        response = self.decide(record, self.adviser, "reject", REASON, token=token)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.PUBLISHED)


# --- decision 11: a stale dialog never decides into a changed state ----------------------

class StaleTests(DecisionTestBase):

    def test_a_missing_token_is_refused(self):
        record = self.at_adviser()
        self.client.force_authenticate(self.adviser)
        response = self.client.post(decide_url(record), {"outcome": "publish"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_record_that_moved_is_a_409_describing_what_it_would_now_close(self):
        record = self.at_rdco()
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
        response = self.decide(record, self.adviser, "publish", token=token)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)


# --- decision 10: what record detail tells Paper View ------------------------------------

class DetailFlagTests(DecisionTestBase):

    def flag(self, record, user):
        return self.detail(record, user)["decision"]

    def test_the_adviser_is_offered_publish_and_reject_with_the_authors_hints(self):
        record = self.at_adviser(requested_itso=True)

        flag = self.flag(record, self.adviser)

        self.assertEqual(flag["outcomes"], ["publish", "reject"])
        self.assertEqual(flag["party"], Party.ADVISER)
        self.assertIsNone(flag["blocked"])
        self.assertTrue(flag["token"])
        self.assertEqual(flag["closes"], {"assignments": [], "document_requests": 0})
        self.assertEqual(flag["author_hints"], ["The author flagged possible intellectual property."])

    def test_rdco_is_offered_all_three_and_told_what_closes(self):
        record = self.at_rdco()
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
        self.assertEqual(flag["outcomes"], ["publish", "reject"])
        self.assertEqual(flag["blocked"], "Open the review first.")

    def test_an_open_revision_request_blocks_with_its_reason(self):
        record = self.at_adviser()
        self.asked(record, self.adviser)
        self.assertIn("Waiting on the author", self.flag(record, self.adviser)["blocked"])

    def test_nobody_else_is_offered_a_decision(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        for user in (self.owner, self.itso, self.adviser, self.rdco):
            with self.subTest(user=user.email):
                flag = self.flag(record, user)
                self.assertEqual(flag["outcomes"], [])
                self.assertIsNone(flag["token"])
                self.assertIsNone(flag["closes"])
