"""
Reviewer seats: who is reviewing a record for each party (ADR-032 §4, IR-415).

An office's `RecordAssignment` says "ITSO has this record". A `ReviewerSeat`
says "this ITSO member is reviewing it". A routed record lands in the office's
**pool** -- an active assignment with no seat -- and a person comes to hold a
seat in one of five ways (`SeatSource`):

- **entry**: the record's Adviser, seated when its Adviser assignment opens;
- **claimed**: an office member takes the record from the pool;
- **assigned**: an office coordinator seats a member;
- **nominated**: whoever routed the record named the member (IR-261 calls
  `nominate()` from `route()`);
- **added**: a seat holder brings in a colleague from their *own* office.
  Sending the record to *another* office is routing, a different act.

**The office completion rule** (§4) is `office_complete()`: at least one seat,
every seat not withdrawn is `done`, and the party has no open resubmission
request. `complete_seat()` is how a reviewer's part ends; IR-269 calls it when
a seat holder clears or records a finding. When an assignment completes,
`office_review.office_completed()` settles a specialist office's clearance and
hands back to RDCO.

**What closes an assignment.** Only three things: this module's completion
rule (`_close_if_complete`), a Decision (`decisions`, which withdraws), and a
soft delete (`withdrawal`). The legacy `shadow.sync()` reconciliation is
retired (IR-274).

**Who may do what is not decided here.** Each act names the predicate from
`core.permissions` it needs and raises `SeatRefused` (a 403) when it fails;
`SeatError` (a 400) is an act that is understood but not possible now.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.enums import (
    OPEN_SEAT_STATES,
    AssignmentState,
    Party,
    PipelineStatus,
    ResubmissionRequestState,
    SeatSource,
    SeatState,
)
from core.permissions import (
    OFFICE_PARTY_BY_ROLE,
    holds_seat,
    is_office_coordinator,
    is_office_member,
    office_parties_of,
)

from .models import RecordAssignment, ResubmissionRequest, ReviewerSeat

#: The parties that are offices, and so have members, a pool and coordinators.
OFFICE_PARTIES = frozenset(str(p) for p in OFFICE_PARTY_BY_ROLE.values())


class SeatError(Exception):
    """An act on a seat that is understood but not possible now. A 400."""


class SeatRefused(Exception):
    """The caller may not do this to this seat or assignment. A 403."""


def _label(party) -> str:
    return str(Party(party).label)


def _name(user) -> str:
    return user.get_full_name() or user.email


def _locked(assignment) -> RecordAssignment:
    """Re-read `assignment` under a row lock, so two claims cannot both win."""
    return RecordAssignment.objects.select_for_update().select_related("record").get(
        pk=assignment.pk
    )


def _require_active(assignment):
    if assignment.state != AssignmentState.ACTIVE:
        raise SeatError(
            f"{_label(assignment.party)} is no longer reviewing this record."
        )


def _live_seats(assignment):
    return assignment.seats.exclude(state=SeatState.WITHDRAWN)


def _seat(assignment, reviewer, *, source, by) -> ReviewerSeat:
    """
    Seat `reviewer` on `assignment`. Shared by every act that adds a person.

    Caller holds the assignment's row lock. The reviewer must staff the office:
    a seat is always someone reviewing *for* that office.
    """
    _require_active(assignment)
    if not is_office_member(reviewer, assignment.party):
        # Unnamed: any user id can be sent here, and a refusal must not turn
        # into a way of looking up who someone is.
        raise SeatError(
            f"That person is not a member of {_label(assignment.party)}. "
            f"To involve another office, route the record to it instead."
        )
    if _live_seats(assignment).filter(reviewer=reviewer).exists():
        raise SeatError(
            f"{_name(reviewer)} already holds a seat on this review."
        )
    try:
        with transaction.atomic():
            return ReviewerSeat.objects.create(
                assignment=assignment, reviewer=reviewer, source=source,
                assigned_by=by, assigned_at=timezone.now(),
            )
    except IntegrityError:
        # The partial unique constraint, reached by a concurrent request the
        # row lock did not cover.
        raise SeatError(f"{_name(reviewer)} already holds a seat on this review.")


# --- the office completion rule -----------------------------------------------

def office_complete(assignment) -> bool:
    """
    ADR-032 §4: may `assignment` complete?

    It has at least one seat, every seat that was not withdrawn is `done`, and
    its party has no open resubmission request on the record. A pool (no seat)
    is never complete: nobody has reviewed it.
    """
    live = list(_live_seats(assignment).values_list("state", flat=True))
    if not live or any(state != SeatState.DONE for state in live):
        return False
    return not ResubmissionRequest.objects.filter(
        record_id=assignment.record_id, party=assignment.party,
        state=ResubmissionRequestState.OPEN,
    ).exists()


def _close_if_complete(assignment, actor) -> bool:
    """
    Complete `assignment` when the rule holds, on a record still in review.
    """
    if assignment.record.pipeline_status != PipelineStatus.IN_REVIEW:
        return False
    if assignment.state != AssignmentState.ACTIVE or not office_complete(assignment):
        return False
    assignment.state = AssignmentState.COMPLETED
    assignment.closed_by = actor
    assignment.closed_at = timezone.now()
    assignment.save(update_fields=["state", "closed_by", "closed_at"])
    # A specialist office's clearance, the RDCO hand-back and their
    # notifications (IR-269). Here rather than in the caller, so a verdict and
    # a coordinator's withdrawal complete an office the same way.
    from .office_review import office_completed

    office_completed(assignment, actor)
    return True


# --- the acts -------------------------------------------------------------------

@transaction.atomic
def claim(assignment, user) -> ReviewerSeat:
    """
    An office member takes an unclaimed record from their office's pool.

    Only from the pool: once someone holds a seat, a colleague joins through
    *Add reviewer* or a coordinator's *Assign*, so the people already on it
    know who else is.
    """
    assignment = _locked(assignment)
    if not is_office_member(user, assignment.party):
        raise SeatRefused(
            f"Only a member of {_label(assignment.party)} may claim this review."
        )
    _require_active(assignment)
    if _live_seats(assignment).exists():
        raise SeatError(
            f"Someone at {_label(assignment.party)} has already taken this review. "
            f"A seat holder can add you, or a coordinator can assign you."
        )
    return _seat(assignment, user, source=SeatSource.CLAIMED, by=user)


def require_coordinator(user, party):
    """Refuse anyone but a coordinator of `party` (ADR-032 §4: own office only)."""
    if not is_office_coordinator(user, party):
        raise SeatRefused(
            f"Only a coordinator of {_label(party)} may assign or change its reviewers."
        )


@transaction.atomic
def assign(assignment, coordinator, reviewer) -> ReviewerSeat:
    """A coordinator seats a member of their own office."""
    assignment = _locked(assignment)
    require_coordinator(coordinator, assignment.party)
    return _seat(assignment, reviewer, source=SeatSource.ASSIGNED, by=coordinator)


@transaction.atomic
def add_reviewer(assignment, holder, reviewer) -> ReviewerSeat:
    """
    A seat holder brings in a colleague from their own office (ADR-032 §4).

    Never another office's member: that is routing, and the two stay separate
    acts, so `_seat` refuses a reviewer who does not staff this party.
    """
    assignment = _locked(assignment)
    if str(assignment.party) not in OFFICE_PARTIES:
        raise SeatError(
            f"{_label(assignment.party)} is not an office, so there is nobody to add."
        )
    if not holds_seat(holder, assignment.record, assignment.party):
        raise SeatRefused(
            f"Only a reviewer seated for {_label(assignment.party)} may add a colleague."
        )
    return _seat(assignment, reviewer, source=SeatSource.ADDED, by=holder)


def _member_options(assignment) -> dict:
    """Every active member of `assignment`'s office, marked `seated` when they hold a live seat."""
    from django.contrib.auth import get_user_model

    roles = [role for role, party in OFFICE_PARTY_BY_ROLE.items() if str(party) == str(assignment.party)]
    seated = set(_live_seats(assignment).values_list("reviewer_id", flat=True))
    members = get_user_model().objects.filter(
        is_active=True, role__name__in=roles,
    ).order_by("last_name", "first_name", "pk")
    return {
        "assignment": assignment.pk,
        "party": str(assignment.party),
        "party_label": _label(assignment.party),
        "members": [
            {"id": u.pk, "name": u.get_full_name() or f"Member #{u.pk}", "seated": u.pk in seated}
            for u in members
        ],
    }


