"""
The Review & Routing Tracker, and the derived `workflow_state` (IR-258).

ADR-021 §4 and §14; the field-by-field mapping is §8 of
`docs/workflow_routing_architecture.md`. Everything here is **read** from rows
IR-257 dual-writes -- `RecordAssignment`, `RoutingEvent`, `ResubmissionRequest`
-- plus the `Review` and `RecordClearance` history the pipeline already keeps.
Nothing here writes, and nothing the frontend shows is worked out on the client.

**`workflow_state` is derived in one function and never stored.**
`derive_workflow_state` takes the facts as arguments, so the precedence -- the
part ADR-021 says must not be reordered -- is one readable block. Open
`DocumentRequest` rows (ADR-022, IR-262) are what make a record
`awaiting_document`.

**`can_act` answers what the server will accept today.** Under ADR-021 a party
may act when it holds an active assignment and the viewer can staff it. Until
IR-260 the pipeline is still authoritative, and it is narrower: IERC holds an
assignment at `itso_review` but may not clear there, and nobody may act on a
`declined` record. `_legacy_gate_allows` applies that narrowing, so the page
never offers an action the server would refuse. IR-260 deletes it.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from django.db.migrations.recorder import MigrationRecorder

from apps.records import lifecycle
from core.enums import (
    ASSIGNABLE_PARTIES,
    AssignmentState,
    DocumentRequestState,
    Office,
    Party,
    PipelineStatus,
    ResubmissionRequestState,
    ReviewDecision,
    RoleName,
    TrackerPartyState,
    WorkflowState,
)
from core.permissions import REVIEWER_ROLES, get_role_name

from .clearance_state import clearance_payload, resubmission_payload
from .models import RecordAssignment, ResubmissionRequest, Review, RoutingEvent
from .shadow import party_for_stage

#: The statuses at which a record is in review. The five stage values and
#: `declined` are the pipeline's spellings of it until IR-260 migrates them to
#: `in_review`; every other status is reported as itself (ADR-021 §4:
#: "terminal states pass through as-is").
IN_REVIEW_STATUSES = frozenset({
    PipelineStatus.IN_REVIEW,
    PipelineStatus.ADVISER_REVIEW,
    PipelineStatus.RDCO_INTAKE,
    PipelineStatus.ITSO_REVIEW,
    PipelineStatus.PARALLEL_REVIEW,
    PipelineStatus.RDCO_REVIEW,
    PipelineStatus.DECLINED,
})

#: Which parties a role can staff (ADR-021 §1). RDCO staffs two. An Adviser
#: staffs `adviser` only on a record whose `adviser` is that user --
#: `_staffable_parties` applies that per-record condition.
ROLE_TO_PARTIES = {
    RoleName.ADVISER: frozenset({Party.ADVISER}),
    RoleName.RDCO: frozenset({Party.INTAKE, Party.RDCO}),
    RoleName.ITSO: frozenset({Party.ITSO}),
    RoleName.IERC: frozenset({Party.IERC}),
    RoleName.KTTO: frozenset({Party.KTTO}),
}

#: The migration from which routing history exists. IR-257's backfill wrote no
#: `RoutingEvent` (§6: the old model never recorded who sent a record where, and
#: the migration does not invent it), so history before it is honestly absent.
SHADOW_BACKFILL_MIGRATION = ("reviews", "0008_backfill_shadow_assignments")

_CLEARING_OFFICES = frozenset(str(o) for o in Office)

#: The tracker's row order: the two entry parties, the three specialist
#: offices, then the decider. Fixed, so a row never moves as a record
#: progresses. Every assignable party appears exactly once.
TRACKER_ORDER = (
    Party.INTAKE, Party.ADVISER, Party.ITSO, Party.IERC, Party.KTTO, Party.RDCO,
)
assert set(TRACKER_ORDER) == set(ASSIGNABLE_PARTIES), "TRACKER_ORDER must list every party"


# --- workflow_state -----------------------------------------------------------

def derive_workflow_state(
    *,
    pipeline_status: str,
    open_resubmissions: int,
    open_document_requests: int,
    active_parties: Iterable[str],
    entry_party: str,
    entry_party_has_acted: bool,
    deciding_parties: Iterable[str],
) -> str:
    """
    ADR-021 §4, first match wins. Pure: the facts are arguments.

    `submitted` must come before `final_review`. A Proposal enters at the
    Adviser, who also decides it, so with the order reversed a Proposal nobody
    has opened would already be "in final review".
    """
    if pipeline_status not in IN_REVIEW_STATUSES:
        return str(pipeline_status)

    active = {str(p) for p in active_parties}
    deciders = {str(p) for p in deciding_parties}

    if open_resubmissions:
        return WorkflowState.AWAITING_RESUBMISSION.value
    if open_document_requests:
        return WorkflowState.AWAITING_DOCUMENT.value
    if active == {str(entry_party)} and not entry_party_has_acted:
        return WorkflowState.SUBMITTED.value
    # Non-empty: "every holder can decide" is vacuously true of nobody, and a
    # record nobody holds is not in final review.
    if active and active <= deciders:
        return WorkflowState.FINAL_REVIEW.value
    return WorkflowState.IN_REVIEW.value


def _active_assignments(record) -> list:
    return list(
        RecordAssignment.objects.filter(record=record, state=AssignmentState.ACTIVE)
        .select_related("opened_by")
        .order_by("opened_at", "pk")
    )


def _entry_party_has_acted(record, entry_party: str) -> bool:
    reviewed = any(
        party_for_stage(stage) == entry_party
        for stage in Review.objects.filter(record=record)
        .values_list("stage", flat=True).distinct()
    )
    return reviewed or RoutingEvent.objects.filter(
        record=record, from_party=entry_party
    ).exists()


def _open_document_request_parties(record) -> list[str]:
    """
    The requesting party of each open document request on `record`, one entry
    per request (ADR-022 §3.1). Its length is the open-request count.
    """
    from apps.documents.models import DocumentRequest

    return list(
        DocumentRequest.objects.filter(record=record, state=DocumentRequestState.OPEN)
        .values_list("party", flat=True)
    )


def workflow_state(record, *, active_assignments: Optional[list] = None) -> str:
    """The record's derived `workflow_state`."""
    # `derive_workflow_state` passes terminal statuses through too; returning
    # here first just skips the three queries it would not need.
    if record.pipeline_status not in IN_REVIEW_STATUSES:
        return str(record.pipeline_status)
    active = active_assignments if active_assignments is not None else _active_assignments(record)
    entry = str(lifecycle.entry_party_for(record))
    return derive_workflow_state(
        pipeline_status=record.pipeline_status,
        open_resubmissions=ResubmissionRequest.objects.filter(
            record=record, state=ResubmissionRequestState.OPEN
        ).count(),
        open_document_requests=len(_open_document_request_parties(record)),
        active_parties=[a.party for a in active],
        entry_party=entry,
        entry_party_has_acted=_entry_party_has_acted(record, entry),
        deciding_parties=lifecycle.deciding_parties_for(record),
    )


