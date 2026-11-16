"""
Every free-text field a person writes has a server-side length limit (IR-926,
ASVS 5.2.2).

IR-829 stored an abstract of 2,000,000 characters. Each field below now refuses
anything over `FREE_TEXT_MAX_LENGTH` (10,000, chosen by Ashlee Sean on
2026-11-15) with a 400 that names the limit, and writes nothing. Each test
reuses the setup of the module that already tests that act, and sends one
character over the limit. The abstract test also checks that exactly the limit
is accepted.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import AccountDeletionRequest
from apps.accounts.test_account_deletion import DeletionBase
from apps.documents.models import DocumentRequest
from apps.documents.tests.test_document_request_decisions import DecisionTestBase as ItemDecisionBase
from apps.opportunities.models import Opportunity
from apps.opportunities.tests import make_user as make_opportunity_user
from apps.reviews.models import ResubmissionRequest, Review, ReviewerSeat
from apps.reviews.test_decisions import DecisionTestBase
from apps.reviews.test_office_review import OfficeReviewTestBase
from apps.reviews.test_revisions import RevisionTestBase
from apps.reviews.test_review_threads import ThreadTestBase
from apps.reviews.test_routing import RoutingTestBase
from apps.reviews.test_seats import SeatTestBase, reassign_url
from core.enums import Party, PipelineStatus, RequestStatus, SeatState
from core.text_limits import FREE_TEXT_MAX_LENGTH

TOO_LONG = "x" * (FREE_TEXT_MAX_LENGTH + 1)
LIMIT_MESSAGE = f"{FREE_TEXT_MAX_LENGTH:,} characters"


def message_of(response):
    return str(response.data)


class AbstractLimitTests(RoutingTestBase):

    def patch(self, record, abstract):
        self.client.force_authenticate(self.owner)
        return self.client.patch(reverse("record-detail", args=[record.pk]), {"abstract": abstract}, format="json")

    def test_an_abstract_over_the_limit_is_refused_and_the_old_one_kept(self):
        record = self.make_record()
        response = self.patch(record, TOO_LONG)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("abstract", response.data)
        self.assertIn(LIMIT_MESSAGE, message_of(response))
        record.refresh_from_db()
        self.assertEqual(record.abstract, "A" * 40)

    def test_an_abstract_of_exactly_the_limit_is_accepted(self):
        record = self.make_record()
        response = self.patch(record, "y" * FREE_TEXT_MAX_LENGTH)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        record.refresh_from_db()
        self.assertEqual(len(record.abstract), FREE_TEXT_MAX_LENGTH)


class RoutingReasonLimitTests(RoutingTestBase):

    def test_accept_and_route_refuses_a_reason_over_the_limit(self):
        record = self.new_model()
        response = self.accept(record, [{"party": Party.RDCO}], reason=TOO_LONG)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn(LIMIT_MESSAGE, message_of(response))
        self.assertEqual(self.active(record), {Party.ADVISER})

    def test_route_refuses_a_reason_over_the_limit(self):
        record = self.new_model()
        self.accepted_to(record, Party.RDCO)
        response = self.route(record, self.rdco, [{"party": Party.ITSO}], reason=TOO_LONG)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn(LIMIT_MESSAGE, message_of(response))
        self.assertNotIn(Party.ITSO, self.active(record))


class RevisionReasonLimitTests(RevisionTestBase):

    def test_a_revision_request_over_the_limit_is_refused_and_nothing_written(self):
        record = self.routed(Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)
        response = self.ask(record, self.ierc, TOO_LONG)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn(LIMIT_MESSAGE, message_of(response))
        self.assertFalse(ResubmissionRequest.objects.filter(record=record).exists())


class OfficeCommentLimitTests(OfficeReviewTestBase):

    def test_a_finding_over_the_limit_is_refused_and_nothing_written(self):
        record = self.routed(Party.IERC)
        seat = self.opened_seat(record, Party.IERC, self.ierc)
        response = self.review(record, self.ierc, "finding", TOO_LONG)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn(LIMIT_MESSAGE, message_of(response))
        seat.refresh_from_db()
        self.assertEqual(seat.state, SeatState.IN_REVIEW)
        self.assertFalse(Review.objects.filter(record=record, stage=Party.IERC).exists())


class DecisionCommentLimitTests(DecisionTestBase):

    def test_a_decision_comment_over_the_limit_is_refused_and_nothing_written(self):
        record = self.at_adviser()
        response = self.decide(record, self.adviser, "reject", TOO_LONG)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn(LIMIT_MESSAGE, message_of(response))
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)
        self.assertFalse(Review.objects.filter(record=record, stage=Party.ADVISER).exists())


class ReassignmentReasonLimitTests(SeatTestBase):

    def setUp(self):
        self.record = self.make_record()
        self.pool = self.assignment(self.record, Party.ITSO)

    def test_a_reassignment_reason_over_the_limit_is_refused(self):
        seat = self.seat(self.pool, self.itso, state=SeatState.IN_REVIEW)
        before = ReviewerSeat.objects.count()
        response = self.post(reassign_url(seat), self.itso_coordinator, {"reviewer": self.itso2.pk, "reason": TOO_LONG})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn(LIMIT_MESSAGE, message_of(response))
        self.assertEqual(ReviewerSeat.objects.count(), before)


class DocumentRequestLimitTests(ItemDecisionBase):

    def test_a_request_message_over_the_limit_is_refused_and_nothing_written(self):
        record = self.at_parallel_review()
        response = self.request_documents(record, self.ierc, [{"label": "Consent form"}], message=TOO_LONG)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn(LIMIT_MESSAGE, message_of(response))
        self.assertFalse(DocumentRequest.objects.filter(record=record).exists())

    def test_a_rejection_reason_over_the_limit_is_refused_and_the_item_kept(self):
        # The reason is checked before the item's state, so no upload is needed
        # (and none can be made where the PDF checker isn't available).
        record = self.at_parallel_review()
        [item] = self.requested(record, self.ierc, [{"label": "Consent form"}])["items"]
        item_id = item["id"]
        before = self.item_state(item_id)
        response = self.decide(item_id, self.ierc, "reject", TOO_LONG)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn(LIMIT_MESSAGE, message_of(response))
        self.assertEqual(self.item_state(item_id), before)


class DeletionRejectionReasonLimitTests(DeletionBase):

    def test_a_rejection_reason_over_the_limit_is_refused_and_the_request_stays_pending(self):
        self.ask(self.student)
        made = self.pending_for(self.student)
        response, _send = self.reject(self.sysadmin, made.pk, reason=TOO_LONG)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.content)
        self.assertIn(LIMIT_MESSAGE, response.content.decode())
        self.assertEqual(AccountDeletionRequest.objects.get(pk=made.pk).status, RequestStatus.PENDING)


class OpportunityDescriptionLimitTests(APITestCase):

    def test_a_description_over_the_limit_is_refused_and_nothing_posted(self):
        from apps.opportunities.test_call_review import payload

        self.client.force_authenticate(make_opportunity_user("limits-rdco@cit.edu", "RDCO"))
        before = Opportunity.objects.count()
        response = self.client.post(reverse("opportunity-list"), payload(description=TOO_LONG), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("description", response.data)
        self.assertIn(LIMIT_MESSAGE, message_of(response))
        self.assertEqual(Opportunity.objects.count(), before)


class UploadReviewCommentLimitTests(RoutingTestBase):

    def test_a_staff_comment_over_the_limit_is_refused_before_anything_is_looked_up(self):
        from apps.documents.models import UploadReview

        self.client.force_authenticate(self.rdco)
        response = self.client.post(reverse("upload-reviews"), {"upload": 999999, "status": 999999,
                                                                 "comment": TOO_LONG}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn(LIMIT_MESSAGE, message_of(response))
        self.assertFalse(UploadReview.objects.exists())

    def test_a_comment_that_is_not_text_is_refused(self):
        self.client.force_authenticate(self.rdco)
        for comment in (None, 42, ["x"]):
            with self.subTest(comment=comment):
                response = self.client.post(reverse("upload-reviews"), {"upload": 1, "status": 1,
                                                                         "comment": comment}, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)


class OpportunityDescriptionPatchLimitTests(APITestCase):

    def test_a_patched_description_over_the_limit_is_refused_and_the_old_one_kept(self):
        from apps.opportunities.tests import make_opportunity

        rdco = make_opportunity_user("limits-rdco-patch@cit.edu", "RDCO")
        opportunity = make_opportunity(posted_by=rdco)
        kept = opportunity.description
        self.client.force_authenticate(rdco)
        response = self.client.patch(reverse("opportunity-detail", args=[opportunity.pk]),
                                     {"description": TOO_LONG}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn(LIMIT_MESSAGE, message_of(response))
        opportunity.refresh_from_db()
        self.assertEqual(opportunity.description, kept)


class FinishReviewSummaryLimitTests(ThreadTestBase):

    def test_a_comment_only_summary_over_the_limit_is_refused_and_no_round_written(self):
        from apps.reviews.models import ReviewRound

        record = self.itso_open()
        response = self.finish(record, self.itso, summary=TOO_LONG)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("A summary can be at most", message_of(response))
        self.assertFalse(ReviewRound.objects.filter(record=record).exists())


class ExtensionReasonLimitTests(SeatTestBase):

    def test_an_extension_reason_over_the_limit_is_refused_and_the_deadline_kept(self):
        from apps.reviews.models import RecordAssignment, Turnaround
        from apps.reviews.test_deadlines import at

        Turnaround.objects.create(party=Party.ITSO, working_days=1)
        record = self.make_record(adviser=self.adviser)
        assignment = RecordAssignment.objects.create(record=record, party=Party.ITSO, opened_at=at(25))
        before = assignment.due_at
        response = self.post(f"/api/v1/assignments/{assignment.pk}/extend/", self.itso_coordinator,
                             {"due_at": at(30, 23, 59).isoformat(), "reason": TOO_LONG})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn(LIMIT_MESSAGE, message_of(response))
        assignment.refresh_from_db()
        self.assertEqual(assignment.due_at, before)


class SystemSettingValueLimitTests(APITestCase):

    def test_a_setting_over_the_limit_is_refused_and_the_old_value_kept(self):
        from apps.accounts.models import SystemSetting
        from apps.accounts.test_system_settings import _url, _user
        from core.enums import RoleName

        setting = SystemSetting.objects.create(key="announcement", value="old text")
        self.client.force_authenticate(_user("limits-sysadmin@cit.edu", RoleName.SYSTEM_ADMIN))
        response = self.client.patch(_url("announcement"), {"value": TOO_LONG}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn(LIMIT_MESSAGE, message_of(response))
        setting.refresh_from_db()
        self.assertEqual(setting.value, "old text")


class ExcelImportAbstractLimitTests(APITestCase):

    def test_a_row_whose_abstract_is_over_the_limit_is_skipped_and_named(self):
        from apps.records.models import Record
        from apps.records.test_excel_import import ImportTestCase, row, workbook

        ImportTestCase.setUp(self)
        response = ImportTestCase.post(self, workbook(row("Too Long", TOO_LONG), row("Fine", "A short abstract.")))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual((response.data["created"], response.data["skipped"]), (1, 1))
        self.assertIn("Row 2: skipped — Abstract can be at most 10,000 characters.", response.data["log"])
        self.assertEqual(set(Record.objects.filter(added_by=self.rdco).values_list("title", flat=True)), {"Fine"})
