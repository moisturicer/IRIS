"""
The workflow as data: stages, edges, and one entry point (IR-136, ADR-002).

ADR-002 (amended 2026-09-09) decides the shape this module implements. Read the
amendment before changing anything here — several things that look like
incidental structure are load-bearing.

**Two structures, not one.** `TRANSITIONS` is an edge set; `STAGES` is a node
registry. The distinction is forced rather than stylistic: "IERC and KTTO clear
concurrently" is a property of a *node*, and no edge table can express a
parallel group. `STAGES` also declares each stage's **kind**, and that single
declaration serves three call sites that each used to re-derive it — most
importantly `resubmit_record`, which chose preserve-vs-restart by testing a set
literal, `CLEARANCE_OFFICES`. **That literal was where ADR-003's primary
research contribution lived.** It reads the table now.

**What this module does NOT do: authorize.** It answers "is this transition
legal, and where does it lead". Whether *this* user may act on *this* record
stays in `reviews.services._can_review` / `_can_submit_clearance` and the
permission layer (ADR-009, IR-165). That split is forced, not chosen:
`_can_review` checks `record.adviser_id == user.pk` — the **assigned** adviser,
not any Adviser — and a table keyed on a *role* cannot express a per-record
condition. `gate_role` below documents which office owns a gate; it never
decides who may pass it.

**Divergence from ADR-002's literal key, recorded rather than hidden.** The ADR
specifies `(from_status, event, actor_role) -> to_status`. Two departures:

1. The key here is `(from_status, event)`, with `gate_role` carried as a *field*
   on the edge instead. In IRIS the actor's role never changes the destination —
   it is a function of the stage — so putting it in the key would add a
   component that is constant per pair and imply the table discriminates on
   something it does not.
2. **Four of the eleven edges have a destination that cannot be a literal**:
   approving at `rdco_intake` depends on which offices the submitter requested
   (ADR-018), approving at `adviser_review` depends on record type, and both
   clearance paths depend on whether every office has cleared. Those edges name
   a **resolver** from the closed set in `_RESOLVERS`. This is still a
   declarative table — the routing is inspectable in one place — but it is not
   a pure lookup, and saying otherwise would be false.

**Per-instance configuration.** `STAGES` and `TRANSITIONS` below are CIT-U's
defaults. `settings.WORKFLOW_TABLE` may override either, which is what makes
ADR-005's "configuration within the instance" true without a `tenant_id` or a
migration, and how ADR-004's `RESTART_ALL` evaluation instance will differ from
production. See `load_table()`.

**Note on the "adding a fourth office requires no code change" criterion**: it is
not satisfied by this module alone and was never satisfiable as written. A table
*references* offices; it does not define them. Office identity lives in
`core.enums.Office`, `ROLE_TO_OFFICE`, `RecordClearance.office`'s choices, plus a
`RoleName` member and a seeded `Role` row. See ADR-002's amendment — the honest
criterion is one enum, one role map and this table, rather than eighteen call
sites.
"""

from dataclasses import dataclass
from enum import Enum

from django.conf import settings
from django.db import transaction

from core.enums import (
    PUBLICLY_VISIBLE_STATUSES,
    ClearanceStatus,
    Office,
    PipelineStatus,
    RecordTypeName,
    ReviewDecision,
    ReviewStage,
    RoleName,
)
from core.exceptions import InvalidPipelineTransition


class WorkflowEvent(str, Enum):
    """
    What a caller asks for. Views and services name these, never status strings.

    Deliberately not one event per gate: `APPROVE` at a sequential stage and
    `APPROVE` at a parallel one are the same intent, and `STAGES` already knows
    which kind it is landing on. One event with a stage-aware destination beats
    two events a caller has to choose between correctly.
    """

    APPROVE = "approve"
    DECLINE = "decline"
    REJECT = "reject"
    RESUBMIT = "resubmit"

    # --- stage 2 (IR-136): the record-owned edges, previously assigned by hand
    # --- in records/views.py and records/services.py.
    SUBMIT = "submit"
    MARK_COMPLETE = "mark_complete"
    REQUEST_DELETE = "request_delete"
    SOFT_DELETE = "soft_delete"
    RESTORE = "restore"


