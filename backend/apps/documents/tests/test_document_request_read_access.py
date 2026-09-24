"""
Who may read a Record's document requests (IR-349, ADR-022 §Amendment 5).

Document-request data is internal workflow data. Being able to read a Record
does not grant it: not to a reader of a published Record, and not to an office
that `visible_to()` lets see everything. Access is by **participation, never by
role** -- the owner, or someone who can staff a party that holds, held or acted
on the Record, or that asked for documents on it.

Both routes that serve the data -- the list and the tracker -- ask the one
predicate, `requests.may_read_requests`. A viewer who fails it gets a 403 from
the list, and from the tracker `document_requests: null` and every party row's
`awaiting_document: null`. The generic `workflow_state` is unchanged.

**Seam: the HTTP API**, as for IR-262.
"""

import json

from rest_framework import status

from apps.documents.models import DocumentRequest
from apps.documents.requests import may_read_requests
from apps.records.models import Record
from apps.records.test_tracker import make_user
from apps.reviews.models import RecordAssignment, RecordClearance
from core.enums import (
    AssignmentState, Office, Party, PipelineStatus, RecordTypeName, ReviewStage, RoleName,
)

from .test_document_requests import DocumentRequestTestBase

MESSAGE = "The signed consent forms are missing."
ITEM = "Rescanned consent form"


class ReadAccessTestBase(DocumentRequestTestBase):

    def ethics_record(self):
        """
        A Thesis at parallel review with IERC's request open. ITSO has cleared
        and closed; IERC holds and asked; KTTO was never requested.
        """
        record = self.submitted(
            RecordTypeName.THESIS_RESEARCH, requested_itso=True, requested_ierc=True,
        )
        self.review(record, self.rdco, "approved", "Needs ITSO and IERC.")
        self.review(record, self.itso, "approved", "No patent concerns.")
        self.requested(record, self.ierc, [{"label": ITEM}], message=MESSAGE)
        return record

    def list_response(self, record, viewer):
        self.client.force_authenticate(viewer)
        return self.client.get(self.requests_url(record))

    def assert_non_participant(self, record, viewer):
        response = self.list_response(record, viewer)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertNotIn(MESSAGE, json.dumps(response.data))

        tracker = self.tracker_ok(record, viewer)
        self.assertIsNone(tracker["document_requests"])
        for row in tracker["parties"]:
            self.assertIsNone(row["awaiting_document"], row["party"])
        body = json.dumps(tracker)
        self.assertNotIn(MESSAGE, body)
        self.assertNotIn(ITEM, body)
        self.assertNotIn(self.ierc.get_full_name(), body)
        return tracker

    def assert_participant(self, record, viewer):
        response = self.list_response(record, viewer)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        [request] = response.data
        self.assertEqual(request["message"], MESSAGE)

        tracker = self.tracker_ok(record, viewer)
        [request] = tracker["document_requests"]
        self.assertEqual(request["message"], MESSAGE)
        rows = self.rows(tracker)
        self.assertIs(rows["ierc"]["awaiting_document"], True)
        self.assertIs(rows["ktto"]["awaiting_document"], False)


class PublicReaderTests(ReadAccessTestBase):

    def test_a_student_reading_a_published_record_sees_no_request_data(self):
        record = self.ethics_record()
        Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.PUBLISHED)

        tracker = self.assert_non_participant(record, self.stranger)

        self.assertEqual(tracker["workflow_state"], "published")


class UninvolvedOfficeTests(ReadAccessTestBase):

    def test_an_office_with_no_assignment_review_or_request_sees_none(self):
        record = self.ethics_record()

        tracker = self.assert_non_participant(record, self.ktto)

        self.assertEqual(tracker["workflow_state"], "awaiting_document")
        self.assertEqual(tracker["workflow_state_label"], "Awaiting document")

    def test_record_detail_still_carries_the_generic_workflow_state(self):
        record = self.ethics_record()

        self.assertEqual(self.detail(record, self.ktto)["workflow_state"], "awaiting_document")


class RoleIsNotParticipationTests(ReadAccessTestBase):

    def test_a_named_adviser_never_assigned_the_adviser_party_sees_none(self):
        # A Thesis enters at Intake, so its named Adviser never holds it.
        record = self.submitted(
            RecordTypeName.THESIS_RESEARCH, adviser=self.adviser,
            requested_itso=True, requested_ierc=True,
        )
        self.review(record, self.rdco, "approved", "Needs ITSO and IERC.")
        self.review(record, self.itso, "approved", "No patent concerns.")
        self.requested(record, self.ierc, [{"label": ITEM}], message=MESSAGE)
        self.assertFalse(RecordAssignment.objects.filter(record=record, party=Party.ADVISER).exists())

        self.assert_non_participant(record, self.adviser)

    def test_rdco_before_it_has_held_or_acted_on_a_proposal_sees_none(self):
        record = self.submitted(RecordTypeName.PROPOSAL, adviser=self.adviser)
        self.requested(record, self.adviser, [{"label": ITEM}], message=MESSAGE)

        self.assertEqual(
            self.list_response(record, self.rdco).status_code, status.HTTP_403_FORBIDDEN
        )
        tracker = self.tracker_ok(record, self.rdco)
        self.assertIsNone(tracker["document_requests"])
        self.assertTrue(all(row["awaiting_document"] is None for row in tracker["parties"]))
        self.assertNotIn(MESSAGE, json.dumps(tracker))


