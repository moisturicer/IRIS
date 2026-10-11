"""
The owner answers the open revision requests with a new version; only the
requesting parties' clearances and seats reset (IR-273).

ADR-032 §5 and its 2026-10-08 Amendments, at the REST seam IR-255 confirmed:
ADR-003's clearance-aware resubmission on the new model. One class per
acceptance criterion, then the IR-416 hand-off (the manuscript lock and which
manuscript a non-owner reads). Both resubmission policies run through
`WORKFLOW_TABLE` here; the old fixed-pipeline policy suite was retired.
"""

from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.documents.models import RecordUpload, UploadSlot
from apps.notifications.models import Notification
from apps.records import lifecycle
from apps.records.models import Record, RecordVersion
from apps.reviews import routing
from apps.reviews.models import (
    RecordAssignment,
    RecordClearance,
    ResubmissionRequest,
    Review,
    ReviewerSeat,
    RoutingEvent,
)
from core.enums import (
    ClearanceStatus,
    Party,
    PipelineStatus,
    RecordTypeName,
    ResubmissionRequestState,
    SeatState,
    VersionCause,
    WorkflowState,
)

from .test_office_review import detail_url
from .test_revisions import RevisionTestBase

RESTART_ALL = {"RESUBMISSION_POLICY": lifecycle.ResubmissionPolicy.RESTART_ALL}


def new_version_url(record):
    return reverse("record-new-version", args=[record.pk])


def manuscript_url(record):
    return reverse("record-manuscript", args=[record.pk])


def _pdf(body, name="paper.pdf"):
    return SimpleUploadedFile(name, body, content_type="application/pdf")


