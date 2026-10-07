"""
Adviser-first entry and routing into office pools (ADR-032 §1, §3, §4; IR-261).

**A new-model slice, beside the legacy pipeline.** A record is on the new
model when its stored `pipeline_status` is `in_review`; the legacy lifecycle
table has no edge from that status, so the two never act on the same record.
Until IR-260's cutover, only `enter_at_adviser()` puts a record there -- the
demo seed and the tests call it, and `POST /records/<id>/submit/` stays on the
legacy pipeline (decided 2026-10-07). IR-260 makes submission call it.

**Two acts, one core.**

- *Accept & route* (the record's Adviser, Thesis/Research or Project only)
  accepts the work -- an `approved` `Review` at stage `adviser` -- finishes the
  Adviser's seat, which completes the Adviser's assignment, and routes.
- *Route* (an office or RDCO seat holder) sends the record onward; the
  router's own assignment stays active.

Both go through `_plan()` then `_apply()`: everything that can refuse is
checked before anything is written, so a refusal leaves no trace.

**Routing into a pool.** A target office gets an active assignment with no
seat -- its pool -- unless the router nominated a member, who is seated
(`source=nominated`). A pending `RecordClearance` is created for a clearing
office that has none; an existing one, `cleared` included, is never reset
(ADR-021 §6, kept by ADR-032 §4). A target already holding the record is
refused unless a nominee is named, in which case only the seat is added: a
route never silently does nothing.

Refusals: `RoutingRefused` is a 403 (who may act), `RoutingError` a 400 (what
was asked). The 404 for a record the caller cannot see is the view's.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from core.enums import (
    AssignmentState,
    ClearanceStatus,
    Office,
    Party,
    PipelineStatus,
    RecordTypeName,
    ReviewDecision,
    SeatState,
)
from core.permissions import OFFICE_PARTY_BY_ROLE, holds_seat, is_office_member

from . import seats
from .models import RecordAssignment, RecordClearance, Review, ReviewerSeat, RoutingEvent

#: ADR-032 §4's party graph: who may route to whom. Nothing routes to the
#: Adviser or to RDCO -- RDCO is opened by the hand-back (IR-269), never by hand.
ROUTE_TARGETS = {
    str(Party.ADVISER): (str(Party.ITSO), str(Party.IERC), str(Party.KTTO)),
    str(Party.ITSO): (str(Party.IERC), str(Party.KTTO)),
    str(Party.IERC): (str(Party.ITSO), str(Party.KTTO)),
    str(Party.KTTO): (str(Party.ITSO), str(Party.IERC)),
    str(Party.RDCO): (str(Party.ITSO), str(Party.IERC), str(Party.KTTO)),
}

#: The parties a seat holder can route onward *as*, in the order checked.
ONWARD_PARTIES = (str(Party.ITSO), str(Party.IERC), str(Party.KTTO), str(Party.RDCO))

#: The record types the Adviser may route. A Proposal is decided by its
#: Adviser alone and never routed (ADR-032 §2).
ROUTABLE_TYPES = (RecordTypeName.THESIS_RESEARCH, RecordTypeName.PROJECT)

#: The author's ADR-018 flag that hints at each office (ADR-032 §3): shown to
#: the router, routing nothing by itself.
_HINT_FIELD = {
    str(Office.ITSO): "requested_itso",
    str(Office.IERC): "requested_ierc",
    str(Office.KTTO): "requested_ktto",
}
_HINT_TEXT = {
    str(Office.ITSO): "The author flagged possible intellectual property.",
    str(Office.IERC): "The author flagged human participants, animal subjects or sensitive data.",
    str(Office.KTTO): "The author flagged possible commercialisation.",
}
_CLEARING_OFFICES = frozenset(str(o) for o in Office)
#: The role that staffs each office party: `core.permissions`' map, inverted.
_ROLE_FOR_PARTY = {str(party): role for role, party in OFFICE_PARTY_BY_ROLE.items()}


class RoutingError(Exception):
    """Understood, but not possible as asked. A 400."""


class RoutingRefused(Exception):
    """The caller may not route this record. A 403."""


def _label(party) -> str:
    return str(Party(party).label)


def _type_name(record) -> str:
    return record.record_type.name if record.record_type else ""


def is_new_model(record) -> bool:
    """On the adviser-first model: stored `in_review` (module note)."""
    return record.pipeline_status == PipelineStatus.IN_REVIEW


# --- entry ----------------------------------------------------------------------

@transaction.atomic
def enter_at_adviser(record, actor=None) -> RecordAssignment:
    """
    Put `record` on the new model at its Adviser (ADR-032 §1).

    `in_review`, an active Adviser assignment with an `entry` seat for
    `record.adviser`, and the submitter's movement in as a routing event. No
    intake assignment is ever opened. Refuses a record with no Adviser, since
    nobody could review it, and one already in the workflow.
    """
    if record.adviser_id is None:
        raise RoutingError("A record enters at its Adviser, and this one names none.")
    if record.pipeline_status not in (PipelineStatus.DRAFT, PipelineStatus.IN_REVIEW):
        raise RoutingError("Only a draft can enter the review workflow.")
    if RecordAssignment.objects.filter(record=record, state=AssignmentState.ACTIVE).exists():
        raise RoutingError("This record is already in the review workflow.")

    record.pipeline_status = PipelineStatus.IN_REVIEW
    record.save(update_fields=["pipeline_status", "updated_at"])
    now = timezone.now()
    assignment = RecordAssignment.objects.create(
        record=record, party=Party.ADVISER, opened_at=now,
    )
    seats.seat_entry(assignment)
    RoutingEvent.objects.create(
        record=record, actor=actor, from_party=None, to_party=Party.ADVISER,
        group_id=uuid.uuid4(), created_at=now,
    )
    return assignment


# --- who may route, as what -----------------------------------------------------

def _may_accept_and_route(record, user) -> bool:
    return (
        is_new_model(record)
        and _type_name(record) in ROUTABLE_TYPES
        and user is not None
        and record.adviser_id == getattr(user, "pk", None)
        and holds_seat(user, record, Party.ADVISER)
    )


def _route_as(record, user):
    """The office party `user` holds an open seat for, or None."""
    if not is_new_model(record) or user is None:
        return None
    return next((p for p in ONWARD_PARTIES if holds_seat(user, record, p)), None)


def routing_flags(record, user) -> dict:
    """
    What record detail tells Paper View (IR-261): whether to offer *Accept &
    route…*, and the party *Route to office…* acts as. A rendering hint; the
    endpoints re-check both.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return {"accept_and_route": False, "route_as": None}
    return {
        "accept_and_route": _may_accept_and_route(record, user),
        "route_as": None if _type_name(record) not in ROUTABLE_TYPES else _route_as(record, user),
    }


