"""
An office reviewer clears or records a finding, and what follows when the
office finishes (ADR-032 §3, §4 and its 2026-10-08 Amendment; IR-269).

**The act.** A seat holder for ITSO, IERC or KTTO, on a record on the new
model, *clears* or *records a finding*. Either writes their own `Review` --
`approved` or `negative_finding` -- under the office's assignment, then ends
their seat through `seats.complete_seat()`. A finding needs a reason; a
clearance may carry one. Offices never reject and never publish, so any other
outcome is refused.

**Before anything is written**, the act refuses:

- a caller holding no open specialist seat here (403, who before what);
- a record still on the legacy pipeline (400);
- an outcome other than `cleared` or `finding`, or a finding with no reason;
- a seat not yet opened: *Open review* stamps the time-on-task start, so
  finishing an unopened seat would leave it empty;
- an office with its own document request still open. An office never
  finishes while it is still asking the author for something; likewise an
  office with its own revision request open (IR-272).

**When an office completes** -- every seat it did not withdraw is done, by the
last verdict or by a coordinator withdrawing the last unfinished seat --
`office_completed()` runs, from `seats._close_if_complete`:

1. **The clearance takes this review round's outcome.** `not_cleared` if any
   `Review` written under *this* assignment is a finding, `cleared` otherwise.
   The latest completed round wins in both directions, so an office routed
   again replaces its earlier outcome only when its new round completes.
   `reviewed_by` and `comment` stay empty: each seat's verdict is its own
   `Review`.
2. **The hand-back.** When no specialist office is still active, IRIS opens an
   RDCO assignment in RDCO's pool, unless RDCO already holds the record. It
   is recorded as a `RoutingEvent` with no actor, because nobody routed it.
3. **Notifications**, after commit (`notify_office_completed`).
"""

from __future__ import annotations

import uuid

from django.db import transaction
from django.utils import timezone

from apps.records.lifecycle import type_name_of
from apps.records.versions import latest_version

from core.enums import (
    OPEN_SEAT_STATES,
    AssignmentState,
    ClearanceStatus,
    DocumentRequestState,
    Party,
    ReviewDecision,
    SeatState,
)
from core.permissions import holds_seat

from . import revisions, routing, seats
from .models import RecordAssignment, RecordClearance, Review, ReviewerSeat, RoutingEvent

#: The specialist offices (ADR-032 §3): the only parties that clear.
SPECIALIST_PARTIES = (str(Party.ITSO), str(Party.IERC), str(Party.KTTO))

#: The two outcomes an office reviewer may record, and the verdict each writes.
#: Spelled through `ClearanceStatus` for the clearance: the wire word is the
#: office outcome it leads to when it is the round's only verdict.
CLEARED = str(ClearanceStatus.CLEARED.value)
FINDING = "finding"
OUTCOMES = {
    CLEARED: ReviewDecision.APPROVED,
    FINDING: ReviewDecision.NEGATIVE_FINDING,
}

#: The hand-back's routing reason. Nobody routed it, so IRIS states why.
HAND_BACK_REASON = "Specialist review complete."

_label = seats._label


class OfficeReviewError(Exception):
    """Understood, but not possible as asked. A 400."""


class OfficeReviewRefused(Exception):
    """The caller may not review this record for an office. A 403."""


# --- who may act, as what ------------------------------------------------------

def _seated_specialist(record, user):
    """The specialist office `user` holds an open seat for on `record`, or None."""
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return next((p for p in SPECIALIST_PARTIES if holds_seat(user, record, p)), None)


def _open_seat(record, user, party) -> ReviewerSeat:
    return (
        ReviewerSeat.objects.select_related("assignment")
        .filter(
            assignment__record=record, assignment__party=party,
            assignment__state=AssignmentState.ACTIVE, reviewer=user,
            state__in=OPEN_SEAT_STATES,
        )
        .first()
    )


def _open_document_request(record, party) -> bool:
    from apps.documents.models import DocumentRequest

    return DocumentRequest.objects.filter(
        record=record, party=party, state=DocumentRequestState.OPEN,
    ).exists()


def _blocked_reason(record, user, party):
    """Why `user` cannot clear or record a finding as `party` yet, or None."""
    seat = _open_seat(record, user, party)
    if seat is not None and seat.state == SeatState.ASSIGNED:
        return "Open the review first."
    if _open_document_request(record, party):
        return (
            f"Withdraw {_label(party)}'s document request first. An office "
            f"finishes only once it is no longer asking the author for anything."
        )
    # Its own revision request, likewise (ADR-032 §5 Amendment, IR-272).
    # Another office's request blocks nothing here.
    return revisions.office_blocked_reason(record, party)


