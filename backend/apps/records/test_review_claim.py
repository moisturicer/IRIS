"""IR-681: a claim offer is the existing pool act, at the record HTTP seam."""
from django.urls import reverse

from apps.reviews.models import RecordAssignment
from apps.reviews.test_decisions import DecisionTestBase
from core.enums import AssignmentState, Party


class ReviewClaimOfferTests(DecisionTestBase):
    def test_only_the_pool_member_gets_an_offer_and_claiming_removes_it(self):
        record = self.routed(Party.ITSO)
        assignment = RecordAssignment.objects.get(record=record, party=Party.ITSO, state=AssignmentState.ACTIVE)
        self.assertEqual(self.detail(record, self.itso)["review_claim"], {
            "assignment": assignment.pk, "label": "Claim review", "party_label": "ITSO",
        })
        for viewer in (self.owner, self.adviser, self.ierc, self.rdco):
            with self.subTest(viewer=viewer.pk):
                self.assertIsNone(self.detail(record, viewer)["review_claim"])
        self.client.force_authenticate(self.itso)
        response = self.client.post(reverse("assignment-claim", args=[assignment.pk]))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(self.detail(record, self.itso)["review_claim"])

    def test_a_completed_office_never_offers_claim(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.cleared(record, self.itso)
        self.assertIsNone(self.detail(record, self.itso)["review_claim"])

    def test_the_footer_gets_the_viewers_own_verdict_in_words(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.assertIsNone(self.detail(record, self.itso)["my_seats"][0]["verdict_label"])
        self.cleared(record, self.itso)
        self.assertEqual(self.detail(record, self.itso)["my_seats"][0]["verdict_label"], "Cleared")
        self.assertEqual(self.detail(record, self.owner)["my_seats"], [])