def _require_routable(record):
    if _type_name(record) == RecordTypeName.PROPOSAL:
        raise RoutingError(
            "A Proposal is decided by its Adviser alone and is never routed to an office."
        )
    if not is_new_model(record):
        raise RoutingError(
            "This record is still on the current review pipeline, which routes it "
            "itself. Use the current decision form."
        )


def _from_party_for(record, user, *, accepting: bool) -> str:
    _require_routable(record)
    if accepting:
        if not _may_accept_and_route(record, user):
            raise RoutingRefused(
                "Only this record's Adviser, holding its review, may accept and route it."
            )
        return str(Party.ADVISER)
    party = _route_as(record, user)
    if party is None:
        raise RoutingRefused("Only a reviewer seated on this record may route it onward.")
    return party


# --- route options (the dialog's picklist) ---------------------------------------

def route_options(record, user) -> dict:
    """
    `GET /records/<id>/route-options/`: what the caller may route this record
    to, and who they may nominate in each office. Raises as the routing acts
    do, so the picklist is offered to exactly the people who could use it.
    """
    accepting = _may_accept_and_route(record, user)
    from_party = _from_party_for(record, user, accepting=accepting)
    active = set(
        RecordAssignment.objects.filter(record=record, state=AssignmentState.ACTIVE)
        .values_list("party", flat=True)
    )
    User = get_user_model()
    targets = []
    for party in ROUTE_TARGETS[from_party]:
        members = [
            {"id": u.pk, "name": u.get_full_name() or u.email}
            for u in User.objects.filter(
                is_active=True, role__name=_ROLE_FOR_PARTY[party],
            ).order_by("last_name", "first_name", "pk")
        ]
        hint_field = _HINT_FIELD.get(party)
        targets.append({
            "party": party,
            "label": _label(party),
            "members": members,
            "already_holds": party in active,
            "author_hint": (
                _HINT_TEXT[party] if hint_field and getattr(record, hint_field, False) else None
            ),
        })
    return {
        "from_party": from_party,
        "from_label": _label(from_party),
        "accept": accepting,
        "targets": targets,
    }


# --- the routing core -------------------------------------------------------------

@dataclass
class _Target:
    party: str
    nominee: object = None
    assignment: RecordAssignment | None = None


@dataclass
class _Plan:
    from_party: str
    reason: str
    targets: list[_Target] = field(default_factory=list)