def office_review_flags(record, user) -> dict:
    """
    What record detail tells Paper View (IR-269): the office the viewer may
    clear or record a finding as, why they cannot yet, and whether they may
    add a colleague. A rendering hint; the endpoints re-check all of it.
    """
    party = _seated_specialist(record, user) if routing.is_new_model(record) else None
    if party is None:
        return {"party": None, "label": None, "blocked": None, "assignment": None}
    seat = _open_seat(record, user, party)
    return {
        "party": party,
        "label": _label(party),
        "blocked": _blocked_reason(record, user, party),
        "assignment": seat.assignment_id if seat else None,
    }


# --- the act ------------------------------------------------------------------------

@transaction.atomic
def record_office_review(record, actor, *, outcome, comment=""):
    """
    Clear, or record a finding, for the office `actor` is seated for.

    Returns `(party, completed)`: the office, and whether this verdict
    completed its review round.
    """
    record = routing._locked(record)
    party = _seated_specialist(record, actor)
    if party is None:
        raise OfficeReviewRefused(
            "Only a reviewer seated for ITSO, IERC or KTTO on this record may "
            "clear it or record a finding."
        )
    if not routing.is_new_model(record):
        raise OfficeReviewError(
            "This record is still on the current review pipeline. Use the "
            "current decision form."
        )
    if not isinstance(outcome, str) or outcome not in OUTCOMES:
        raise OfficeReviewError(
            "An office clears a record or records a finding. Offices never "
            "reject and never publish (ADR-032 §3); RDCO decides."
        )
    comment = (comment or "").strip() if isinstance(comment, str) else ""
    if outcome == FINDING and not comment:
        raise OfficeReviewError("Say what the finding is, so RDCO and the author can act on it.")

    seat = _open_seat(record, actor, party)
    blocked = _blocked_reason(record, actor, party)
    if blocked:
        raise OfficeReviewError(blocked)

    Review.objects.create(
        record=record, reviewed_by=actor, stage=party, status=OUTCOMES[outcome],
        comment=comment, assignment=seat.assignment,
        version=latest_version(record),
    )
    try:
        completed = seats.complete_seat(seat, actor)
    except seats.SeatError as exc:
        raise OfficeReviewError(str(exc))
    return party, completed


# --- when an office completes --------------------------------------------------------

def office_completed(assignment, actor) -> None:
    """
    `assignment` has just completed (`seats._close_if_complete`). For a
    specialist office: settle its clearance, hand back to RDCO when it was the
    last one active, and notify. Any other party completing changes nothing
    here -- the Adviser's completion is accept & route's (IR-261).
    """
    party = str(assignment.party)
    if party not in SPECIALIST_PARTIES:
        return
    record = assignment.record

    finding = Review.objects.filter(
        assignment=assignment, status=ReviewDecision.NEGATIVE_FINDING,
    ).exists()
    outcome = ClearanceStatus.NOT_CLEARED if finding else ClearanceStatus.CLEARED
    clearance, _ = RecordClearance.objects.get_or_create(
        record=record, office=party, defaults={"status": outcome},
    )
    clearance.status = outcome
    clearance.reviewed_by = None
    clearance.comment = ""
    clearance.save(update_fields=["status", "reviewed_by", "comment", "updated_at"])

    rdco = _hand_back(record, party)
    _notify(record, actor, party, outcome, rdco)


def _hand_back(record, from_party):
    """
    Open RDCO's pool when no specialist office is still active (ADR-032 §3).

    Returns `("opened", assignment)` when it opened one, `("holding",
    assignment)` when RDCO already holds the record, or None while another
    office is still reviewing. Only the record types the Adviser may route
    reach an office, so a Proposal never gets here; the check stays so a
    hand-back can never be the way RDCO enters a Proposal.
    """
    if type_name_of(record) not in routing.ROUTABLE_TYPES:
        return None
    active = RecordAssignment.objects.filter(record=record, state=AssignmentState.ACTIVE)
    if active.filter(party__in=SPECIALIST_PARTIES).exists():
        return None
    held = active.filter(party=Party.RDCO).first()
    if held is not None:
        return ("holding", held)
    now = timezone.now()
    opened = RecordAssignment.objects.create(
        record=record, party=Party.RDCO, opened_at=now, reason=HAND_BACK_REASON,
    )
    RoutingEvent.objects.create(
        record=record, actor=None, from_party=from_party, to_party=Party.RDCO,
        reason=HAND_BACK_REASON, group_id=uuid.uuid4(), created_at=now,
    )
    return ("opened", opened)


def _notify(record, actor, party, outcome, rdco):
    from apps.notifications.services import notify_office_completed

    rdco_holders = []
    if rdco is not None and rdco[0] == "holding":
        rdco_holders = list(
            rdco[1].seats.filter(state__in=OPEN_SEAT_STATES).select_related("reviewer")
        )
        rdco_holders = [s.reviewer for s in rdco_holders]
    transaction.on_commit(lambda: notify_office_completed(
        record,
        actor=actor,
        office_label=_label(party),
        outcome_label=str(ClearanceStatus(outcome).label),
        handed_back=rdco is not None and rdco[0] == "opened",
        rdco_holding=rdco is not None and rdco[0] == "holding",
        rdco_holders=rdco_holders,
    ))