class ParticipantsSeeEverythingTests(ReadAccessTestBase):

    def test_the_owner(self):
        self.assert_participant(self.ethics_record(), self.owner)

    def test_the_requesting_party(self):
        record = self.ethics_record()
        # Another IERC member, who did not write the request. With IERC's
        # assignment gone, only the request's party speaks for them.
        colleague = make_user("tracker-ierc-colleague@cit.edu", RoleName.IERC)
        RecordAssignment.objects.filter(record=record, party=Party.IERC).delete()

        self.assert_participant(record, colleague)

    def test_the_user_who_made_the_request(self):
        record = self.ethics_record()
        # Nothing but `requested_by` connects the requester to the record: no
        # IERC assignment, and the request now names a party they cannot staff.
        RecordAssignment.objects.filter(record=record, party=Party.IERC).delete()
        DocumentRequest.objects.filter(record=record).update(party=Party.KTTO)

        response = self.list_response(record, self.ierc)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data[0]["message"], MESSAGE)
        self.assertIsNotNone(self.tracker_ok(record, self.ierc)["document_requests"])

    def test_a_party_currently_holding_an_assignment(self):
        record = self.ethics_record()
        # KTTO joins the record: it holds it now, and has done nothing else.
        RecordAssignment.objects.create(record=record, party=Party.KTTO, opened_by=self.rdco)

        self.assert_participant(record, self.ktto)

    def test_a_party_whose_assignment_is_closed(self):
        record = self.ethics_record()
        # ITSO cleared and closed. Remove what it recorded, so only the
        # closed assignment speaks for it.
        self.assertFalse(
            RecordAssignment.objects.filter(
                record=record, party=Party.ITSO, state=AssignmentState.ACTIVE
            ).exists()
        )
        record.reviews.filter(stage=ReviewStage.ITSO).delete()
        RecordClearance.objects.filter(record=record, office=Office.ITSO).update(reviewed_by=None)

        self.assert_participant(record, self.itso)

    def test_a_party_that_reviewed_under_an_assignment(self):
        record = self.ethics_record()
        # RDCO reviewed at intake. Without the assignment rows, the review
        # alone still makes it a participant.
        RecordAssignment.objects.filter(
            record=record, party__in=[Party.INTAKE, Party.RDCO]
        ).delete()

        self.assert_participant(record, self.rdco)

    def test_a_party_that_signed_a_clearance(self):
        record = self.ethics_record()
        RecordAssignment.objects.filter(record=record, party=Party.ITSO).delete()
        record.reviews.filter(stage=ReviewStage.ITSO).delete()

        self.assert_participant(record, self.itso)


class NoRecordAccessTests(ReadAccessTestBase):

    def test_a_viewer_who_cannot_see_the_record_gets_404_on_both_routes(self):
        record = self.ethics_record()

        self.assertEqual(
            self.list_response(record, self.stranger).status_code, status.HTTP_404_NOT_FOUND
        )
        self.assertEqual(self.tracker(record.pk, self.stranger).status_code, status.HTTP_404_NOT_FOUND)


class OneRuleTests(ReadAccessTestBase):
    """The list and the tracker never disagree, and both are the predicate."""

    def test_both_routes_agree_with_the_predicate_for_every_viewer(self):
        thesis = self.ethics_record()
        proposal = self.submitted(RecordTypeName.PROPOSAL, adviser=self.adviser)
        self.requested(proposal, self.adviser, [{"label": ITEM}], message=MESSAGE)
        published = self.ethics_record()
        Record.objects.filter(pk=published.pk).update(pipeline_status=PipelineStatus.PUBLISHED)

        viewers = [
            self.owner, self.stranger, self.adviser, self.other_adviser,
            self.rdco, self.itso, self.ierc, self.ktto,
        ]
        for record in (thesis, proposal, published):
            record.refresh_from_db()
            for viewer in viewers:
                with self.subTest(record=record.pk, viewer=viewer.email):
                    listed = self.list_response(record, viewer).status_code
                    tracker = self.tracker(record.pk, viewer)
                    if listed == status.HTTP_404_NOT_FOUND:
                        self.assertEqual(tracker.status_code, status.HTTP_404_NOT_FOUND)
                        continue
                    allowed = may_read_requests(record, viewer)
                    self.assertEqual(listed == status.HTTP_200_OK, allowed)
                    self.assertEqual(tracker.data["document_requests"] is not None, allowed)
                    flags = [row["awaiting_document"] for row in tracker.data["parties"]]
                    if allowed:
                        self.assertNotIn(None, flags)
                    else:
                        self.assertEqual(flags, [None] * len(flags))
