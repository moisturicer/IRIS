"""
The owner's dashboard counts after the fixed pipeline's removal (IR-274).

`pending_mine` drives the sidebar's workspace badge. It counted the five stage
statuses, which IR-260 migrated to `in_review`, so from the cutover on it was 0
for every owner. `declined_mine` counted the stored `declined`, which no record
holds any more; a revision request is an open `ResubmissionRequest` now.
"""

from django.urls import reverse
from rest_framework import status

from apps.reviews.test_decisions import DecisionTestBase


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
