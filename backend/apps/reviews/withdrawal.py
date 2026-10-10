"""
Deleting a record ends its review (IR-274).

The legacy `shadow.sync()` reconciled assignments from the old pipeline stage
after every transition. A soft delete left no stage that anyone held, so the
reconciliation withdrew everything as a side effect. IR-274 retires that
module. The rule is stated here instead, and `lifecycle.apply()` calls it for
a soft delete.

**Withdrawn, never completed.** Nobody finished their part, so every active
assignment and every unfinished seat on it becomes `withdrawn`, and every open
revision request is closed as withdrawn by the person who deleted. A seat
already `done` is history and stays. Clearances are untouched: a clearance
records completed rounds only (ADR-032 §4 Amendment). Open document requests
are left as they were, which is what the legacy reconciliation did too.
"""

from django.utils import timezone

from core.enums import OPEN_SEAT_STATES, AssignmentState, ResubmissionRequestState, SeatState

from .models import RecordAssignment, ResubmissionRequest, ReviewerSeat


def withdraw_review(record, actor) -> None:
    """Withdraw `record`'s active assignments, their open seats and its open revision requests."""
    now = timezone.now()
    active = list(
        RecordAssignment.objects.select_for_update()
        .filter(record=record, state=AssignmentState.ACTIVE)
        .values_list("pk", flat=True)
    )
    ReviewerSeat.objects.filter(
        assignment_id__in=active, state__in=OPEN_SEAT_STATES,
    ).update(state=SeatState.WITHDRAWN)
    RecordAssignment.objects.filter(pk__in=active).update(
        state=AssignmentState.WITHDRAWN, closed_by=actor, closed_at=now,
    )
    ResubmissionRequest.objects.filter(
        record=record, state=ResubmissionRequestState.OPEN,
    ).update(state=ResubmissionRequestState.WITHDRAWN, resolved_by=actor, resolved_at=now)
