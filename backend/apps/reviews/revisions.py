"""
A reviewer asks the owners for a revision, or withdraws the ask (ADR-032 §5
and its 2026-10-08 Amendment; IR-272).

**The act.** A holder of an *opened* seat on a record on the new model -- the
Adviser, an office reviewer or RDCO -- asks the owners to revise the record
itself, with a reason. It writes the seat holder's own `declined` `Review`
("Resubmission requested"), carrying the reason and the version it was made
against, and the `ResubmissionRequest` that tracks it. The seat stays
`in_review` and no assignment closes: the party reviews the next version.
`RecordClearance` is not touched. *Changes requested* is read from the open
request, so an office's earlier completed review round still stands, and the
Adviser and RDCO, who hold no clearance, are shown the same way.

**One open request per party, not per person.** A second reviewer from a
party that already asked is refused and pointed at the request that is open.

**What an open request blocks** (`decision_blocked_reason`,
`office_blocked_reason`):

- while **any** request is open, every decision. Today that is accept &
  route; IR-270 and IR-271 call `decision_blocked_reason` for accept &
  publish, keep unlisted, reject and the Proposal decisions;
- while an office's **own** request is open, every seat of that office is
  refused Clear and Record finding. Other offices may still clear: their
  outcome survives the new version, which is what clearance-aware
  resubmission preserves (ADR-003).

Routing and document requests still work.

**Withdrawal.** Any seat holder of the requesting party may withdraw its open
request. No reason is asked for. Nothing else changes: whoever withdraws holds
an open seat, so their office has not finished, and completes as it would
have.

The owners are told of both, after commit. The owner answers every open
request at once with a new version (`new_version.py`, IR-273).
"""

from __future__ import annotations

from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.records.versions import latest_version
from core.enums import (
    OPEN_SEAT_STATES,
    AssignmentState,
    Party,
    ResubmissionRequestState,
    ReviewDecision,
    SeatState,
)

from . import routing, seats
from .models import ResubmissionRequest, Review, ReviewerSeat

#: The parties that may ask for a revision, in the tracker's order.
ASKING_PARTIES = (
    str(Party.ADVISER), str(Party.ITSO), str(Party.IERC), str(Party.KTTO), str(Party.RDCO),
)

_label = seats._label


class RevisionError(Exception):
    """Understood, but not possible as asked. A 400."""


class RevisionRefused(Exception):
    """The caller may not ask for, or withdraw, this revision. A 403."""


# --- what is open --------------------------------------------------------------------

def open_requests(record):
    """Every open revision request on `record`, oldest first."""
    return (
        ResubmissionRequest.objects.filter(record=record, state=ResubmissionRequestState.OPEN)
        .order_by("created_at", "pk")
    )


def open_request_for(record, party) -> Optional[ResubmissionRequest]:
    """`party`'s open revision request on `record`, or None."""
    return open_requests(record).filter(party=str(party)).first()


def _join(labels: list[str]) -> str:
    return labels[0] if len(labels) == 1 else f"{', '.join(labels[:-1])} and {labels[-1]}"


def decision_blocked_reason(record) -> Optional[str]:
    """
    Why nobody may decide `record` now, or None. Every decision asks this:
    one is refused while any revision request is open (ADR-032 §11).
    """
    parties = list(dict.fromkeys(open_requests(record).values_list("party", flat=True)))
    if not parties:
        return None
    who = _join([_label(p) for p in parties])
    return (
        f"Waiting on the author: {who} asked for a revision. Nothing can be "
        f"decided until the owner submits a new version, or the request is withdrawn."
    )


def office_blocked_reason(record, party) -> Optional[str]:
    """Why `party`'s reviewers may not clear or record a finding now, or None."""
    if open_request_for(record, party) is None:
        return None
    return (
        f"{_label(party)} has asked the author for a revision. Review the new "
        f"version once it is submitted, or withdraw the request."
    )


# --- who may ask, as what --------------------------------------------------------------