def workflow_state_label(state: str) -> str:
    for enum in (WorkflowState, PipelineStatus):
        if state in enum.values:
            return str(enum(state).label)
    return state


# --- labels -------------------------------------------------------------------

def is_staff_viewer(user) -> bool:
    return get_role_name(user) in REVIEWER_ROLES


def party_label(party: Optional[str], *, staff_viewer: bool) -> Optional[str]:
    """
    A party's display name. Intake reads "Intake & Triage" to staff and
    "Intake" to students (ADR-021 §2); the staff label is the enum's.
    """
    if not party:
        return None
    if party == Party.INTAKE and not staff_viewer:
        return "Intake"
    return str(Party(party).label)


# --- who may act --------------------------------------------------------------

def _staffable_parties(record, user) -> frozenset:
    parties = ROLE_TO_PARTIES.get(get_role_name(user), frozenset())
    if Party.ADVISER in parties and record.adviser_id != getattr(user, "pk", None):
        parties = parties - {Party.ADVISER}
    return frozenset(str(p) for p in parties)


def _legacy_gate_allows(record, user) -> frozenset:
    """
    The parties the current pipeline will actually let `user` act as.

    Temporary, and deleted by IR-260: it asks the same two predicates
    `/reviews/submit/` asks, and names the party each one admits.
    """
    from .services import _can_review, _can_submit_clearance

    allowed = set()
    if _can_review(user, record):
        by_status = {
            PipelineStatus.ADVISER_REVIEW: Party.ADVISER,
            PipelineStatus.RDCO_INTAKE: Party.INTAKE,
            PipelineStatus.RDCO_REVIEW: Party.RDCO,
        }
        party = by_status.get(record.pipeline_status)
        if party:
            allowed.add(str(party))
    can_clear, office = _can_submit_clearance(user, record)
    if can_clear and office:
        allowed.add(str(office))
    return frozenset(allowed)