class StageKind(str, Enum):
    """
    Sequential gate or parallel clearance group.

    Not in `core.enums`: those are values persisted in a column. This is a
    property of the *table*, never written to the database.
    """

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


@dataclass(frozen=True)
class Stage:
    """
    One node of the workflow.

    `records_as` is the `ReviewStage` a `Review` row gets when a review lands
    here — but only for sequential gates. A parallel stage leaves it `None`
    because the value is the **acting office**, resolved from the actor's role,
    which is why `Review.stage` is a union of gates and offices (ADR-002
    amendment, point 5). `offices` is the group that may clear a parallel stage
    and is empty for sequential ones.
    """

    kind: StageKind
    records_as: str | None = None
    offices: tuple = ()
    label: str | None = None

    @property
    def is_parallel(self) -> bool:
        return self.kind is StageKind.PARALLEL


@dataclass(frozen=True)
class Edge:
    """
    One legal transition.

    Exactly one of `to` and `resolver` is set. `gate_role` documents which role
    owns the gate; it is descriptive, never enforced here (see the module note
    on authorization). `decision` is what gets written to `Review.status`, which
    is why `DECLINE` and `REJECT` are separate edges rather than one with a flag:
    they are different outcomes and ADR-003's whole contribution rests on the
    difference.
    """

    decision: str
    gate_role: str | None = None
    to: str | None = None
    resolver: str | None = None

    def __post_init__(self):
        if bool(self.to) == bool(self.resolver):
            raise ValueError("an edge needs exactly one of `to` or `resolver`")


# ---------------------------------------------------------------------------
# CIT-U's table. Override per instance via settings.WORKFLOW_TABLE.
# ---------------------------------------------------------------------------

#: Nodes. Every status a review can be *acted on* at appears here; terminal and
#: pre-pipeline statuses (draft, approved, published, declined, rejected,
#: completed, pending_delete) deliberately do not — nothing is reviewed there.
STAGES: dict[str, Stage] = {
    PipelineStatus.ADVISER_REVIEW: Stage(
        kind=StageKind.SEQUENTIAL,
        records_as=ReviewStage.ADVISER,
    ),
    PipelineStatus.RDCO_INTAKE: Stage(
        kind=StageKind.SEQUENTIAL,
        records_as=ReviewStage.RDCO_INTAKE,
    ),
    PipelineStatus.RDCO_REVIEW: Stage(
        kind=StageKind.SEQUENTIAL,
        records_as=ReviewStage.RDCO,
    ),
    # ITSO's stage. KTTO may also act here -- it starts in parallel with ITSO --
    # which is why the group is both, not ITSO alone.
    PipelineStatus.ITSO_REVIEW: Stage(
        kind=StageKind.PARALLEL,
        offices=(Office.ITSO, Office.KTTO),
    ),
    PipelineStatus.PARALLEL_REVIEW: Stage(
        kind=StageKind.PARALLEL,
        offices=(Office.IERC, Office.KTTO),
    ),
}

