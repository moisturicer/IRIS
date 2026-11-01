"""
The owner's dashboard counts after the fixed pipeline's removal (IR-274).

`pending_mine` drives the sidebar's workspace badge. It counted the five stage
statuses, which IR-260 migrated to `in_review`, so from the cutover on it was 0
for every owner. `declined_mine` counted the stored `declined`, which no record
holds any more; a revision request is an open `ResubmissionRequest` now.

`needs_action_mine` (IR-534, spec Appendix D · B2) is what the sidebar's My
Library dot reads: the owner's records whose derived `workflow_state` is
waiting on them -- `awaiting_resubmission` or `awaiting_document`.
"""

from django.urls import reverse
from rest_framework import status

from apps.documents.models import DocumentRequest
from apps.reviews.models import RecordAssignment
from apps.reviews.test_decisions import DecisionTestBase
from core.enums import DocumentRequestState, Party


class OwnerDashboardCountsTests(DecisionTestBase):

    def stats(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get(reverse("dashboard-stats"))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    def test_a_record_in_review_is_pending(self):
        self.make_record()  # a draft: not pending
        self.at_adviser()
        data = self.stats()
        self.assertEqual(data["pending_mine"], 1)
        self.assertEqual(data["declined_mine"], 0)

    def test_an_open_revision_request_counts_once_per_record(self):
        record = self.at_adviser()
        self.asked(record, self.adviser)
        data = self.stats()
        self.assertEqual((data["pending_mine"], data["declined_mine"]), (1, 1))


class NeedsActionMineTests(DecisionTestBase):
    """B2: only what is waiting on the owner counts, never "in review"."""

    def needs_action(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get(reverse("dashboard-stats"))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data["needs_action_mine"]

    def asked_for_documents(self, record):
        return DocumentRequest.objects.create(
            record=record, party=Party.ADVISER,
            assignment=RecordAssignment.objects.get(record=record, party=Party.ADVISER),
            requested_by=self.adviser, message="The signed form, please.",
        )

    def test_a_record_only_in_review_does_not_count(self):
        self.make_record()  # a draft
        self.at_adviser()
        self.assertEqual(self.needs_action(), 0)

    def test_an_open_resubmission_request_counts(self):
        record = self.at_adviser()
        self.asked(record, self.adviser)
        self.assertEqual(self.needs_action(), 1)

    def test_an_open_document_request_counts(self):
        self.asked_for_documents(self.at_adviser())
        self.assertEqual(self.needs_action(), 1)

    def test_a_record_counts_once_whatever_it_is_waiting_for(self):
        record = self.at_adviser()
        self.asked(record, self.adviser)
        self.asked_for_documents(record)
        self.at_adviser()  # a second, only in review
        self.assertEqual(self.needs_action(), 1)

    def test_a_closed_document_request_no_longer_counts(self):
        request = self.asked_for_documents(self.at_adviser())
        request.state = DocumentRequestState.WITHDRAWN
        request.save(update_fields=["state"])
        self.assertEqual(self.needs_action(), 0)

    def test_someone_elses_waiting_record_does_not_count(self):
        record = self.at_adviser()
        self.asked(record, self.adviser)
        self.client.force_authenticate(self.adviser)
        response = self.client.get(reverse("dashboard-stats"))
        self.assertEqual(response.data["needs_action_mine"], 0)