def can_act(record, user, *, active_assignments: Optional[list] = None) -> list[str]:
    """
    The parties `user` may act as on `record`, in party order.

    A party qualifies when it holds an active assignment and the user can
    staff it (ADR-021 §1), narrowed by what the pipeline accepts until IR-260.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return []
    active = active_assignments if active_assignments is not None else _active_assignments(record)
    held = {a.party for a in active}
    eligible = held & _staffable_parties(record, user) & _legacy_gate_allows(record, user)
    return [str(p) for p in TRACKER_ORDER if str(p) in eligible]


def requestable_parties(record, user, *, active_assignments: Optional[list] = None) -> list[str]:
    """
    The parties `user` may ask for documents as (ADR-022 §Security).

    An active assignment the user can staff -- `can_act` without the legacy
    pipeline narrowing. A request moves nothing that narrowing protects, so
    IERC may ask for a consent form while ITSO still holds the clearance gate.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return []
    active = active_assignments if active_assignments is not None else _active_assignments(record)
    eligible = {a.party for a in active} & _staffable_parties(record, user)
    return [str(p) for p in TRACKER_ORDER if str(p) in eligible]


def _party_value(stage) -> Optional[str]:
    party = party_for_stage(stage)
    return str(party) if party else None


def _name(user) -> Optional[str]:
    return user.get_full_name() if user else None


def _iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def current_holders(record, user, *, active_assignments: Optional[list] = None) -> list[dict]:
    active = active_assignments if active_assignments is not None else _active_assignments(record)
    staff = is_staff_viewer(user)
    return [
        {
            "party": a.party,
            "label": party_label(a.party, staff_viewer=staff),
            "opened_at": _iso(a.opened_at),
            "opened_by": _name(a.opened_by),
        }
        for a in active
    ]


def workflow_fields(record, user) -> dict[str, Any]:
    """The workflow fields Record detail carries (IR-258, IR-262)."""
    active = _active_assignments(record)
    state = workflow_state(record, active_assignments=active)
    return {
        "workflow_state": state,
        "workflow_state_label": workflow_state_label(state),
        "current_holders": current_holders(record, user, active_assignments=active),
        "can_act": can_act(record, user, active_assignments=active),
        "can_request_document": requestable_parties(record, user, active_assignments=active),
    }


# --- the tracker --------------------------------------------------------------

def _party_rows(record, *, reviews: list, clearances: list, staff: bool) -> list[dict]:
    assignments: dict[str, RecordAssignment] = {}
    for a in RecordAssignment.objects.filter(record=record).order_by("opened_at", "pk"):
        assignments[a.party] = a  # last one wins: the party's latest turn

    latest_review: dict[str, Review] = {}
    for r in reviews:  # oldest first, so the last write is the latest
        party = party_for_stage(r.stage)
        if party:
            latest_review[str(party)] = r

    clearance_by_office = {c.office: c for c in clearances}
    deciders = {str(p) for p in lifecycle.deciding_parties_for(record)}
    awaiting_document = set(_open_document_request_parties(record))

    rows = []
    for member in TRACKER_ORDER:
        party = str(member)
        assignment = assignments.get(party)
        review = latest_review.get(party)
        clearance = clearance_by_office.get(party) if party in _CLEARING_OFFICES else None

        if assignment is None:
            # RDCO always decides a Thesis/Research or Project, so it is
            # awaited there, never "not requested"; on a Proposal, which the
            # Adviser may decide alone, it is not requested until routed to
            # (ADR-021 §14, stated per party as the ADR states it).
            state = (
                TrackerPartyState.AWAITING
                if party == Party.RDCO and deciders == {party}
                else TrackerPartyState.NOT_REQUESTED
            )
            at = None
        elif assignment.state == AssignmentState.ACTIVE:
            state, at = TrackerPartyState.ACTIVE, assignment.opened_at
        elif assignment.state == AssignmentState.WITHDRAWN:
            state, at = TrackerPartyState.WITHDRAWN, assignment.closed_at
        else:
            state, at = TrackerPartyState.COMPLETED, assignment.closed_at

        # An outcome belongs to a party that was actually asked. A party with
        # no assignment shows none, even if an old clearance row exists (§8.2:
        # "never requested" means no assignment at all).
        if assignment is None:
            outcome = outcome_label = None
        elif clearance is not None:
            outcome, outcome_label = clearance.status, clearance.get_status_display()
        elif review is not None:
            outcome, outcome_label = review.status, review.get_status_display()
        else:
            outcome = outcome_label = None

        rows.append({
            "party": party,
            "label": party_label(party, staff_viewer=staff),
            "state": state.value,
            "state_label": str(state.label),
            # §8.2's split of an active party: reviewing already, or
            # requested but not yet started. Meaningless for any other state.
            "started": state is TrackerPartyState.ACTIVE and review is not None,
            # §9.1's ◐: this party has asked the owner for a document and is
            # waiting on it. Independent of `state` -- a party may close its
            # assignment while its request stays open (ADR-022 §1). The key
            # is named for the workflow state this party is holding the record
            # in (§8.1), so it is spelled through that enum.
            WorkflowState.AWAITING_DOCUMENT.value: party in awaiting_document,
            "outcome": outcome,
            "outcome_label": outcome_label,
            "at": _iso(at),
            "preserved": (
                clearance_payload(clearance, last_resubmitted_at=record.last_resubmitted_at)["preserved"]
                if clearance is not None else False
            ),
        })
    return rows