#: Edges, keyed `(from_status, event)`. See the module docstring on why
#: `actor_role` is a field rather than part of the key.
TRANSITIONS: dict[tuple, Edge] = {
    # --- Proposal: the adviser gate ---
    (PipelineStatus.ADVISER_REVIEW, WorkflowEvent.APPROVE): Edge(
        decision=ReviewDecision.APPROVED,
        gate_role=RoleName.ADVISER,
        # Proposals terminate at `approved` (visible as ongoing research);
        # anything else here publishes. Type-dependent, so a resolver.
        resolver="after_adviser_review",
    ),
    (PipelineStatus.ADVISER_REVIEW, WorkflowEvent.DECLINE): Edge(
        decision=ReviewDecision.DECLINED,
        gate_role=RoleName.ADVISER,
        to=PipelineStatus.DECLINED,
    ),
    (PipelineStatus.ADVISER_REVIEW, WorkflowEvent.REJECT): Edge(
        decision=ReviewDecision.REJECTED,
        gate_role=RoleName.ADVISER,
        to=PipelineStatus.REJECTED,
    ),
    # --- RDCO intake ---
    (PipelineStatus.RDCO_INTAKE, WorkflowEvent.APPROVE): Edge(
        decision=ReviewDecision.APPROVED,
        gate_role=RoleName.RDCO,
        # Which offices were requested decides where this lands (ADR-018).
        resolver="enter_clearance_stage",
    ),
    (PipelineStatus.RDCO_INTAKE, WorkflowEvent.DECLINE): Edge(
        decision=ReviewDecision.DECLINED,
        gate_role=RoleName.RDCO,
        to=PipelineStatus.DECLINED,
    ),
    (PipelineStatus.RDCO_INTAKE, WorkflowEvent.REJECT): Edge(
        decision=ReviewDecision.REJECTED,
        gate_role=RoleName.RDCO,
        to=PipelineStatus.REJECTED,
    ),
    # --- RDCO final review ---
    (PipelineStatus.RDCO_REVIEW, WorkflowEvent.APPROVE): Edge(
        decision=ReviewDecision.APPROVED,
        gate_role=RoleName.RDCO,
        to=PipelineStatus.PUBLISHED,
    ),
    (PipelineStatus.RDCO_REVIEW, WorkflowEvent.DECLINE): Edge(
        decision=ReviewDecision.DECLINED,
        gate_role=RoleName.RDCO,
        to=PipelineStatus.DECLINED,
    ),
    (PipelineStatus.RDCO_REVIEW, WorkflowEvent.REJECT): Edge(
        decision=ReviewDecision.REJECTED,
        gate_role=RoleName.RDCO,
        to=PipelineStatus.REJECTED,
    ),
    # --- Clearance stages. The acting office comes from the actor's role, so
    # --- there is one edge per stage, not one per office.
    (PipelineStatus.ITSO_REVIEW, WorkflowEvent.APPROVE): Edge(
        decision=ReviewDecision.APPROVED,
        resolver="after_clearance",
    ),
    (PipelineStatus.ITSO_REVIEW, WorkflowEvent.DECLINE): Edge(
        decision=ReviewDecision.DECLINED,
        to=PipelineStatus.DECLINED,
    ),
    (PipelineStatus.ITSO_REVIEW, WorkflowEvent.REJECT): Edge(
        decision=ReviewDecision.REJECTED,
        to=PipelineStatus.REJECTED,
    ),
    (PipelineStatus.PARALLEL_REVIEW, WorkflowEvent.APPROVE): Edge(
        decision=ReviewDecision.APPROVED,
        resolver="after_clearance",
    ),
    (PipelineStatus.PARALLEL_REVIEW, WorkflowEvent.DECLINE): Edge(
        decision=ReviewDecision.DECLINED,
        to=PipelineStatus.DECLINED,
    ),
    (PipelineStatus.PARALLEL_REVIEW, WorkflowEvent.REJECT): Edge(
        decision=ReviewDecision.REJECTED,
        to=PipelineStatus.REJECTED,
    ),
    # --- Resubmission out of `declined`. Where it lands depends on whether the
    # --- decline came from a clearance office or a sequential gate -- which is
    # --- ADR-003's contribution, and is now a table lookup.
    (PipelineStatus.DECLINED, WorkflowEvent.RESUBMIT): Edge(
        decision=ReviewDecision.APPROVED,  # unused: resubmission writes no Review
        resolver="after_resubmission",
    ),

    # --- Stage 2: the record-owned edges -----------------------------------
    # These were seven hand-written assignments in records/views.py and
    # records/services.py. None of them writes a Review, so `decision` is unused
    # on every edge below -- it stays on the dataclass because the review edges
    # above need it.

    # Submission out of draft. Type-differentiated, so a resolver: a Proposal
    # enters adviser_review and everything else rdco_intake.
    (PipelineStatus.DRAFT, WorkflowEvent.SUBMIT): Edge(
        decision=ReviewDecision.APPROVED,
        resolver="first_status",
    ),
    # RDCO marks an approved Proposal finished. Only Proposals reach `approved`
    # -- approve_record sends every other type to `published` -- so keying on
    # the status is sufficient; the view keeps an explicit record-type check as
    # a defensive precondition rather than as routing.
    (PipelineStatus.APPROVED, WorkflowEvent.MARK_COMPLETE): Edge(
        decision=ReviewDecision.APPROVED,
        gate_role=RoleName.RDCO,
        to=PipelineStatus.COMPLETED,
    ),
    # Restoring a record whose delete request was declined. The destination is
    # the status it held before, which lives on the DeleteRequest row, so the
    # caller supplies it.
    (PipelineStatus.PENDING_DELETE, WorkflowEvent.RESTORE): Edge(
        decision=ReviewDecision.APPROVED,
        gate_role=RoleName.RDCO,
        resolver="restore_previous",
    ),
}

