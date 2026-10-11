"""
The record-level workflow edges, and the resubmission policy (IR-136, ADR-002).

**What is left after IR-274.** This module once held the fixed review pipeline:
a `STAGES` node registry, ~30 review edges and the resolvers that routed a
record from intake through the clearance stages to RDCO. ADR-032 retired that
pipeline. Review is now assignments, seats and Decisions (`apps.reviews`), and
a record in review is stored as `in_review` whoever holds it. IR-260 cut every
record over and IR-274 deleted the table.

What remains is what never depended on who reviews:

- the **record-owned edges** -- requesting deletion of accepted work, soft
  deletion and restoring a record whose delete request was declined -- with
  `apply()`, their one entry point;
- **`ResubmissionPolicy`**, ADR-004's experimental control, which
  `reviews.new_version` reads to choose between the clearance-aware and
  restart-all arms;
- **`clearance_reset_fields()`**, what resetting a clearance means, written
  once so the two arms cannot drift;
- **who decides** each record type, which the tracker reads.

**What this module does NOT do: authorize.** It answers "is this transition
legal, and where does it lead". Whether *this* user may act on *this* record is
the permission layer's question (ADR-009, IR-165).

**Per-instance configuration.** `TRANSITIONS` below is CIT-U's default.
`settings.WORKFLOW_TABLE` may override it, and carries `RESUBMISSION_POLICY` as
its own key. That is ADR-005's "configuration within the instance": a second
deployment changes configuration rather than forking code. See `load_table()`.
"""

from dataclasses import dataclass
from enum import Enum

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.enums import (
    DELETE_REVIEW_STATUSES,
    ClearanceStatus,
    Party,
    PipelineStatus,
    RecordTypeName,
    RoleName,
)
from core.exceptions import InvalidPipelineTransition


class WorkflowEvent(str, Enum):
    """What a caller asks of a record's status. Views name these, never status strings."""

    REQUEST_DELETE = "request_delete"
    SOFT_DELETE = "soft_delete"
    RESTORE = "restore"


class ResubmissionPolicy(str, Enum):
    """
    What a new version does to clearances already granted (IR-137, ADR-004).

    Here rather than in `core.enums`: it is configuration of the instance,
    never a value written to a column.

    `CLEARANCE_AWARE` is ADR-003's contribution and production's default.
    `RESTART_ALL` is the *comparison arm*, and it exists because counting
    preserved clearances cannot produce a negative result -- given which office
    asked for changes, the count is deterministically computable, so the claim
    is only testable against IRIS running the other policy. ADR-004's
    operational rule is hard: the comparison runs on a dedicated evaluation
    instance, never on a customer's production one.
    """

    CLEARANCE_AWARE = "clearance_aware"
    RESTART_ALL = "restart_all"

    @classmethod
    def coerce(cls, value) -> "ResubmissionPolicy":
        """
        One policy from configuration, or a refusal naming what was allowed.

        **Case-insensitive on purpose.** ADR-004 and IR-137 both write the
        values in upper case (`RESTART_ALL`), so the single most likely thing
        an operator types is the spec's own spelling. Rejecting it would fail
        the person who read the documentation correctly.

        Everything else raises. The alternative -- treating an unrecognised
        value as the default -- would run the evaluation instance on the
        production arm and report nothing, which is the one failure this
        setting cannot be allowed to have.
        """
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            raise ValueError(
                f"RESUBMISSION_POLICY={value!r} is not a resubmission policy. "
                f"Use one of: {', '.join(p.value for p in cls)}."
            ) from None


@dataclass(frozen=True)
class Edge:
    """
    One legal transition. Exactly one of `to` and `resolver` is set.

    `gate_role` documents which role owns the edge; it is descriptive, never
    enforced here (see the module note on authorization).
    """

    gate_role: str | None = None
    to: str | None = None
    resolver: str | None = None

    def __post_init__(self):
        if bool(self.to) == bool(self.resolver):
            raise ValueError("an edge needs exactly one of `to` or `resolver`")


# ---------------------------------------------------------------------------
# CIT-U's table. Override per instance via settings.WORKFLOW_TABLE.
# ---------------------------------------------------------------------------

#: Edges, keyed `(from_status, event)`.
TRANSITIONS: dict[tuple, Edge] = {
    # Restoring a record whose delete request was declined. The destination is
    # the status it held before, which lives on the DeleteRequest row, so the
    # caller supplies it.
    (PipelineStatus.PENDING_DELETE, WorkflowEvent.RESTORE): Edge(
        gate_role=RoleName.RDCO,
        resolver="restore_previous",
    ),
}

# Deleting accepted work raises a delete request for review rather than removing
# it; anything not yet accepted is soft-deleted outright. Generated rather than
# typed out so the two sets cannot drift from DELETE_REVIEW_STATUSES, which is
# what `perform_destroy` branches on.
for _status in DELETE_REVIEW_STATUSES:
    TRANSITIONS[(_status, WorkflowEvent.REQUEST_DELETE)] = Edge(to=PipelineStatus.PENDING_DELETE)

# Soft delete is legal from **every** status, deliberately: it is reachable from
# `perform_destroy` for a record not yet accepted, and from delete-request
# *approve*, where the record is already at `pending_delete`. Whether every one
# of these should stay permitted is a separate, deliberate decision.
for _status in PipelineStatus.values:
    TRANSITIONS[(_status, WorkflowEvent.SOFT_DELETE)] = Edge(to=PipelineStatus.PENDING_DELETE)

del _status


# ---------------------------------------------------------------------------
# Creation. Not edges: a record being created has no status to come *from*.
# ---------------------------------------------------------------------------

#: What a newly created record starts as.
INITIAL_STATUS = PipelineStatus.DRAFT