def _routing_history(record, *, staff: bool) -> list[dict]:
    groups: dict[Any, dict] = {}
    for event in (
        RoutingEvent.objects.filter(record=record)
        .select_related("actor").order_by("created_at", "pk")
    ):
        group = groups.get(event.group_id)
        if group is None:
            group = groups[event.group_id] = {
                "group_id": str(event.group_id),
                "from": event.from_party,
                "from_label": party_label(event.from_party, staff_viewer=staff),
                "to": [],
                "to_labels": [],
                "actor": _name(event.actor),
                "reason": event.reason,
                "at": _iso(event.created_at),
            }
        group["to"].append(event.to_party)
        group["to_labels"].append(party_label(event.to_party, staff_viewer=staff))
    return list(groups.values())


def _routing_recorded_from() -> Optional[str]:
    app, name = SHADOW_BACKFILL_MIGRATION
    applied = (
        MigrationRecorder.Migration.objects.filter(app=app, name=name)
        .values_list("applied", flat=True).first()
    )
    return _iso(applied)


def _resubmissions(record, *, staff: bool) -> list[dict]:
    return [
        {
            "id": r.pk,
            "party": r.party,
            "label": party_label(r.party, staff_viewer=staff),
            "state": r.state,
            "state_label": r.get_state_display(),
            "reason": r.reason,
            "requested_by": _name(r.requested_by),
            "created_at": _iso(r.created_at),
            "resolved_at": _iso(r.resolved_at),
        }
        for r in ResubmissionRequest.objects.filter(record=record)
        .select_related("requested_by").order_by("created_at", "pk")
    ]


def tracker_payload(record, user) -> dict[str, Any]:
    """`GET /records/<id>/tracker/` -- §8.1 of the architecture doc."""
    from apps.documents.requests import payload as document_request_payload, requests_for

    staff = is_staff_viewer(user)
    reviews = list(
        Review.objects.filter(record=record)
        .select_related("reviewed_by").order_by("created_at", "pk")
    )
    clearances = list(record.clearances.select_related("reviewed_by").order_by("office"))
    latest_decline = next(
        (r for r in reversed(reviews) if r.status == ReviewDecision.DECLINED), None
    )

    payload = {
        "record_id": record.pk,
        "record_type": lifecycle.type_name_of(record) or None,
        **workflow_fields(record, user),
        "parties": _party_rows(record, reviews=reviews, clearances=clearances, staff=staff),
        "routing_history": _routing_history(record, staff=staff),
        "routing_recorded_from": _routing_recorded_from(),
        "reviews": [
            {
                "id": r.pk,
                "party": _party_value(r.stage),
                "label": party_label(_party_value(r.stage), staff_viewer=staff),
                "status": r.status,
                "status_label": r.get_status_display(),
                "comment": r.comment,
                "reviewed_by_name": _name(r.reviewed_by),
                "created_at": _iso(r.created_at),
            }
            for r in reviews
        ],
        "resubmissions": _resubmissions(record, staff=staff),
        "document_requests": [
            document_request_payload(r, staff_viewer=staff) for r in requests_for(record)
        ],
        "clearances": [
            clearance_payload(c, last_resubmitted_at=record.last_resubmitted_at)
            for c in clearances
        ],
        "resubmission": resubmission_payload(
            record,
            clearances=clearances,
            latest_decline_stage=latest_decline.stage if latest_decline else None,
        ),
    }
    return payload