def _open_seat(record, user) -> Optional[ReviewerSeat]:
    """
    `user`'s open seat on an active assignment of `record`, or None. A user
    staffs one party, so there is at most one; the order only makes the
    answer deterministic.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    held = {
        seat.assignment.party: seat
        for seat in ReviewerSeat.objects.select_related("assignment").filter(
            assignment__record=record, assignment__state=AssignmentState.ACTIVE,
            reviewer=user, state__in=OPEN_SEAT_STATES,
        )
    }
    return next((held[p] for p in ASKING_PARTIES if p in held), None)


def revision_flags(record, user, *, readable: bool) -> dict:
    """
    What record detail tells Paper View (IR-272). A rendering hint; the
    endpoints re-check all of it.

    - `party`, `label`: the party the viewer may ask for a revision as;
    - `blocked`: why they cannot ask yet;
    - `withdrawable`: the id of their party's open request, which they may
      withdraw instead -- a party asks once;
    - `decision_blocked`: why nobody may decide the record now;
    - `open`: every open request, for the owner's *Action required*. Who
      asked and why are review content, `None` to anyone who may not read
      the review (IR-479);
    - `new_version`: for an owner, the version that would answer them
      (`new_version.new_version_hint`, IR-273).
    """
    from .new_version import new_version_hint

    new_model = routing.is_new_model(record)
    requests = list(
        open_requests(record).select_related("requested_by", "review__version")
    ) if new_model else []

    seat = _open_seat(record, user) if new_model else None
    party = seat.assignment.party if seat else None
    mine = next((r for r in requests if r.party == party), None) if party else None

    return {
        "party": party,
        "label": _label(party) if party else None,
        "blocked": (
            "Open the review first." if seat is not None and seat.state == SeatState.ASSIGNED
            else None
        ),
        "withdrawable": mine.pk if mine else None,
        "decision_blocked": decision_blocked_reason(record) if requests else None,
        "open": [request_payload(r, readable=readable) for r in requests],
        "new_version": new_version_hint(record, user) if requests else None,
    }


def request_payload(request: ResubmissionRequest, *, readable: bool) -> dict:
    """One open revision request, as record detail states it."""
    version = request.review.version if request.review_id else None
    return {
        "id": request.pk,
        "party": request.party,
        "label": _label(request.party),
        "reason": request.reason if readable else None,
        "requested_by": (
            request.requested_by.get_full_name() if readable and request.requested_by else None
        ),
        # The version it was made against: its review's (ADR-032 §5 Amendment).
        "version": version.number if version else None,
        "created_at": request.created_at.isoformat(),
    }


# --- the acts -------------------------------------------------------------------------

@transaction.atomic
def request_revision(record, actor, *, reason) -> ResubmissionRequest:
    """
    Ask the owners for a revision, as the party `actor` holds an open seat
    for. Who comes first, then what (ADR-022 §Amendment 4): a caller with no
    seat here is a 403 whatever state the record is in.
    """
    record = routing._locked(record)
    seat = _open_seat(record, actor)
    if seat is None:
        raise RevisionRefused(
            "Only a reviewer holding this record's review may ask for a revision."
        )
    if not routing.is_new_model(record):
        raise RevisionError(
            "This record is still on the current review pipeline. Use the "
            "current decision form."
        )
    reason = reason.strip() if isinstance(reason, str) else ""
    if not reason:
        raise RevisionError("Say what needs revising, so the author can act on it.")
    if seat.state == SeatState.ASSIGNED:
        raise RevisionError("Open the review first.")
    party = seat.assignment.party
    if open_request_for(record, party) is not None:
        raise RevisionError(
            f"A revision request from {_label(party)} is already open. A party "
            f"asks once; withdraw that request to ask differently."
        )

    review = Review.objects.create(
        record=record, reviewed_by=actor, stage=party, status=ReviewDecision.DECLINED,
        comment=reason, assignment=seat.assignment, version=latest_version(record),
    )
    request = ResubmissionRequest.objects.create(
        record=record, party=party, assignment=seat.assignment, review=review,
        requested_by=actor, reason=reason, created_at=review.created_at,
    )

    from apps.notifications.services import notify_revision_requested

    transaction.on_commit(lambda: notify_revision_requested(request, party_label=_label(party)))
    return request


@transaction.atomic
def withdraw_revision_request(record, actor, request_id) -> ResubmissionRequest:
    """
    Withdraw the open request `request_id` on `record`. Any seat holder of
    the party that asked may (party, not person); a missing id is a
    `ResubmissionRequest.DoesNotExist`, which the view answers with a 404.
    """
    record = routing._locked(record)
    request = ResubmissionRequest.objects.get(record=record, pk=request_id)
    party = request.party
    seat = _open_seat(record, actor)
    if seat is None or seat.assignment.party != party:
        raise RevisionRefused(
            f"Only a reviewer for {_label(party)} may withdraw its revision request."
        )
    if not routing.is_new_model(record):
        raise RevisionError(
            "This record is still on the current review pipeline. Use the "
            "current decision form."
        )
    if request.state != ResubmissionRequestState.OPEN:
        raise RevisionError("Only an open revision request can be withdrawn.")

    request.state = ResubmissionRequestState.WITHDRAWN
    request.resolved_by = actor
    request.resolved_at = timezone.now()
    request.save(update_fields=["state", "resolved_by", "resolved_at"])

    from apps.notifications.services import notify_revision_withdrawn

    transaction.on_commit(lambda: notify_revision_withdrawn(
        request, party_label=_label(party), withdrawn_by=actor,
    ))
    return request
