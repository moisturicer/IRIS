"""
Workflow audit events (IR-144, ADR-011).

The evaluation's turnaround and preserved-clearance metrics are computed from
these rows alone, and an event missed during the pilot cannot be
reconstructed. So:

- **One type per act.** Each act writes its own event type, and the functions
  here fix their metadata keys (`seat_moved` serves the six seat moves, which
  share theirs; `resubmitted` also writes the `CLEARANCE_PRESERVED` rows that
  belong to its act). `docs/evaluation/AUDIT_EXPORT.md` documents the same keys;
  change one and change the other.
- **Called from the workflow services, inside their transaction**, after the
  per-record lock. A refused or rolled-back act therefore leaves no event.
- **Never breaks the act.** `create_audit_event` isolates every insert in a
  savepoint and logs a failure instead of raising.
- **No review prose.** Decision and finding comments are never copied
  (IR-479). The only free text is what the event needs to mean anything: a
  revision request's `reason`, a document request's `message`, and a rejected
  document's `reason`.
- **Kept apart (ADR-022).** A document request writes only `DOCUMENT_REQUEST*`
  events and a revision only revision events, so "you forgot a form" stays
  distinguishable from "revise the work".

Every id in metadata is a primary key, every party a `core.enums.Party` value,
so the rows join back to the workflow tables when a question needs more.
"""

from __future__ import annotations

from core.enums import AssignmentState

from .models import AuditEvent
from .services import create_audit_event


def _version(record) -> int | None:
    """The number of `record`'s latest version, the one an act was taken on."""
    from apps.records.versions import latest_version

    version = latest_version(record)
    return version.number if version else None


def _write(event_type, actor, record, **metadata):
    create_audit_event(event_type, actor, record=record, metadata=metadata)


# --- entering review and moving between parties ------------------------------

def submitted(record, actor, *, to_party) -> None:
    """The record entered review at its Adviser. Starts `to_party`'s clock."""
    _write(AuditEvent.SUBMITTED, actor, record, to_party=str(to_party), version=_version(record))


def routed(record, actor, *, from_party, to_party, opened, group, nominee=None, hand_back=False):
    """
    One routing movement, one row per target. `opened` is true when the target
    got a new assignment -- the start of its clock -- and false when the
    target already held the record and only a nominee was seated. The
    hand-back to RDCO is a movement nobody made: no actor, `hand_back` true.
    """
    _write(
        AuditEvent.ROUTED, actor, record,
        from_party=str(from_party) if from_party else None,
        to_party=str(to_party),
        opened=bool(opened),
        nominee=getattr(nominee, "pk", None),
        group=str(group),
        hand_back=bool(hand_back),
    )


#: How an assignment closed. `completed`: its party finished (the completion
#: rule, or the decider's own turn). `closed_by_decision`: a Decision ended
#: someone else's turn. `withdrawn`: the owner withdrew the record.
COMPLETED = str(AssignmentState.COMPLETED.value)
CLOSED_BY_DECISION = "closed_by_decision"
WITHDRAWN = str(AssignmentState.WITHDRAWN.value)


def assignment_closed(assignment, actor, *, how, decision=None, withdrawn_seats=()):
    """A party's assignment closed. Stops that party's clock."""
    _write(
        AuditEvent.ASSIGNMENT_CLOSED, actor, assignment.record,
        party=str(assignment.party),
        assignment=assignment.pk,
        how=how,
        decision=getattr(decision, "pk", None),
        withdrawn_seats=sorted(withdrawn_seats),
    )


def assignment_extended(extension):
    """ADR-043 history is mandatory: failure rolls back the date movement."""
    assignment = extension.assignment
    return AuditEvent.objects.create(
        event_type=AuditEvent.ASSIGNMENT_EXTENDED, user=extension.actor,
        record_id=assignment.record_id,
        metadata={"assignment": assignment.pk, "party": assignment.party,
                  "extension": extension.pk,
                  "previous_due_at": extension.previous_due_at.isoformat(),
                  "due_at": extension.due_at.isoformat(),
                  "reason": extension.reason, "system": extension.system},
    )


# --- verdicts and decisions ------------------------------------------------------

def decision_recorded(record, actor, *, party, outcome, final, review):
    """
    A reviewer's verdict: an office's `cleared` or `finding`, the Adviser's
    `accepted_and_routed`, or a final outcome (`accept`, `publish`,
    `keep_unlisted`, `reject`, with `final` true). Outcome only, never the
    comment.
    """
    _write(
        AuditEvent.DECISION_RECORDED, actor, record,
        party=str(party), outcome=outcome, final=bool(final),
        review=review.pk, version=_version(record),
    )