#: Where the legacy Excel importer places records -- **straight to published,
#: bypassing review entirely**. ADR-002 calls this "the Excel bypass" and asks
#: that it become "a declared, auditable edge"; naming it here is that
#: declaration. It is recorded, not endorsed.
LEGACY_IMPORT_STATUS = PipelineStatus.PUBLISHED


def load_table() -> dict:
    """
    The active `TRANSITIONS` for this instance.

    `settings.WORKFLOW_TABLE["TRANSITIONS"]` overrides CIT-U's default. This is
    the ADR-005 seam: a second institution changes configuration in its own
    deployment rather than forking application code.
    """
    override = getattr(settings, "WORKFLOW_TABLE", None) or {}
    return override.get("TRANSITIONS", TRANSITIONS)


def resubmission_policy() -> ResubmissionPolicy:
    """
    The active resubmission policy -- `WORKFLOW_TABLE`'s own key (ADR-004).

    **An unrecognised value raises rather than falling back**, and
    `RecordsConfig.ready()` calls this at startup so it raises *there* -- before
    a participant is mid-session -- rather than on the first new version. A
    silent default would run the evaluation instance on the production arm,
    and nothing in its output would say so.
    """
    override = getattr(settings, "WORKFLOW_TABLE", None) or {}
    return ResubmissionPolicy.coerce(
        override.get("RESUBMISSION_POLICY", ResubmissionPolicy.CLEARANCE_AWARE)
    )


def clearance_reset_fields() -> dict:
    """
    What resetting a clearance means, written once.

    Both resubmission arms apply exactly this, differing only in which rows they
    apply it to. That is not tidiness: "the two arms differ in nothing but the
    policy" is IR-137's acceptance criterion, and two copies of these fields is
    precisely how one arm quietly acquires a different one.

    **`updated_at` is set by hand because `.update()` bypasses `auto_now`.**
    Without it a reset row keeps the timestamp of the moment it *cleared*, and
    `clearance_state.clearance_payload` publishes that as the office's decision
    time.

    A function, not a module constant: `timezone.now()` in a constant would be
    evaluated once at import.
    """
    return {
        "status": ClearanceStatus.PENDING,
        "reviewed_by": None,
        "comment": "",
        "updated_at": timezone.now(),
    }


# ---------------------------------------------------------------------------
# Who decides (ADR-032 §2-§3)
# ---------------------------------------------------------------------------

#: The parties with decision authority over a record of each type. The tracker
#: reads them to tell *final review* from *in review*. A type not listed takes
#: the Thesis/Research row. Every type *enters* at its Adviser (ADR-032 §1).
DECIDING_PARTIES = {RecordTypeName.PROPOSAL: frozenset({Party.ADVISER, Party.RDCO})}
DEFAULT_DECIDING_PARTIES = frozenset({Party.RDCO})


def type_name_of(record) -> str:
    return record.record_type.name if record.record_type else ""


def deciding_parties_for(record) -> frozenset:
    """The parties with decision authority over a record of this type."""
    return DECIDING_PARTIES.get(type_name_of(record), DEFAULT_DECIDING_PARTIES)


# ---------------------------------------------------------------------------
# Resolvers -- the closed set of dynamic destinations
# ---------------------------------------------------------------------------

def _resolve_restore_previous(record, restore_to=None, **_) -> str:
    """
    Where a record goes when its delete request is declined.

    `restore_to` is the `DeleteRequest.previous_pipeline_status` the caller
    holds. The fallback serves an older row that predates that column being
    populated: `approved` for a Proposal, `published` for anything else.
    """
    if restore_to:
        return restore_to
    return (
        PipelineStatus.APPROVED
        if type_name_of(record) == RecordTypeName.PROPOSAL
        else PipelineStatus.PUBLISHED
    )


_RESOLVERS = {
    "restore_previous": _resolve_restore_previous,
}


def edge_for(status: str, event: WorkflowEvent) -> Edge | None:
    """The declared edge, or None when the transition is not legal."""
    return load_table().get((status, event))


def require_edge(record, event: WorkflowEvent) -> Edge:
    """The declared edge from the record's current status, or a refusal."""
    edge = edge_for(record.pipeline_status, event)
    if edge is None:
        raise InvalidPipelineTransition(
            f"'{event.value}' is not a legal transition from "
            f"'{record.pipeline_status}'."
        )
    return edge


# ---------------------------------------------------------------------------
# The single entry point
# ---------------------------------------------------------------------------

@transaction.atomic
def apply(record, event: WorkflowEvent, actor=None, *, restore_to=None) -> str:
    """
    Resolve and persist the record's next `pipeline_status`. Returns it.

    **A soft delete also ends the record's review**: every active assignment,
    its open seats and every open revision request are withdrawn in the same
    transaction (`reviews.withdrawal`). Nobody finished, so nothing is closed
    as *completed*. The legacy `shadow.sync()` did this as a side effect of
    reconciling from the old stage; IR-274 states it as its own rule.

    Raises `InvalidPipelineTransition` when the table declares no such edge.
    That is a **legality** verdict, not an authorization one -- callers check
    who may act *before* calling this.
    """
    edge = require_edge(record, event)

    if edge.to is not None:
        destination = edge.to
    else:
        resolver = _RESOLVERS.get(edge.resolver)
        if resolver is None:
            raise InvalidPipelineTransition(
                f"the table names resolver '{edge.resolver}', which does not exist"
            )
        destination = resolver(record, restore_to=restore_to, actor=actor)

    if destination != record.pipeline_status:
        record.pipeline_status = destination
        record.save(update_fields=["pipeline_status", "updated_at"])

    if event is WorkflowEvent.SOFT_DELETE:
        from apps.reviews.withdrawal import withdraw_review

        withdraw_review(record, actor)
    return destination
