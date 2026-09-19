"""
Shadow writes of the reviewer-directed routing tables (IR-257, ADR-021 §8).

IR-256 added `RecordAssignment`, `RoutingEvent` and `ResubmissionRequest` beside
the pipeline. This module keeps them accurate while the pipeline stays
authoritative: `lifecycle.apply()` calls `sync()` after every transition, inside
its own transaction, so the shadow rows and the status move land together or
not at all. **Nothing reads these rows yet.** IR-258 reads them for the tracker,
and IR-260 makes them authoritative and deletes this module's reason to exist.

**Reconciled from state, not replayed from events.** After a transition,
`active_parties_for()` reads the §6 mapping of
`docs/workflow_routing_architecture.md` off the record's status and clearances,
and `sync()` closes and opens assignments until the rows match it. Replaying
each edge instead would make the shadow correct only for records that took
every step through this code, and a record parked at a stage (the legacy
importer, a test fixture, anything written before IR-257) would then carry
wrong rows forever. Reconciling makes every transition self-correcting, and
makes §6 the one statement of who holds what.

**Three rules from IR-256 hold here.** No workflow action deletes a row: closing
an assignment or resolving a request changes its `state`. No outcome is stored
on an assignment: the outcome is the `Review`. No column stores
`workflow_state`.
"""

import uuid

from django.utils import timezone

from core.enums import (
    AssignmentState,
    ClearanceStatus,
    Party,
    PipelineStatus,
    ResubmissionRequestState,
    ReviewDecision,
    ReviewStage,
)

from .models import (
    RecordAssignment,
    RecordClearance,
    ResubmissionRequest,
    Review,
    RoutingEvent,
)


def party_for_stage(stage):
    """
    The party a `Review.stage` names, or None.

    `Party` is `ReviewStage`, so this is the identity except for the one value
    IR-260 renames: `rdco_intake` is a stored stage, and `intake` is the party
    it names (§6's preamble). Nothing new is ever assigned to `rdco_intake`.
    """
    if not stage:
        return None
    if stage == ReviewStage.RDCO_INTAKE:
        return Party.INTAKE
    return Party(stage)


def declining_party(record):
    """The party of the record's last decline, which is who asked for changes."""
    stage = (
        Review.objects.filter(record=record, status=ReviewDecision.DECLINED)
        .order_by("-created_at", "-pk")
        .values_list("stage", flat=True)
        .first()
    )
    return party_for_stage(stage)


def _pending_offices(record) -> set:
    return set(
        RecordClearance.objects.filter(record=record, status=ClearanceStatus.PENDING)
        .values_list("office", flat=True)
    )


def active_parties_for(record) -> set:
    """
    Who holds the record now: §6's "Active assignments" column.

    A clearance stage is held by every office still pending, so IERC is not
    active at `itso_review` until ITSO clears and its row exists. A declined
    record is still held by the party that asked for changes, and by any office
    whose clearance is still pending: they have not finished either.
    """
    status = record.pipeline_status
    if status == PipelineStatus.ADVISER_REVIEW:
        return {Party.ADVISER}
    if status == PipelineStatus.RDCO_INTAKE:
        return {Party.INTAKE}
    if status in (PipelineStatus.ITSO_REVIEW, PipelineStatus.PARALLEL_REVIEW):
        return _pending_offices(record)
    if status == PipelineStatus.RDCO_REVIEW:
        return {Party.RDCO}
    if status == PipelineStatus.DECLINED:
        requester = declining_party(record)
        return ({requester} if requester else set()) | _pending_offices(record)
    # draft, and every status the pipeline has finished with.
    return set()


def sync(record, event, actor, *, acting_party=None, review=None):
    """
    Bring the shadow rows in line with the transition that just happened.

    `acting_party` is the party a reviewer acted as, or None when the submitter
    or the system moved the record. `review` is the `Review` that transition
    wrote, when it wrote one.

    Called by `lifecycle.apply()` inside its transaction and after the status
    is saved, so everything read here is the record's new state.
    """
    # Imported here: `lifecycle` imports this module inside `apply()`, and this
    # module needs the event names, not the table.
    from apps.records.lifecycle import WorkflowEvent

    now = timezone.now()
    # Plain strings throughout: stored `party` values come back as `str`, and
    # set arithmetic between those and enum members should not depend on how
    # the enum hashes.
    expected = {str(party) for party in active_parties_for(record)}
    acting_party = str(acting_party) if acting_party else None
    held = {
        a.party: a
        for a in RecordAssignment.objects.select_for_update().filter(
            record=record, state=AssignmentState.ACTIVE
        )
    }

    # A deletion ends every turn unfinished. Anything else that closes an
    # assignment does so because the party's work there is done -- including
    # a restart after a sequential decline, where the party that asked for
    # changes has had its answer.
    closing_state = (
        AssignmentState.WITHDRAWN
        if event is WorkflowEvent.SOFT_DELETE
        else AssignmentState.COMPLETED
    )
    closed = {}
    for party in sorted(held.keys() - expected):
        assignment = held.pop(party)
        assignment.state = closing_state
        assignment.closed_by = actor
        assignment.closed_at = now
        assignment.save(update_fields=["state", "closed_by", "closed_at"])
        closed[party] = assignment

    opened = {}
    for party in sorted(expected - held.keys()):
        opened[party] = RecordAssignment.objects.create(
            record=record,
            party=party,
            # Null when submission or the system opened it (the model's rule).
            opened_by=actor if acting_party else None,
            opened_at=now,
        )
    held.update(opened)

    if event is WorkflowEvent.DECLINE and review is None:
        review = (
            Review.objects.filter(record=record, status=ReviewDecision.DECLINED)
            .order_by("-created_at", "-pk")
            .first()
        )

    if review is not None and acting_party:
        assignment = held.get(acting_party) or closed.get(acting_party)
        if assignment is not None:
            review.assignment = assignment
            review.save(update_fields=["assignment"])

    if event is WorkflowEvent.DECLINE and review is not None:
        ResubmissionRequest.objects.create(
            record=record,
            party=acting_party or party_for_stage(review.stage),
            assignment=held.get(acting_party),
            review=review,
            requested_by=actor,
            reason=review.comment,
            created_at=now,
        )
    elif event in (WorkflowEvent.RESUBMIT, WorkflowEvent.SOFT_DELETE):
        ResubmissionRequest.objects.filter(
            record=record, state=ResubmissionRequestState.OPEN
        ).update(
            state=(
                ResubmissionRequestState.RESUBMITTED
                if event is WorkflowEvent.RESUBMIT
                else ResubmissionRequestState.WITHDRAWN
            ),
            resolved_by=actor,
            resolved_at=now,
        )

    # Routing is recorded where it actually happened: a reviewer's decision
    # sent the record on, or the submitter sent it in. One call to several
    # parties is one decision, so the events share a group.
    targets = [party for party in opened if party != acting_party]
    submitted = event in (WorkflowEvent.SUBMIT, WorkflowEvent.RESUBMIT)
    if targets and (acting_party or submitted):
        group_id = uuid.uuid4()
        RoutingEvent.objects.bulk_create([
            RoutingEvent(
                record=record,
                actor=actor,
                from_party=acting_party,
                to_party=party,
                group_id=group_id,
                created_at=now,
            )
            for party in targets
        ])
