"""
Reviewer names and review comments are read by participants only (IR-479).

ADR-032 §10, as amended 2026-10-08. Reading a record -- every office member
reads every record, every signed-in user reads a published one -- is not
enough to read who reviewed it and what they wrote. `may_read_review` decides:
an owner, anyone who has ever held a seat, or a member of an office whose
assignment on the record is active now. Everyone else gets `None` in each
field that carries review content, and still sees the outcomes.

One class per acceptance criterion, at the REST seam: record detail and the
tracker, the two routes that serve it.
"""

from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.records.models import Record
from apps.reviews.models import RecordAssignment, ResubmissionRequest, Review
from core.enums import (
    AssignmentState,
    ClearanceStatus,
    Party,
    PipelineStatus,
    ResubmissionRequestState,
    ReviewDecision,
    RoleName,
)

from .test_office_review import OfficeReviewTestBase
from .workflow_test_helpers import make_user


class ReviewPrivacyTestBase(OfficeReviewTestBase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.ktto_member = make_user("privacy-ktto@cit.edu", RoleName.KTTO)

    def reviewed(self):
        """
        A Thesis the Adviser routed to ITSO and IERC with a reason. ITSO
        cleared it with a comment, and a resubmission request IERC made has
        since been answered: every kind of review content, in one record.
        """
        record = self.routed(Party.ITSO, Party.IERC)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.cleared(record, self.itso, "No patentable mechanism.")
        ierc = self.assignment(record, Party.IERC)
        declined = Review.objects.create(
            record=record, reviewed_by=self.ierc, stage=Party.IERC,
            status=ReviewDecision.DECLINED, comment="Consent form is missing.",
            assignment=ierc,
        )
        ResubmissionRequest.objects.create(
            record=record, party=Party.IERC, assignment=ierc, review=declined,
            requested_by=self.ierc, reason="Consent form is missing.",
            state=ResubmissionRequestState.RESUBMITTED,
            resolved_by=self.owner, resolved_at=timezone.now(),
        )
        return record

    def published(self, record):
        Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.PUBLISHED)
        record.refresh_from_db()
        return record

    def get(self, name, record, user):
        self.client.force_authenticate(user)
        response = self.client.get(reverse(name, args=[record.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    def detail(self, record, user):
        return self.get("record-detail", record, user)

    def tracker(self, record, user=None):
        return self.get("record-tracker", record, user or self.owner)

    # --- the two readings --------------------------------------------------------

    def assertNothingDisclosed(self, record, user):
        detail = self.detail(record, user)
        self.assertIsNone(detail["reviews"])
        for clearance in detail["clearances"]:
            self.assertIsNone(clearance["comment"], clearance["office"])
            self.assertIsNone(clearance["reviewed_by_name"], clearance["office"])
        for holder in detail["current_holders"]:
            self.assertIsNone(holder["opened_by"], holder["party"])

        tracker = self.tracker(record, user)
        self.assertIsNone(tracker["reviews"])
        for clearance in tracker["clearances"]:
            self.assertIsNone(clearance["comment"])
            self.assertIsNone(clearance["reviewed_by_name"])
        for holder in tracker["current_holders"]:
            self.assertIsNone(holder["opened_by"])
        for movement in tracker["routing_history"]:
            self.assertIsNone(movement["actor"])
            self.assertIsNone(movement["reason"])
        self.assertTrue(tracker["resubmissions"], "the request itself is still listed")
        for request in tracker["resubmissions"]:
            self.assertIsNone(request["reason"])
            self.assertIsNone(request["requested_by"])
            self.assertIsNone(request["resolved_by"])
        for row in tracker["parties"]:
            self.assertIsNone(row["seats"], row["party"])

        # What happened stays visible: where the record went, and how each
        # office concluded.
        self.assertEqual(self.rows(tracker)[Party.ITSO]["outcome"], ClearanceStatus.CLEARED)
        self.assertEqual(
            {c["office"]: c["status"] for c in detail["clearances"]}[Party.ITSO],
            ClearanceStatus.CLEARED,
        )
        self.assertTrue(any(m["to"] for m in tracker["routing_history"]))
        self.assertIn("workflow_state", tracker)

    def assertEverythingDisclosed(self, record, user):
        detail = self.detail(record, user)
        comments = {r["comment"] for r in detail["reviews"]}
        self.assertIn("No patentable mechanism.", comments)
        self.assertIn("Consent form is missing.", comments)

        tracker = self.tracker(record, user)
        self.assertTrue(tracker["reviews"])
        self.assertEqual(tracker["resubmissions"][0]["reason"], "Consent form is missing.")
        self.assertEqual(tracker["resubmissions"][0]["requested_by"], self.ierc.get_full_name())
        from_adviser = [m for m in tracker["routing_history"] if m["from"] == Party.ADVISER]
        self.assertEqual(from_adviser[0]["actor"], self.adviser.get_full_name())
        self.assertTrue(from_adviser[0]["reason"])


# --- AC: a student reading a published record ------------------------------------------

class PublishedRecordTests(ReviewPrivacyTestBase):

    def test_a_student_reading_a_published_record_is_told_the_outcome_and_nothing_else(self):
        record = self.published(self.reviewed())
        self.assertNothingDisclosed(record, self.stranger)


# --- AC: an office not taking part, and RDCO --------------------------------------------

class OfficeNotTakingPartTests(ReviewPrivacyTestBase):

    def test_an_office_member_whose_office_is_not_taking_part_gets_none(self):
        record = self.reviewed()  # ITSO and IERC; never KTTO
        self.assertNothingDisclosed(record, self.ktto_member)

    def test_rdco_on_a_record_rdco_never_held_gets_none(self):
        record = self.routed(Party.ITSO, Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.cleared(record, self.itso, "No patentable mechanism.")
        ierc = self.assignment(record, Party.IERC)
        declined = Review.objects.create(
            record=record, reviewed_by=self.ierc, stage=Party.IERC,
            status=ReviewDecision.DECLINED, comment="Consent form is missing.", assignment=ierc,
        )
        ResubmissionRequest.objects.create(
            record=record, party=Party.IERC, assignment=ierc, review=declined,
            requested_by=self.ierc, reason="Consent form is missing.",
            state=ResubmissionRequestState.RESUBMITTED,
            resolved_by=self.owner, resolved_at=timezone.now(),
        )
        # IERC is still reviewing, so there has been no hand-back.
        self.assertFalse(RecordAssignment.objects.filter(record=record, party=Party.RDCO).exists())

        self.assertNothingDisclosed(record, self.rdco)


# --- AC: who reads it -----------------------------------------------------------------------

class ParticipantsReadItTests(ReviewPrivacyTestBase):

    def test_an_owner_reads_it(self):
        self.assertEverythingDisclosed(self.reviewed(), self.owner)

    def test_the_owner_still_reads_it_once_the_record_is_published(self):
        self.assertEverythingDisclosed(self.published(self.reviewed()), self.owner)

    def test_someone_whose_seat_is_done_reads_it(self):
        """ITSO cleared and finished; the reviewer keeps the history (ADR-032 §10)."""
        record = self.reviewed()
        self.assertEqual(
            RecordAssignment.objects.get(record=record, party=Party.ITSO).state,
            AssignmentState.COMPLETED,
        )
        self.assertEverythingDisclosed(record, self.itso)

    def test_a_pool_member_of_an_office_taking_part_reads_it_without_a_seat(self):
        record = self.reviewed()  # IERC is active, and nobody there is seated
        self.assertEverythingDisclosed(record, self.ierc2)


# --- AC: IR-269's per-seat detail follows the same rule ------------------------------------

class SeatDetailTests(ReviewPrivacyTestBase):

    def test_a_pool_member_now_sees_who_reviews_for_their_office(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)

        seats = self.rows(self.tracker(record, self.itso2))[Party.ITSO]["seats"]

        self.assertEqual(len(seats), 1)