def add_reviewer_options(assignment, holder) -> dict:
    """
    Who `holder` may add to `assignment` (IR-269): every active member of the
    office, marked `seated` when they already hold a live seat on it. Refused
    as `add_reviewer` is: the office must be one, the holder seated on it.
    """
    if str(assignment.party) not in OFFICE_PARTIES:
        raise SeatError(
            f"{_label(assignment.party)} is not an office, so there is nobody to add."
        )
    if not holds_seat(holder, assignment.record, assignment.party):
        raise SeatRefused(
            f"Only a reviewer seated for {_label(assignment.party)} may add a colleague."
        )
    return _member_options(assignment)


def assign_options(assignment, coordinator) -> dict:
    """
    Who a coordinator may assign to `assignment` (IR-268): the same list,
    refused as `assign` is. Its own list, not *Add reviewer*'s, because that
    one is served only to a seat holder and a coordinator assigning from the
    pool holds no seat.
    """
    require_coordinator(coordinator, assignment.party)
    _require_active(assignment)
    return _member_options(assignment)


@transaction.atomic
def nominate(assignment, router, reviewer) -> ReviewerSeat:
    """
    Seat the member the router named when routing (ADR-032 §4, IR-261).

    The router's authority to route is `route()`'s to check; this checks only
    that the nominee belongs to the office they were nominated for.
    """
    assignment = _locked(assignment)
    return _seat(assignment, reviewer, source=SeatSource.NOMINATED, by=router)