def published(record, actor, *, party):
    """The decision made the record publicly visible. Beside its `DECISION_RECORDED`."""
    _write(AuditEvent.PUBLISHED, actor, record, party=str(party), version=_version(record))


# --- revisions ---------------------------------------------------------------------

def resubmission_requested(request, actor):
    """A party asked the owners to revise the work."""
    _write(
        AuditEvent.RESUBMISSION_REQUESTED, actor, request.record,
        party=str(request.party), request=request.pk, reason=request.reason,
        version=_version(request.record),
    )


#: Who closed a request without it being answered.
BY_REQUESTING_PARTY = "requesting_party"
BY_DECISION = "decision"
BY_RECORD_WITHDRAWN = "record_withdrawn"


def revision_request_withdrawn(request, actor, *, closed_by=BY_REQUESTING_PARTY):
    _write(
        AuditEvent.REVISION_REQUEST_WITHDRAWN, actor, request.record,
        party=str(request.party), request=request.pk, closed_by=closed_by,
    )


def resubmitted(record, actor, *, version, policy, requests, rereview_parties,
                reset_parties, preserved_parties):
    """
    The owner submitted a new version answering every open revision request,
    then one `CLEARANCE_PRESERVED` per office whose clearance survived it.

    - `rereview_parties`: the parties that asked, who review the new version;
    - `reset_parties`: the offices whose clearance the policy reset;
    - `preserved_parties`: the offices whose `cleared` clearance it kept.
    """
    _write(
        AuditEvent.RESUBMITTED, actor, record,
        version=version.number, policy=policy, requests=sorted(requests),
        rereview_parties=list(rereview_parties),
        reset_parties=sorted(reset_parties),
        preserved_parties=sorted(preserved_parties),
    )
    for party in sorted(preserved_parties):
        _write(
            AuditEvent.CLEARANCE_PRESERVED, actor, record,
            party=str(party), version=version.number, policy=policy,
        )


# --- reviewer seats ------------------------------------------------------------------

def _seat_metadata(seat):
    return {
        "party": str(seat.assignment.party),
        "assignment": seat.assignment_id,
        "seat": seat.pk,
        "reviewer": seat.reviewer_id,
        "source": str(seat.source),
    }


def seat_moved(event_type, seat, actor, *, previous=None):
    """
    An ADR-032 seat move: `SEAT_CLAIMED`, `SEAT_ASSIGNED`, `SEAT_NOMINATED`,
    `REVIEWER_ADDED`, `SEAT_WITHDRAWN`, or `SEAT_REASSIGNED` with the seat it
    replaced as `previous`.
    """
    metadata = _seat_metadata(seat)
    if previous is not None:
        metadata.update(previous_seat=previous.pk, previous_reviewer=previous.reviewer_id)
    _write(event_type, actor, seat.assignment.record, **metadata)


def seat_opened(seat, actor):
    """The seat holder opened their review for the first time."""
    _write(AuditEvent.SEAT_OPENED, actor, seat.assignment.record, **_seat_metadata(seat))


# --- withdrawal ----------------------------------------------------------------------

def record_withdrawn(record, actor, *, closed_parties):
    """The owner withdrew the record from review; `closed_parties` lost their open work."""
    _write(
        AuditEvent.RECORD_WITHDRAWN, actor, record,
        version=_version(record), closed_parties=sorted(str(p) for p in closed_parties),
    )


# --- document requests (ADR-022) -----------------------------------------------------

def _items(items):
    return [{"id": item.pk, "label": item.label} for item in items]


def _every_item(request):
    return request.items.order_by("sort_order", "pk")


def _document_request(event_type, request, actor, items, **extra):
    _write(
        event_type, actor, request.record,
        party=str(request.party), request=request.pk, items=_items(items), **extra,
    )


def document_requested(request, actor):
    _document_request(
        AuditEvent.DOCUMENT_REQUESTED, request, actor, _every_item(request),
        message=request.message,
    )


def document_request_fulfilled(request, actor):
    _document_request(
        AuditEvent.DOCUMENT_REQUEST_FULFILLED, request, actor, _every_item(request),
    )


def document_accepted(request, item, actor):
    _document_request(AuditEvent.DOCUMENT_REQUEST_ACCEPTED, request, actor, [item])


def document_rejected(request, item, actor, *, reason):
    _document_request(AuditEvent.DOCUMENT_REQUEST_REJECTED, request, actor, [item], reason=reason)


def document_request_withdrawn(request, actor, *, closed_by=BY_REQUESTING_PARTY):
    _document_request(
        AuditEvent.DOCUMENT_REQUEST_WITHDRAWN, request, actor, _every_item(request),
        closed_by=closed_by, closed_by_decision=closed_by == BY_DECISION,
    )
