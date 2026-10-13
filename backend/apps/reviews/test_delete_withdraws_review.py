"""
Deleting a record in review ends every turn unfinished (IR-274).

The legacy `shadow.sync()` did this as a side effect of the soft-delete
transition. IR-274 retires that module, so the rule is stated here on its own:
an owner withdrawing a record that is still in review withdraws its active
assignments, their open seats and its open revision requests, and closes
nothing as *completed* -- nobody finished.
"""

from django.urls import reverse
from rest_framework import status

from apps.reviews.models import RecordAssignment, ResubmissionRequest, ReviewerSeat
from core.enums import (
    AssignmentState,
    Party,
    PipelineStatus,
    ResubmissionRequestState,
    SeatState,
)

from .test_revisions import RevisionTestBase


class DeletingARecordInReviewTests(RevisionTestBase):

    def test_every_open_turn_is_withdrawn_and_nothing_is_completed(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.asked(record, self.itso)
        completed_before = set(
            RecordAssignment.objects.filter(
                record=record, state=AssignmentState.COMPLETED,
            ).values_list("pk", flat=True)
        )

        self.client.force_authenticate(self.owner)
        response = self.client.delete(reverse("record-detail", args=[record.pk]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        record.refresh_from_db()
        self.assertTrue(record.is_deleted)
        self.assertEqual(record.pipeline_status, PipelineStatus.PENDING_DELETE)

        assignments = RecordAssignment.objects.filter(record=record)
        self.assertFalse(assignments.filter(state=AssignmentState.ACTIVE).exists())
        self.assertEqual(
            set(assignments.filter(state=AssignmentState.COMPLETED).values_list("pk", flat=True)),
            completed_before,
        )
        withdrawn = assignments.filter(state=AssignmentState.WITHDRAWN)
        self.assertTrue(withdrawn.exists())
        self.assertTrue(all(a.closed_by_id == self.owner.pk for a in withdrawn))

        seats = ReviewerSeat.objects.filter(assignment__record=record)
        self.assertFalse(seats.filter(state__in=(SeatState.ASSIGNED, SeatState.IN_REVIEW)).exists())
        self.assertTrue(seats.filter(state=SeatState.WITHDRAWN).exists())

        requests = ResubmissionRequest.objects.filter(record=record)
        self.assertTrue(requests.exists())
        self.assertFalse(requests.filter(state=ResubmissionRequestState.OPEN).exists())
        self.assertTrue(all(
            r.state == ResubmissionRequestState.WITHDRAWN and r.resolved_by_id == self.owner.pk
            for r in requests
        ))