def _require_open(seat):
    if seat.state not in OPEN_SEAT_STATES:
        raise SeatError(f"This seat is {seat.get_state_display().lower()}, so it cannot change.")


@transaction.atomic
def withdraw(seat, coordinator) -> ReviewerSeat:
    """
    A coordinator takes a seat away. A finished seat is history and stays.

    Withdrawing the last unfinished seat can complete the office, when every
    other seat is done (new-model records only, as `_close_if_complete` says).
    """
    assignment = _locked(seat.assignment)
    seat = ReviewerSeat.objects.select_for_update().get(pk=seat.pk)
    require_coordinator(coordinator, seat.assignment.party)
    _require_active(assignment)
    _require_open(seat)
    seat.state = SeatState.WITHDRAWN
    seat.save(update_fields=["state"])
    _close_if_complete(assignment, coordinator)
    return seat


@transaction.atomic
def reassign(seat, coordinator, reviewer) -> ReviewerSeat:
    """A coordinator moves an unfinished seat to another member. Returns the new seat."""
    assignment = _locked(seat.assignment)
    seat = ReviewerSeat.objects.select_for_update().get(pk=seat.pk)
    require_coordinator(coordinator, seat.assignment.party)
    _require_active(assignment)
    _require_open(seat)
    if seat.reviewer_id == reviewer.pk:
        raise SeatError(f"{_name(reviewer)} already holds this seat.")
    seat.state = SeatState.WITHDRAWN
    seat.save(update_fields=["state"])
    return _seat(assignment, reviewer, source=SeatSource.ASSIGNED, by=coordinator)