class NewVersionTestBase(RevisionTestBase):

    def thesis(self, *parties):
        """A Thesis with a manuscript, accepted and routed to `parties`."""
        record = self.new_model(abstract_file=_pdf(b"%PDF-1.7 v1"))
        self.accepted_to(record, *parties)
        return record

    def itso_cleared_and_ierc_asked(self):
        """ITSO has cleared and IERC has an open request: the card's AC1 setup."""
        record = self.thesis(Party.ITSO, Party.IERC)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.cleared(record, self.itso)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.asked(record, self.ierc)
        return record

    def edit_title(self, record, title="A revised title", as_user=None):
        self.client.force_authenticate(as_user or self.owner)
        response = self.client.patch(detail_url(record), {"title": title}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response

    def upload_manuscript(self, record, body=b"%PDF-1.7 v2", as_user=None):
        self.client.force_authenticate(as_user or self.owner)
        with patch("apps.documents.tasks.extract_manuscript_text.delay"):
            return self.client.patch(
                detail_url(record), {"abstract_file": _pdf(body, "revised.pdf")},
                format="multipart",
            )

    def submit_version(self, record, as_user=None):
        return self.post(new_version_url(record), as_user or self.owner, {})

    def submitted(self, record, as_user=None):
        response = self.submit_version(record, as_user)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        record.refresh_from_db()
        return response

    def versions(self, record):
        return list(RecordVersion.objects.filter(record=record).order_by("number"))

    def seat_state(self, record, party, reviewer):
        return ReviewerSeat.objects.filter(
            assignment__record=record, assignment__party=party, reviewer=reviewer,
        ).exclude(state=SeatState.WITHDRAWN).latest("pk").state

    def read_manuscript(self, record, as_user):
        self.client.force_authenticate(as_user)
        response = self.client.get(manuscript_url(record))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return b"".join(response.streaming_content)


# --- AC: metadata-only version ---------------------------------------------------------

class MetadataOnlyVersionTests(NewVersionTestBase):

    def test_only_ierc_is_reset_and_itso_s_clearance_is_preserved(self):
        record = self.itso_cleared_and_ierc_asked()
        itso_clearance = RecordClearance.objects.get(record=record, office=Party.ITSO)
        request = ResubmissionRequest.objects.get(record=record, party=Party.IERC)
        [v1] = self.versions(record)

        self.edit_title(record)
        self.submitted(record)

        # v2, pointing at the same manuscript.
        v1_, v2 = self.versions(record)
        self.assertEqual((v2.number, v2.cause, v2.created_by), (2, VersionCause.REVISION, self.owner))
        self.assertEqual(v2.manuscript.name, v1.manuscript.name)
        # IERC's request is answered.
        request.refresh_from_db()
        self.assertEqual(request.state, ResubmissionRequestState.RESUBMITTED)
        self.assertEqual(request.resolved_by, self.owner)
        self.assertIsNotNone(request.resolved_at)
        # IERC reviews again; ITSO is untouched.
        self.assertEqual(self.clearance(record, Party.IERC), ClearanceStatus.PENDING)
        self.assertEqual(self.seat_state(record, Party.IERC, self.ierc), SeatState.IN_REVIEW)
        self.assertEqual(self.clearance(record, Party.ITSO), ClearanceStatus.CLEARED)
        self.assertEqual(self.seat_state(record, Party.ITSO, self.itso), SeatState.DONE)
        untouched = RecordClearance.objects.get(record=record, office=Party.ITSO)
        self.assertEqual(untouched.updated_at, itso_clearance.updated_at)

    def test_itso_s_clearance_is_marked_preserved_and_the_record_is_back_in_review(self):
        record = self.itso_cleared_and_ierc_asked()
        self.edit_title(record)

        response = self.submitted(record)

        # It answers with the tracker.
        self.assertNotEqual(response.data["workflow_state"], WorkflowState.AWAITING_RESUBMISSION.value)
        self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)
        self.assertEqual(record.resubmission_count, 1)
        clearances = {c["office"]: c for c in self.detail(record, self.owner)["clearances"]}
        self.assertTrue(clearances[Party.ITSO]["preserved"])
        self.assertFalse(clearances[Party.IERC]["preserved"])
        self.assertEqual(self.detail(record, self.owner)["revision"]["open"], [])

    def test_ierc_s_reviewers_are_told_and_itso_s_are_not(self):
        record = self.itso_cleared_and_ierc_asked()
        self.edit_title(record)
        before = set(Notification.objects.values_list("pk", flat=True))

        with self.captureOnCommitCallbacks(execute=True):
            self.submitted(record)

        new = Notification.objects.exclude(pk__in=before)
        self.assertEqual({n.recipient for n in new}, {self.ierc})
        self.assertIn("v2", new.get().message)


# --- AC: upload version -----------------------------------------------------------------

