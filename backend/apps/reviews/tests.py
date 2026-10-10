"""
Who reviews a record, and which offices it reaches (rewritten for IR-274).

**What this file used to pin.** It tested `reviews.services` -- the fixed
pipeline's `approve_record`, `decline_record` and `submit_clearance` -- for two
things: that ADR-018's requested-office flags decided which clearance rows
intake created and where the record went next, and that an owner could not
review their own record at intake. IR-274 deleted that service with the
pipeline (ADR-032 §13). Both concerns survive, restated for the adviser-first
model and asserted at the HTTP seam rather than against a service:

- **The flags route nothing by themselves** (ADR-032 §3). A submission enters
  at the Adviser whatever the author flagged, and an office gets a clearance
  only when someone routes to it.
- **An owner never reviews their own record.** Owning a record is not a review
  role at any step: the owner cannot accept & route it, decide it or record an
  office review on it.
"""

from django.urls import reverse
from rest_framework import status

from apps.reviews.models import RecordAssignment, RecordClearance
from core.enums import AssignmentState, Party, PipelineStatus

from .test_routing import RoutingTestBase


class RequestedFlagsRouteNothingTests(RoutingTestBase):

    def offices(self, record):
        return set(RecordClearance.objects.filter(record=record).values_list("office", flat=True))

    def test_every_flag_set_still_enters_at_the_adviser_alone(self):
        record = self.new_model(requested_itso=True, requested_ierc=True, requested_ktto=True)
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)
        self.assertEqual(self.active(record), {Party.ADVISER})
        self.assertEqual(self.offices(record), set())

    def test_only_the_office_routed_to_gets_a_clearance(self):
        record = self.new_model(requested_itso=True, requested_ierc=True, requested_ktto=True)
        response = self.accept(record, [{"party": Party.ITSO}])
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.offices(record), {"itso"})
        self.assertIn(Party.ITSO, self.active(record))

    def test_an_office_nobody_flagged_can_still_be_routed_to(self):
        record = self.new_model()
        response = self.accept(record, [{"party": Party.IERC}])
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.offices(record), {"ierc"})

    def test_intake_is_never_a_route_target(self):
        record = self.new_model()
        response = self.accept(record, [{"party": "intake"}])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertFalse(
            RecordAssignment.objects.filter(record=record, party=Party.INTAKE).exists()
        )


class OwnerNeverReviewsTests(RoutingTestBase):

    def post_as_owner(self, name, record, body):
        self.client.force_authenticate(self.owner)
        return self.client.post(reverse(name, args=[record.pk]), body, format="json")

    def test_the_owner_cannot_accept_and_route_their_own_record(self):
        record = self.new_model()
        response = self.post_as_owner(
            "record-accept-and-route", record, {"to": [{"party": Party.ITSO}], "reason": "Mine."},
        )
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
        self.assertEqual(self.active(record), {Party.ADVISER})

    def test_the_owner_cannot_decide_their_own_record(self):
        record = self.new_model()
        response = self.post_as_owner(
            "record-decide", record, {"outcome": "publish", "comment": "", "token": "none"},
        )
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)

    def test_the_owner_cannot_record_an_office_review(self):
        record = self.new_model()
        self.accept(record, [{"party": Party.ITSO}])
        response = self.post_as_owner(
            "record-office-review", record, {"outcome": "cleared", "comment": ""},
        )
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
        self.assertEqual(
            RecordAssignment.objects.get(record=record, party=Party.ITSO).state,
            AssignmentState.ACTIVE,
        )