def _plan(record, from_party, to, reason) -> _Plan:
    """Validate a routing request completely, writing nothing."""
    reason = (reason or "").strip()
    if not reason:
        raise RoutingError("Give a reason for routing, so the office knows why it was asked.")
    if not isinstance(to, list) or not to:
        raise RoutingError("Choose at least one office to route to.")

    allowed = ROUTE_TARGETS[from_party]
    active = {
        a.party: a
        for a in RecordAssignment.objects.filter(record=record, state=AssignmentState.ACTIVE)
    }
    User = get_user_model()
    plan = _Plan(from_party=from_party, reason=reason)
    seen = set()
    for entry in to:
        party = str(entry.get("party", "")) if isinstance(entry, dict) else ""
        if party not in allowed:
            raise RoutingError(
                f"{_label(from_party)} cannot route to "
                f"{_label(party) if party in Party.values else repr(party)}. "
                f"It may route to {', '.join(_label(p) for p in allowed)}."
            )
        if party in seen:
            raise RoutingError(f"{_label(party)} is listed twice.")
        seen.add(party)

        nominee = None
        nominee_id = entry.get("nominee")
        if nominee_id not in (None, ""):
            try:
                nominee = User.objects.filter(pk=int(nominee_id), is_active=True).first()
            except (TypeError, ValueError):
                nominee = None
            if nominee is None or not is_office_member(nominee, party):
                raise RoutingError(f"The nominee is not a member of {_label(party)}.")

        held = active.get(party)
        if held is not None:
            if nominee is None:
                raise RoutingError(
                    f"{_label(party)} already has this record. Nominate someone to add "
                    f"a reviewer, or ask a seat holder there to add one."
                )
            if held.seats.exclude(state=SeatState.WITHDRAWN).filter(reviewer=nominee).exists():
                raise RoutingError(f"The nominee already holds a seat at {_label(party)}.")
        plan.targets.append(_Target(party=party, nominee=nominee, assignment=held))
    return plan


def _apply(record, actor, plan: _Plan) -> list[_Target]:
    """Write a validated plan. Returns the targets that newly opened."""
    now = timezone.now()
    group = uuid.uuid4()
    opened = []
    for target in plan.targets:
        if target.assignment is None:
            target.assignment = RecordAssignment.objects.create(
                record=record, party=target.party, opened_by=actor, opened_at=now,
                reason=plan.reason,
            )
            opened.append(target)
            if target.party in _CLEARING_OFFICES:
                # Never reset: a `cleared` office stays cleared (ADR-032 §4).
                RecordClearance.objects.get_or_create(
                    record=record, office=target.party,
                    defaults={"status": ClearanceStatus.PENDING},
                )
        if target.nominee is not None:
            seats.nominate(target.assignment, actor, target.nominee)
        RoutingEvent.objects.create(
            record=record, actor=actor, from_party=plan.from_party,
            to_party=target.party, reason=plan.reason, group_id=group, created_at=now,
        )
    return opened


def _notify(record, actor, plan, opened, *, accepted):
    from apps.notifications.services import notify_routed

    targets = [t.party for t in plan.targets]
    transaction.on_commit(lambda: notify_routed(
        record,
        actor=actor,
        from_label=_label(plan.from_party),
        target_labels=[_label(p) for p in targets],
        opened_parties=[t.party for t in opened],
        nominees=[(t.nominee, _label(t.party)) for t in plan.targets if t.nominee is not None],
        reason=plan.reason,
        accepted=accepted,
    ))


@transaction.atomic
def accept_and_route(record, actor, *, to, reason):
    """
    The Adviser accepts the work and routes it to one or more offices
    (ADR-032 §3). The Adviser's review is an `approved` `Review` carrying the
    reason; their seat is done, so their assignment completes. The record stays
    `in_review`.
    """
    from_party = _from_party_for(record, actor, accepting=True)
    plan = _plan(record, from_party, to, reason)

    adviser_seat = (
        ReviewerSeat.objects.select_related("assignment")
        .filter(
            assignment__record=record, assignment__party=Party.ADVISER,
            assignment__state=AssignmentState.ACTIVE, reviewer=actor,
        )
        .exclude(state__in=(SeatState.DONE, SeatState.WITHDRAWN))
        .first()
    )
    Review.objects.create(
        record=record, reviewed_by=actor, stage=Party.ADVISER,
        status=ReviewDecision.APPROVED, comment=plan.reason,
        assignment=adviser_seat.assignment,
    )
    seats.complete_seat(adviser_seat, actor)
    opened = _apply(record, actor, plan)
    _notify(record, actor, plan, opened, accepted=True)
    return plan


@transaction.atomic
def route(record, actor, *, to, reason):
    """An office or RDCO seat holder routes onward; their own turn stays active."""
    from_party = _from_party_for(record, actor, accepting=False)
    plan = _plan(record, from_party, to, reason)
    opened = _apply(record, actor, plan)
    _notify(record, actor, plan, opened, accepted=False)
    return plan