@transaction.atomic
def open_review(seat, user) -> ReviewerSeat:
    """
    *Open review* (ADR-032 §4): `assigned` -> `in_review`, stamping `opened_at`.

    Opening a seat already in review changes nothing, so a second click, or a
    second tab, never moves the time-on-task start.
    """
    seat = ReviewerSeat.objects.select_for_update().select_related("assignment").get(pk=seat.pk)
    if seat.reviewer_id != getattr(user, "pk", None):
        raise SeatRefused("Only the reviewer holding this seat may open it.")
    _require_active(seat.assignment)
    if seat.state == SeatState.IN_REVIEW:
        return seat
    if seat.state != SeatState.ASSIGNED:
        raise SeatError(f"This seat is {seat.get_state_display().lower()}, so it cannot be opened.")
    seat.state = SeatState.IN_REVIEW
    seat.opened_at = timezone.now()
    seat.save(update_fields=["state", "opened_at"])
    return seat


@transaction.atomic
def complete_seat(seat, actor=None) -> bool:
    """
    A reviewer's part is finished: the seat becomes `done`. Returns whether the
    office's assignment completed with it.

    IR-269 calls this when a seat holder clears or records a finding; the
    verdict itself is their `Review`, never the seat.
    """
    assignment = _locked(seat.assignment)
    seat = ReviewerSeat.objects.select_for_update().get(pk=seat.pk)
    _require_active(assignment)
    _require_open(seat)
    seat.state = SeatState.DONE
    seat.done_at = timezone.now()
    seat.save(update_fields=["state", "done_at"])
    return _close_if_complete(assignment, actor)


# --- the Adviser's entry seat --------------------------------------------------

def seat_entry(assignment) -> ReviewerSeat | None:
    """
    The Adviser's entry seat, when the Adviser assignment opens (ADR-032 §4).

    No seat when the record names no Adviser, or the Adviser already holds one.
    """
    adviser_id = assignment.record.adviser_id
    if str(assignment.party) != Party.ADVISER or adviser_id is None:
        return None
    if _live_seats(assignment).filter(reviewer_id=adviser_id).exists():
        return None
    return ReviewerSeat.objects.create(
        assignment=assignment, reviewer_id=adviser_id, source=SeatSource.ENTRY,
        assigned_at=assignment.opened_at,
    )


# --- what the API reads -------------------------------------------------------

def seat_payload(seat) -> dict:
    """One seat, as every seat endpoint and the record's `my_seats` state it."""
    assignment = seat.assignment
    return {
        "id": seat.pk,
        "assignment": assignment.pk,
        "record": assignment.record_id,
        "party": assignment.party,
        "party_label": _label(assignment.party),
        "reviewer": seat.reviewer_id,
        "reviewer_name": _name(seat.reviewer) if seat.reviewer else None,
        "state": seat.state,
        "state_label": seat.get_state_display(),
        "source": seat.source,
        "assigned_by": seat.assigned_by_id,
        "assigned_at": seat.assigned_at.isoformat() if seat.assigned_at else None,
        "opened_at": seat.opened_at.isoformat() if seat.opened_at else None,
        "done_at": seat.done_at.isoformat() if seat.done_at else None,
    }


def my_seats(record, user) -> list[dict]:
    """
    `user`'s own seats on `record`, oldest first, withdrawn ones left out.

    Only the viewer's own: nobody sees another reviewer's seats here (§9).
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return []
    seats = (
        ReviewerSeat.objects.filter(assignment__record=record, reviewer=user)
        .exclude(state=SeatState.WITHDRAWN)
        .select_related("assignment", "reviewer")
        .order_by("assigned_at", "pk")
    )
    return [seat_payload(s) for s in seats]


def review_access(user) -> dict:
    """
    `review_access` on `GET /users/me/` (spec Appendix D · B3, built once here).

    - `my_reviews`: the user holds or has held a seat, or is a member of an
      office, whose pool lives on My Reviews even before they hold any seat.
    - `offices`: the office parties the user is a member of.
    - `is_coordinator`: `User.is_office_coordinator`, for a member of an office.
      The flag means nothing without one (`is_office_coordinator`).
    """
    offices = sorted(office_parties_of(user))
    return {
        "my_reviews": bool(offices) or ReviewerSeat.objects.filter(reviewer=user).exists(),
        "offices": offices,
        "is_coordinator": any(is_office_coordinator(user, office) for office in offices),
    }