# Deleting a publicly visible record raises a delete request for review rather
# than removing it; anything not yet public is soft-deleted outright. Generated
# rather than typed out so the two sets cannot drift from
# PUBLICLY_VISIBLE_STATUSES, which is what `perform_destroy` branches on.
for _status in PUBLICLY_VISIBLE_STATUSES:
    TRANSITIONS[(_status, WorkflowEvent.REQUEST_DELETE)] = Edge(
        decision=ReviewDecision.APPROVED,
        to=PipelineStatus.PENDING_DELETE,
    )

# Soft delete is legal from **every** status, deliberately. Before IR-136 it was
# an unguarded assignment reachable from two places -- `perform_destroy` for a
# not-yet-public record, and delete-request *approve*, where the record is
# already at `pending_delete`. Declaring a partial edge set here would turn a
# silent success into an InvalidPipelineTransition, which stage 2 must not do:
# this stage makes the edges visible, it does not tighten them. Whether every
# one of these should stay permitted is a separate, deliberate decision.
for _status in PipelineStatus.values:
    TRANSITIONS[(_status, WorkflowEvent.SOFT_DELETE)] = Edge(
        decision=ReviewDecision.APPROVED,
        to=PipelineStatus.PENDING_DELETE,
    )

del _status


# ---------------------------------------------------------------------------
# Creation. Not edges: a record being created has no status to come *from*.
# ---------------------------------------------------------------------------

#: What a newly created record starts as.
INITIAL_STATUS = PipelineStatus.DRAFT

#: Where the legacy Excel importer places records -- **straight to published,
#: bypassing the review pipeline entirely**. ADR-002 calls this "the Excel
#: bypass" and asks that it become "a declared, auditable edge"; naming it here
#: is that declaration. It is recorded, not endorsed: whether the bypass stays
#: permitted is a decision for a person, and stage 2 deliberately preserves
#: today's behaviour rather than quietly removing it inside a refactor.
LEGACY_IMPORT_STATUS = PipelineStatus.PUBLISHED


def load_table() -> tuple[dict, dict]:
    """
    The active `(STAGES, TRANSITIONS)` for this instance.

    `settings.WORKFLOW_TABLE` may supply either key to override CIT-U's default.
    This is the ADR-005 seam: a second institution changes configuration in its
    own deployment rather than forking application code. Absent the setting —
    the normal case — the defaults above are used unchanged.
    """
    override = getattr(settings, "WORKFLOW_TABLE", None) or {}
    return (
        override.get("STAGES", STAGES),
        override.get("TRANSITIONS", TRANSITIONS),
    )


def stage_for(status: str) -> Stage | None:
    """The `Stage` a status names, or None when nothing is reviewed there."""
    stages, _ = load_table()
    return stages.get(status)


def is_clearance_stage(status: str) -> bool:
    """True when `status` is a parallel clearance stage."""
    stage = stage_for(status)
    return bool(stage and stage.is_parallel)


def clearance_offices() -> frozenset:
    """
    Every office that owns a parallel gate anywhere in the table.

    Replaces `resubmit_record`'s `CLEARANCE_OFFICES` literal and
    `clearance_state.CLEARANCE_OFFICES`. Derived from `STAGES` so a table that
    adds an office to a group does not leave a set literal behind to drift.
    """
    stages, _ = load_table()
    return frozenset(
        office for stage in stages.values() for office in stage.offices
    )


def review_stage_for(status: str, office: str | None = None) -> str | None:
    """
    What `Review.stage` should hold for a review landing at `status`.

    The union, resolved: a sequential gate declares its value in `STAGES`, while
    a parallel stage takes the **acting office**, which the caller supplies
    because only it knows who acted. ADR-002 amendment, point 5.
    """
    stage = stage_for(status)
    if stage is None:
        return None
    return office if stage.is_parallel else stage.records_as


