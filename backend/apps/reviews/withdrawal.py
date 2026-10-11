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
records completed rounds only (ADR-032 §4 Amendment).

**Open document requests are withdrawn too (IR-517).** They used to be left
open, as the legacy reconciliation left them, which kept requests open against
a record nobody can reach. They close as a Decision closes them, with
`closed_at` and no `closed_by_decision`: there is no Decision to name.

`open_review_work()` reads what is about to be withdrawn, so the caller can tell
the people whose work ends (IR-517) from the same rule that ends it.
"""

from dataclasses import dataclass, field

from django.utils import timezone

from core.enums import (
    OPEN_SEAT_STATES,
    AssignmentState,
    DocumentRequestState,
    ResubmissionRequestState,
    SeatState,
)

from .models import RecordAssignment, ResubmissionRequest, ReviewerSeat


@dataclass
class OpenReviewWork:
    """What withdrawing a record ends, and whose it was."""

    #: `(reviewer, party)` for every open seat on an active assignment.
    seats: list = field(default_factory=list)
    #: The parties with an open document request.
    requesting_parties: set = field(default_factory=set)


def _active_assignments(record):
    return RecordAssignment.objects.filter(record=record, state=AssignmentState.ACTIVE)


def _open_document_requests(record):
    from apps.documents.models import DocumentRequest

    return DocumentRequest.objects.filter(record=record, state=DocumentRequestState.OPEN)


def open_review_work(record) -> OpenReviewWork:
    """The open seats and document requests `withdraw_review` would close."""
    seats = (
        ReviewerSeat.objects.filter(
            assignment__in=_active_assignments(record), state__in=OPEN_SEAT_STATES,
        )
        .select_related("reviewer", "assignment")
        .order_by("pk")
    )
    return OpenReviewWork(
        seats=[(seat.reviewer, str(seat.assignment.party)) for seat in seats],
        requesting_parties={
            str(party) for party in _open_document_requests(record).values_list("party", flat=True)
        },
    )


def withdraw_review(record, actor) -> None:
    """
    Withdraw `record`'s active assignments, their open seats, its open revision
    requests and its open document requests.
    """
    now = timezone.now()
    active = list(
        _active_assignments(record).select_for_update().values_list("pk", flat=True)
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
    _open_document_requests(record).update(state=DocumentRequestState.WITHDRAWN, closed_at=now)