class UploadVersionTests(NewVersionTestBase):

    def test_a_new_manuscript_is_the_next_version_s(self):
        record = self.itso_cleared_and_ierc_asked()
        [v1] = self.versions(record)

        response = self.upload_manuscript(record)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.submitted(record)

        _, v2 = self.versions(record)
        self.assertEqual(v2.manuscript.name, record.abstract_file.name)
        self.assertNotEqual(v2.manuscript.name, v1.manuscript.name)
        # The earlier version still reads as it did.
        self.assertEqual(v1.manuscript.read(), b"%PDF-1.7 v1")

    def test_the_owner_may_replace_the_manuscript_only_while_a_revision_is_asked_for(self):
        """
        Still a 400, but since IR-507 it is the record update's own "not now"
        (`detail`, naming the status), answered before the body is read --
        not the manuscript lock's `abstract_file` error. An owner may edit
        nothing in review until a revision is asked for, the file included.
        """
        record = self.thesis(Party.IERC)

        refused = self.upload_manuscript(record)
        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("in_review", refused.data["detail"])
        record.refresh_from_db()
        self.assertEqual(record.abstract_file.name, self.versions(record)[0].manuscript.name)

        self.opened_seat(record, Party.IERC, self.ierc)
        self.asked(record, self.ierc)
        self.assertEqual(self.upload_manuscript(record).status_code, status.HTTP_200_OK)

    def test_a_reviewer_may_not_replace_it_while_a_revision_is_asked_for(self):
        """
        Staff are not exempt (ADR-032 §5 Amendment): the revision is the owner's.
        A 403 since IR-507, where it was the manuscript lock's 400: no office
        edits a record that is not theirs, so the refusal comes before the lock.
        """
        record = self.itso_cleared_and_ierc_asked()

        response = self.upload_manuscript(record, as_user=self.ierc)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        record.refresh_from_db()
        self.assertEqual(record.abstract_file.name, self.versions(record)[0].manuscript.name)

    def test_a_reviewer_reads_the_submitted_version_until_the_new_one_is_submitted(self):
        """IR-416's hand-off: an unsubmitted upload is the owner's alone."""
        record = self.itso_cleared_and_ierc_asked()
        self.upload_manuscript(record)

        self.assertEqual(self.read_manuscript(record, self.ierc), b"%PDF-1.7 v1")
        self.assertEqual(self.read_manuscript(record, self.owner), b"%PDF-1.7 v2")
        self.assertTrue(self.detail(record, self.owner)["manuscript_unsubmitted"])
        self.assertFalse(self.detail(record, self.ierc)["manuscript_unsubmitted"])

        self.submitted(record)

        self.assertEqual(self.read_manuscript(record, self.ierc), b"%PDF-1.7 v2")
        self.assertFalse(self.detail(record, self.owner)["manuscript_unsubmitted"])

    def test_withdrawing_the_last_request_puts_the_submitted_manuscript_back(self):
        """Found in review: an upload no version can carry must not stay the record's."""
        record = self.itso_cleared_and_ierc_asked()
        request = self.open_requests(record).get()
        self.upload_manuscript(record)

        response = self.withdraw(record, self.ierc, request.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        record.refresh_from_db()
        [v1] = self.versions(record)
        self.assertEqual(record.abstract_file.name, v1.manuscript.name)
        self.assertEqual(self.read_manuscript(record, self.owner), b"%PDF-1.7 v1")
        self.assertFalse(self.detail(record, self.owner)["manuscript_unsubmitted"])

    def test_withdrawing_one_of_two_requests_keeps_the_owner_s_upload(self):
        record = self.thesis(Party.IERC, Party.KTTO)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.opened_seat(record, Party.KTTO, self.ktto)
        ierc_request = self.asked(record, self.ierc)
        self.asked(record, self.ktto)
        self.upload_manuscript(record)

        self.withdraw(record, self.ierc, ierc_request.pk)

        self.assertEqual(self.read_manuscript(record, self.owner), b"%PDF-1.7 v2")


# --- what Ask IRIS answers from (settled 2026-10-08, after review) ----------------------

class ExtractionFollowsSubmissionTests(NewVersionTestBase):
    """
    The chunks Ask IRIS and Paper Chat answer from are the submitted
    manuscript's, the same file reviewers are served: an owner's revision is
    extracted when its version is submitted, never on upload.
    """

    EXTRACT = "apps.documents.tasks.extract_manuscript_text.delay"

    def test_an_unsubmitted_revision_is_not_extracted(self):
        record = self.itso_cleared_and_ierc_asked()

        with patch(self.EXTRACT) as extract, self.captureOnCommitCallbacks(execute=True):
            response = self.upload_manuscript(record)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        extract.assert_not_called()

    def test_submitting_the_version_extracts_its_manuscript(self):
        record = self.itso_cleared_and_ierc_asked()
        self.upload_manuscript(record)

        with patch(self.EXTRACT) as extract, self.captureOnCommitCallbacks(execute=True):
            self.submitted(record)

        extract.assert_called_once_with(record.pk)

    def test_a_metadata_only_version_extracts_nothing(self):
        record = self.itso_cleared_and_ierc_asked()
        self.edit_title(record)

        with patch(self.EXTRACT) as extract, self.captureOnCommitCallbacks(execute=True):
            self.submitted(record)

        extract.assert_not_called()

    def test_withdrawing_puts_the_file_back_without_extracting_again(self):
        record = self.itso_cleared_and_ierc_asked()
        request = self.open_requests(record).get()
        self.upload_manuscript(record)

        with patch(self.EXTRACT) as extract, self.captureOnCommitCallbacks(execute=True):
            self.withdraw(record, self.ierc, request.pk)

        extract.assert_not_called()

    def test_a_draft_s_manuscript_is_still_extracted_on_upload(self):
        record = self.make_record()

        with patch(self.EXTRACT) as extract, self.captureOnCommitCallbacks(execute=True):
            response = self.upload_manuscript(record)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        extract.assert_called_once_with(record.pk)


# --- AC: nothing changed -----------------------------------------------------------------

class NothingChangedTests(NewVersionTestBase):

    def assert_refused_as_unchanged(self, record):
        response = self.submit_version(record)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        detail = response.data["detail"]
        self.assertIn("Nothing has changed", detail)
        self.assertIn("manuscript", detail)
        self.assertIn("details", detail)
        self.assertEqual(len(self.versions(record)), 1)
        self.assertEqual(self.open_requests(record).count(), 1)

    def test_resubmitting_with_no_change_is_refused_saying_what_is_missing(self):
        self.assert_refused_as_unchanged(self.itso_cleared_and_ierc_asked())

    def test_an_edit_made_before_the_request_does_not_answer_it(self):
        """
        The edit is made while the record is still a draft. It used to be made
        in review before the request was opened, which IR-507 now refuses: an
        owner edits only a draft or a record awaiting their revision. A draft
        edit stamps `details_edited_at` just the same, so the question this
        asks -- does an earlier stamp answer a later request? -- is unchanged.
        """
        record = self.make_record(abstract_file=_pdf(b"%PDF-1.7 v1"))
        self.edit_title(record)
        routing.enter_at_adviser(record, self.owner)
        self.accepted_to(record, Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.asked(record, self.ierc)

        self.assert_refused_as_unchanged(record)

    def test_saving_the_same_details_again_is_not_a_change(self):
        record = self.itso_cleared_and_ierc_asked()
        self.edit_title(record, title=record.title)

        self.assert_refused_as_unchanged(record)

    def test_a_reviewer_editing_the_details_does_not_answer_the_request(self):
        """
        Found in review: the revision is the owner's to make. Since IR-507 the
        reviewer's edit is refused outright -- a 403, since IERC can see the
        record -- where before it was saved and merely did not count.
        """
        record = self.itso_cleared_and_ierc_asked()
        self.client.force_authenticate(self.ierc)
        response = self.client.patch(detail_url(record), {"title": "A revised title"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        record.refresh_from_db()
        self.assertNotEqual(record.title, "A revised title")
        self.assert_refused_as_unchanged(record)

    def test_a_supporting_document_uploaded_since_the_request_is_a_change(self):
        record = self.itso_cleared_and_ierc_asked()
        slot = UploadSlot.objects.create(name="Consent form", record_type=record.record_type)
        RecordUpload.objects.create(
            record=record, slot=slot, file=_pdf(b"%PDF-1.7 consent"), uploaded_by=self.owner,
        )

        self.submitted(record)

        self.assertEqual(len(self.versions(record)), 2)

    def test_the_owner_is_told_before_trying(self):
        """Record detail carries the same answer, so the dialog can say it first."""
        record = self.itso_cleared_and_ierc_asked()

        hint = self.detail(record, self.owner)["revision"]["new_version"]
        self.assertEqual(hint["number"], 2)
        self.assertEqual(hint["rereview"], ["IERC"])
        self.assertEqual(hint["kept"], ["ITSO"])
        self.assertIn("Nothing has changed", hint["blocked"])

        self.edit_title(record)
        self.assertIsNone(self.detail(record, self.owner)["revision"]["new_version"]["blocked"])
        # Nobody but an owner is offered it.
        self.assertIsNone(self.detail(record, self.ierc)["revision"]["new_version"])


# --- AC: two requests --------------------------------------------------------------------

class TwoRequestsTests(NewVersionTestBase):

    def test_one_version_resets_exactly_the_two_parties_that_asked(self):
        record = self.thesis(Party.ITSO, Party.IERC, Party.KTTO)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.cleared(record, self.itso)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.opened_seat(record, Party.KTTO, self.ktto)
        self.asked(record, self.ierc)
        self.asked(record, self.ktto)
        self.edit_title(record)

        self.submitted(record)

        self.assertFalse(self.open_requests(record).exists())
        self.assertEqual(
            set(ResubmissionRequest.objects.filter(record=record).values_list("state", flat=True)),
            {ResubmissionRequestState.RESUBMITTED},
        )
        self.assertEqual(
            dict(RecordClearance.objects.filter(record=record).values_list("office", "status")),
            {
                Party.ITSO: ClearanceStatus.CLEARED,
                Party.IERC: ClearanceStatus.PENDING,
                Party.KTTO: ClearanceStatus.PENDING,
            },
        )
        self.assertEqual(self.seat_state(record, Party.ITSO, self.itso), SeatState.DONE)
        self.assertEqual(self.seat_state(record, Party.IERC, self.ierc), SeatState.IN_REVIEW)
        self.assertEqual(self.seat_state(record, Party.KTTO, self.ktto), SeatState.IN_REVIEW)

    def test_a_requesting_office_s_finished_seat_returns_to_review(self):
        """One IERC reviewer had cleared before a colleague asked: IERC reviews v2 whole."""
        record = self.thesis(Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.opened_seat(record, Party.IERC, self.ierc2)
        self.cleared(record, self.ierc)
        self.asked(record, self.ierc2)
        self.edit_title(record)

        self.submitted(record)

        seat = ReviewerSeat.objects.get(assignment__record=record, reviewer=self.ierc)
        self.assertEqual(seat.state, SeatState.IN_REVIEW)
        self.assertIsNone(seat.done_at)
        self.assertEqual(self.seat_state(record, Party.IERC, self.ierc2), SeatState.IN_REVIEW)


# --- AC: restart-all ---------------------------------------------------------------------

@override_settings(WORKFLOW_TABLE=RESTART_ALL)
class RestartAllTests(NewVersionTestBase):

    def test_every_clearance_resets(self):
        record = self.itso_cleared_and_ierc_asked()
        self.edit_title(record)

        self.submitted(record)

        self.assertEqual(
            dict(RecordClearance.objects.filter(record=record).values_list("office", "status")),
            {Party.ITSO: ClearanceStatus.PENDING, Party.IERC: ClearanceStatus.PENDING},
        )
        self.assertEqual(self.detail(record, self.owner)["resubmission"]["offices_preserved"], [])
        hint_kept = self.detail(record, self.owner)["revision"]["new_version"]
        self.assertIsNone(hint_kept)  # nothing is open any more

    def test_the_policies_differ_only_in_which_clearances_reset(self):
        """Seats, requests and the version are the clearance-aware arm's."""
        record = self.itso_cleared_and_ierc_asked()
        self.edit_title(record)

        self.submitted(record)

        self.assertEqual(self.seat_state(record, Party.ITSO, self.itso), SeatState.DONE)
        self.assertEqual(self.seat_state(record, Party.IERC, self.ierc), SeatState.IN_REVIEW)
        self.assertEqual(self.active(record), {Party.IERC})
        self.assertEqual(len(self.versions(record)), 2)
        self.assertFalse(self.open_requests(record).exists())

    def test_the_owner_is_told_that_nothing_is_kept(self):
        record = self.itso_cleared_and_ierc_asked()

        hint = self.detail(record, self.owner)["revision"]["new_version"]

        self.assertEqual((hint["rereview"], hint["kept"]), (["IERC"], []))


# --- AC: RDCO or Adviser revision ----------------------------------------------------------

class RdcoOrAdviserRevisionTests(NewVersionTestBase):

    def test_if_rdco_asked_only_rdco_re_reviews(self):
        record = self.thesis(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.cleared(record, self.itso)  # the hand-back opens RDCO's pool
        self.opened_seat(record, Party.RDCO, self.rdco)
        self.asked(record, self.rdco)
        self.edit_title(record)

        self.submitted(record)

        self.assertEqual(self.active(record), {Party.RDCO})
        self.assertEqual(self.seat_state(record, Party.RDCO, self.rdco), SeatState.IN_REVIEW)
        self.assertEqual(self.seat_state(record, Party.ITSO, self.itso), SeatState.DONE)
        self.assertEqual(self.clearance(record, Party.ITSO), ClearanceStatus.CLEARED)
        clearances = {c["office"]: c for c in self.detail(record, self.owner)["clearances"]}
        self.assertTrue(clearances[Party.ITSO]["preserved"])

    def test_if_the_adviser_asked_only_the_adviser_re_reviews(self):
        record = self.new_model(RecordTypeName.PROPOSAL)
        seat = self.adviser_seat(record)
        self.asked(record, self.adviser)
        self.edit_title(record)

        self.submitted(record)

        seat.refresh_from_db()
        self.assertEqual(seat.state, SeatState.IN_REVIEW)
        self.assertEqual(self.active(record), {Party.ADVISER})
        self.assertFalse(RecordClearance.objects.filter(record=record).exists())
        self.assertEqual(len(self.versions(record)), 2)


# --- AC: no deletions -------------------------------------------------------------------------

class NoDeletionsTests(NewVersionTestBase):

    MODELS = (Review, RoutingEvent, RecordClearance, ResubmissionRequest, RecordVersion,
              ReviewerSeat, RecordAssignment)

    def snapshot(self):
        return {m: set(m.objects.values_list("pk", flat=True)) for m in self.MODELS}

    def test_nothing_is_deleted_under_either_policy(self):
        for table in ({}, RESTART_ALL):
            with self.subTest(policy=table or "clearance_aware"), override_settings(WORKFLOW_TABLE=table):
                record = self.itso_cleared_and_ierc_asked()
                self.edit_title(record)
                before = self.snapshot()

                self.submitted(record)

                after = self.snapshot()
                for model in self.MODELS:
                    self.assertLessEqual(before[model], after[model], model.__name__)


# --- who may, and when ---------------------------------------------------------------------

class WhoMaySubmitTests(NewVersionTestBase):

    def test_a_reviewer_is_refused_with_403(self):
        record = self.itso_cleared_and_ierc_asked()
        self.edit_title(record)

        response = self.submit_version(record, as_user=self.ierc)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.open_requests(record).count(), 1)

    def test_someone_who_cannot_see_the_record_gets_404(self):
        record = self.itso_cleared_and_ierc_asked()

        response = self.submit_version(record, as_user=self.stranger)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_with_no_open_request_there_is_nothing_to_answer(self):
        record = self.thesis(Party.IERC)
        # A change exists, so the refusal is about the missing request. It was
        # made through the record update until IR-507 refused an owner's edit
        # in review with no revision asked for; the stamp is what that wrote.
        Record.objects.filter(pk=record.pk).update(details_edited_at=timezone.now())

        response = self.submit_version(record)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("No reviewer has asked for a revision", response.data["detail"])
        self.assertEqual(len(self.versions(record)), 1)

    def test_a_record_not_in_review_is_refused(self):
        """IR-274: this was asked of a record still holding a fixed-pipeline status. Those statuses are gone; the refusal they exercised -- a record not in review -- is asked of a published record instead. It used to point the owner at
        the legacy Resubmit, which no longer exists."""
        record = self.make_record()
        record.pipeline_status = PipelineStatus.PUBLISHED
        record.save(update_fields=["pipeline_status"])

        response = self.submit_version(record)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not in review", response.data["detail"])