# ---------------------------------------------------------------------------
# Resolvers -- the closed set of dynamic destinations
# ---------------------------------------------------------------------------

def _resolve_after_adviser_review(record, **_) -> str:
    """Proposals stop at `approved` and stay visible as ongoing; others publish."""
    type_name = record.record_type.name if record.record_type else ""
    return (
        PipelineStatus.APPROVED
        if type_name == RecordTypeName.PROPOSAL
        else PipelineStatus.PUBLISHED
    )


def _resolve_enter_clearance_stage(record, **_) -> str:
    """
    Create the requested offices' clearance rows and say where the record lands.

    ADR-018: the office set is data on the record, not a function of its type.
    `requested_itso` takes effect for Project only — Thesis/Research has no ITSO
    stage at all. A record requesting nothing goes straight to `rdco_review`,
    because a clearance stage with no office attached would auto-clear, which is
    worse than skipping it.
    """
    from apps.reviews.models import RecordClearance

    type_name = record.record_type.name if record.record_type else ""
    offices: list = []
    if type_name == RecordTypeName.PROJECT and record.requested_itso:
        offices.append(Office.ITSO)
    if record.requested_ierc:
        offices.append(Office.IERC)
    if record.requested_ktto:
        offices.append(Office.KTTO)

    for office in offices:
        RecordClearance.objects.get_or_create(record=record, office=office)

    if Office.ITSO in offices:
        return PipelineStatus.ITSO_REVIEW
    if offices:
        return PipelineStatus.PARALLEL_REVIEW
    return PipelineStatus.RDCO_REVIEW


def _resolve_after_clearance(record, office=None, **_) -> str:
    """
    Where the record goes once this office has cleared.

    ITSO clearing is the one sequenced step: IERC's row is created here, and
    only if it was actually requested (ADR-018) — unconditionally creating it
    would force an ethics review nobody asked for. KTTO may already have
    cleared, be pending, or never have been requested, which is exactly what
    "are all clearances done" reflects.
    """
    from apps.reviews.models import RecordClearance

    if office == Office.ITSO and record.pipeline_status == PipelineStatus.ITSO_REVIEW:
        if record.requested_ierc:
            RecordClearance.objects.get_or_create(record=record, office=Office.IERC)
        if _all_clearances_done(record):
            return PipelineStatus.RDCO_REVIEW
        return PipelineStatus.PARALLEL_REVIEW

    if _all_clearances_done(record):
        return PipelineStatus.RDCO_REVIEW
    return record.pipeline_status  # still waiting on a peer office


def _resolve_after_resubmission(record, declining_stage=None, **_) -> str:
    """
    **ADR-003's contribution, as a table lookup rather than a set literal.**

    A decline from a clearance office resets only that office and routes back to
    the stage it reviews at, preserving every peer's completed work. A decline
    from a sequential gate is a full restart: all clearances are dropped and the
    record re-enters its route from the top.

    `declining_stage` is a `Review.stage`, which is a union — the membership test
    against `clearance_offices()` is what decides which of the two this is, and
    that set now comes from `STAGES` rather than a literal.
    """
    from apps.reviews.models import RecordClearance

    if declining_stage and declining_stage in clearance_offices():
        office = declining_stage
        RecordClearance.objects.filter(record=record, office=office).update(
            status=ClearanceStatus.PENDING, reviewed_by=None, comment=""
        )
        return _stage_reviewed_by(record, office)

    RecordClearance.objects.filter(record=record).delete()
    return first_status_for(record)


def _stage_reviewed_by(record, office: str) -> str:
    """
    The clearance stage this office reviews at, for this record.

    KTTO is the awkward one: it acts at both `itso_review` and `parallel_review`,
    so which stage to route back to depends on whether ITSO is still pending.
    Derived from the table rather than hardcoded, so an added office lands
    correctly without another branch here.
    """
    from apps.reviews.models import RecordClearance

    stages, _ = load_table()
    candidates = [
        status
        for status, stage in stages.items()
        if stage.is_parallel and office in stage.offices
    ]
    if not candidates:
        return first_status_for(record)
    if len(candidates) == 1:
        return candidates[0]

    # Acts at more than one stage. Route to the earliest whose *other* offices
    # still have work outstanding -- for KTTO that is itso_review while ITSO is
    # pending, and parallel_review once it is not.
    for status in (PipelineStatus.ITSO_REVIEW, PipelineStatus.PARALLEL_REVIEW):
        if status not in candidates:
            continue
        peers = [o for o in stages[status].offices if o != office]
        if RecordClearance.objects.filter(
            record=record, office__in=peers, status=ClearanceStatus.PENDING
        ).exists():
            return status
    return candidates[-1]


def _resolve_first_status(record, **_) -> str:
    """Submission out of draft — the same type-differentiated entry the pipeline uses."""
    return first_status_for(record)


def _resolve_restore_previous(record, restore_to=None, **_) -> str:
    """
    Where a record goes when its delete request is declined.

    `restore_to` is the `DeleteRequest.previous_pipeline_status` the caller
    holds. The fallback reproduces today's behaviour exactly: an older row may
    predate that column being populated, and those records fall back to
    `approved` for a Proposal and `published` for anything else.
    """
    if restore_to:
        return restore_to
    type_name = record.record_type.name if record.record_type else ""
    return (
        PipelineStatus.APPROVED
        if type_name == RecordTypeName.PROPOSAL
        else PipelineStatus.PUBLISHED
    )


_RESOLVERS = {
    "after_adviser_review": _resolve_after_adviser_review,
    "enter_clearance_stage": _resolve_enter_clearance_stage,
    "after_clearance": _resolve_after_clearance,
    "after_resubmission": _resolve_after_resubmission,
    "first_status": _resolve_first_status,
    "restore_previous": _resolve_restore_previous,
}


# ---------------------------------------------------------------------------
# Helpers the table and its callers share
# ---------------------------------------------------------------------------

def _all_clearances_done(record) -> bool:
    from apps.reviews.models import RecordClearance

    return not RecordClearance.objects.filter(
        record=record, status=ClearanceStatus.PENDING
    ).exists()


def first_status_for(record) -> str:
    """The status a record enters when submitted or restarted."""
    type_name = record.record_type.name if record.record_type else ""
    return (
        PipelineStatus.ADVISER_REVIEW
        if type_name == RecordTypeName.PROPOSAL
        else PipelineStatus.RDCO_INTAKE
    )


def edge_for(status: str, event: WorkflowEvent) -> Edge | None:
    """The declared edge, or None when the transition is not legal."""
    _, transitions = load_table()
    return transitions.get((status, event))


# ---------------------------------------------------------------------------
# The single entry point
# ---------------------------------------------------------------------------

@transaction.atomic
def apply(
    record,
    event: WorkflowEvent,
    actor=None,
    *,
    office=None,
    declining_stage=None,
    restore_to=None,
) -> str:
    """
    Resolve and persist the record's next `pipeline_status`. Returns it.

    **Atomic from the first commit** (ADR-002's Decision, and its Security
    Impact: this closes the partial-application defect where a record could
    advance having been cleared by one office instead of two). The clearance
    rows a resolver writes and the status change land together or not at all.

    Raises `InvalidPipelineTransition` when the table declares no such edge.
    That is a **legality** verdict, not an authorization one — callers check who
    may act *before* calling this. See the module docstring.

    Deliberately does not create the `Review` row, send notifications, or touch
    IR-139's resubmission counters. Those are orchestration and stay in
    `reviews.services`, which is also what honours IR-136's "do not rebuild the
    eleven transitions" instruction.
    """
    edge = edge_for(record.pipeline_status, event)
    if edge is None:
        raise InvalidPipelineTransition(
            f"'{event.value}' is not a legal transition from "
            f"'{record.pipeline_status}'."
        )

    if edge.to is not None:
        destination = edge.to
    else:
        resolver = _RESOLVERS.get(edge.resolver)
        if resolver is None:
            raise InvalidPipelineTransition(
                f"the table names resolver '{edge.resolver}', which does not exist"
            )
        destination = resolver(
            record,
            office=office,
            declining_stage=declining_stage,
            restore_to=restore_to,
            actor=actor,
        )

    if destination != record.pipeline_status:
        record.pipeline_status = destination
        record.save(update_fields=["pipeline_status", "updated_at"])
    return destination
