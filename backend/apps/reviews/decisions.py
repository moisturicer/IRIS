"""
The Adviser or RDCO decides a Thesis/Research or Project (ADR-032 §3, §11;
ADR-021 §12; IR-270).

**A Decision ends a record's review.** Three outcomes, by who decides:

- **The Adviser**, while their own seat is open (no specialist path):
  *publish* or *reject*. RDCO is never involved.
- **RDCO**, on the specialist path, holding the hand-back's seat: *publish*,
  *keep unlisted* (`completed`) or *reject*.

Accept & route (IR-261) is not a Decision. It is an acceptance that closes
nothing; it shares only the rule that it is refused while a revision request
is open (`revisions.decision_blocked_reason`).

**What a Decision writes, in one transaction:**

1. the decider's own `Review` -- `approved` for both accepts, `rejected` for a
   reject -- against the latest version. My Reviews tells *published* from
   *accepted* by the record's status and "this is its latest approval", so no
   outcome is stored twice (IR-268);
2. the decider's seat `done`, and their assignment `completed`. Any other
   unfinished seat on that assignment -- a second RDCO reviewer -- is
   withdrawn;
3. every other active assignment and its unfinished seats `withdrawn`, and
   every open `DocumentRequest` `withdrawn`, the decider's own included. Each
   closed assignment, withdrawn seat and request names the decision in
   `closed_by_decision`, which is the reason ADR-021 §12 asks for. A withdrawn office round leaves
   its `RecordClearance` as it was: a clearance records completed rounds only
   (ADR-032 §4 Amendment);
4. `pipeline_status` -- written here, not through `lifecycle.apply()`. The
   legacy table has no edge out of `in_review`, and `apply()` would run
   `shadow.sync()`, which closes assignments as *completed* where a Decision
   withdraws them. This is the second write outside `apply()`, beside
   `routing.enter_at_adviser()`; IR-260 folds both in.

**Before anything is written**, the act refuses, who before what:

- a caller holding no open Adviser or RDCO seat here (403). An Adviser who
  has already accepted & routed is told RDCO decides now; an RDCO member
  without a seat is told to claim it;
- a Proposal (400: IR-271 builds its accept and reject), or a record still on
  the legacy pipeline (400);
- an unknown outcome, or one the decider may not take -- only RDCO keeps a
  record unlisted (400);
- a reject with no reason (400);
- an unopened seat (400, "Open the review first", as Clear and Request
  revision refuse);
- an open revision request (400, its explanation);
- a stale dialog (409). Record detail carries a `token` summarising what the
  decision would close; the client echoes it, and a record that has moved
  since -- a new version, an office routed to, a seat or document request
  opened -- is refused with what the decision would close now, so nobody
  decides into a state they did not see.

Notifications, after commit: the owners once, and the holders of the open
seats the decision withdrew.
"""

from __future__ import annotations

import hashlib
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.records.lifecycle import type_name_of
from apps.records.versions import latest_version
from core.enums import (
    OPEN_SEAT_STATES,
    AssignmentState,
    DocumentRequestState,
    Party,
    PipelineStatus,
    RecordTypeName,
    ReviewDecision,
    SeatState,
)
from core.permissions import is_office_member

from . import revisions, routing, seats
from .models import RecordAssignment, Review, ReviewerSeat

PUBLISH = "publish"
KEEP_UNLISTED = "keep_unlisted"
REJECT = "reject"

#: Each outcome: the decider's verdict, and the status it leaves the record in.
OUTCOMES = {
    PUBLISH: (ReviewDecision.APPROVED, PipelineStatus.PUBLISHED),
    KEEP_UNLISTED: (ReviewDecision.APPROVED, PipelineStatus.COMPLETED),
    REJECT: (ReviewDecision.REJECTED, PipelineStatus.REJECTED),
}

#: Who may take which outcome, in the order the action bar offers them.
#: RDCO alone keeps a record unlisted (ADR-032 §3).
OUTCOMES_FOR = {
    str(Party.ADVISER): (PUBLISH, REJECT),
    str(Party.RDCO): (PUBLISH, KEEP_UNLISTED, REJECT),
}

#: How the tracker names a Decision on the work it closed ("RDCO published
#: the record").
_VERB = {
    PUBLISH: "published the record",
    KEEP_UNLISTED: "accepted the record and kept it unlisted",
    REJECT: "rejected the record",
}

#: Who decided, in prose: the owner's notification and the tracker's "RDCO
#: published the record". Structured payloads keep the party's own label.
DECIDER_NAME = {str(Party.ADVISER): "The Adviser", str(Party.RDCO): "RDCO"}

_label = seats._label


class DecisionError(Exception):
    """Understood, but not possible as asked. A 400."""


class DecisionRefused(Exception):
    """The caller may not decide this record. A 403."""


class DecisionStale(Exception):
    """The record changed since the caller's dialog read it. A 409."""


# --- who decides, as what ------------------------------------------------------------

def _deciding_party(record, user) -> Optional[str]:
    """
    The party `user` may decide `record` as, or None: its Adviser holding the
    open Adviser seat (and not owning the record), or RDCO's seat holder.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    if routing._seated_adviser(record, user):
        return str(Party.ADVISER)
    if _decider_seat(record, user, Party.RDCO) is not None:
        return str(Party.RDCO)
    return None


def _decider_seat(record, user, party) -> Optional[ReviewerSeat]:
    return (
        ReviewerSeat.objects.select_related("assignment")
        .filter(
            assignment__record=record, assignment__party=party,
            assignment__state=AssignmentState.ACTIVE, reviewer=user,
            state__in=OPEN_SEAT_STATES,
        )
        .first()
    )


def _refusal(record, user) -> str:
    """Why `user`, holding no deciding seat, may not decide: said as usefully as we can."""
    if user is not None and record.adviser_id == getattr(user, "pk", None):
        if record.owners.filter(user=user).exists():
            return "Nobody decides their own submission."
        return (
            "You have already accepted this record and sent it for specialist "
            "review, so RDCO decides it now."
        )
    if is_office_member(user, Party.RDCO):
        return (
            "Claim this review from RDCO's pool, or be assigned it, before you "
            "decide it."
        )
    return (
        "Only the record's Adviser, holding its review, or RDCO's reviewer may "
        "decide this record."
    )


def _require_decidable(record):
    if type_name_of(record) == RecordTypeName.PROPOSAL:
        raise DecisionError(
            "A Proposal is accepted or rejected by its Adviser, never published, "
            "and IRIS does not offer that decision yet."
        )
    if not routing.is_new_model(record):
        raise DecisionError(
            "This record is still on the current review pipeline. Use the "
            "current decision form."
        )


def _blocked_reason(record, seat) -> Optional[str]:
    """Why the seated decider cannot decide yet, or None."""
    if seat is not None and seat.state == SeatState.ASSIGNED:
        return "Open the review first."
    return revisions.decision_blocked_reason(record)


# --- what a decision would close -------------------------------------------------------

def _open_document_requests(record):
    from apps.documents.models import DocumentRequest

    return DocumentRequest.objects.filter(record=record, state=DocumentRequestState.OPEN)


def _closing(record):
    """
    The assignments a decision would close and, for each, the open seats it
    would withdraw: every active assignment but the decider's, plus the
    decider's own when someone else is seated on it too.
    """
    rows = []
    for assignment in (
        RecordAssignment.objects.filter(record=record, state=AssignmentState.ACTIVE)
        .order_by("opened_at", "pk")
    ):
        open_seats = list(
            assignment.seats.filter(state__in=OPEN_SEAT_STATES)
            .select_related("reviewer").order_by("assigned_at", "pk")
        )
        rows.append((assignment, open_seats))
    return rows


def closes_payload(record, decider_seat) -> dict:
    """
    `closes` on record detail and on a 409: what deciding now would end.
    Holders' names go only to the decider, who holds a seat and so may read
    the review (IR-479).
    """
    assignments = []
    for assignment, open_seats in _closing(record):
        holders = [
            s.reviewer.get_full_name() for s in open_seats if s.pk != decider_seat.pk
        ]
        if assignment.pk == decider_seat.assignment_id and not holders:
            continue  # the decider's own turn, with nobody else on it, simply completes
        assignments.append({
            "party": assignment.party, "label": _label(assignment.party), "holders": holders,
        })
    return {
        "assignments": assignments,
        "document_requests": _open_document_requests(record).count(),
    }


def decision_token(record) -> str:
    """
    A short digest of everything a decision would act on: the latest version,
    every active assignment, every open seat and every open document request.
    Any change to any of them changes the token, so a dialog opened before the
    change is refused rather than deciding into it (IR-270, decision 11).
    """
    version = latest_version(record)
    active = sorted(
        RecordAssignment.objects.filter(record=record, state=AssignmentState.ACTIVE)
        .values_list("pk", flat=True)
    )
    open_seats = sorted(
        ReviewerSeat.objects.filter(
            assignment__record=record, assignment__state=AssignmentState.ACTIVE,
            state__in=OPEN_SEAT_STATES,
        ).values_list("pk", "state")
    )
    requests = sorted(_open_document_requests(record).values_list("pk", flat=True))
    facts = f"{version.pk if version else 0}|{active}|{open_seats}|{requests}"
    return hashlib.sha256(facts.encode()).hexdigest()[:16]


# --- what record detail tells Paper View ------------------------------------------------

def author_hints(record) -> list[str]:
    """The author's ADR-018 flags, as the routing dialog words them (ADR-032 §3)."""
    return [
        routing._HINT_TEXT[office]
        for office, field in routing._HINT_FIELD.items()
        if getattr(record, field, False)
    ]


def decision_flags(record, user) -> dict:
    """
    `decision` on record detail (IR-270): the outcomes the viewer may take, why
    not yet, what deciding would close, the staleness token, and -- for the
    Adviser -- the author's hints the publish confirmation shows. A rendering
    hint; `decide/` re-checks all of it.
    """
    empty = {
        "party": None, "outcomes": [], "blocked": None, "closes": None,
        "token": None, "author_hints": [],
    }
    if not routing._routable(record):
        return empty
    party = _deciding_party(record, user)
    if party is None:
        return empty
    seat = _decider_seat(record, user, party)
    return {
        "party": party,
        "outcomes": list(OUTCOMES_FOR[party]),
        "blocked": _blocked_reason(record, seat),
        "closes": closes_payload(record, seat),
        "token": decision_token(record),
        "author_hints": author_hints(record) if party == Party.ADVISER else [],
    }


# --- the act ------------------------------------------------------------------------------

def _close_assignment(assignment, actor, now, review, state):
    assignment.state = state
    assignment.closed_by = actor
    assignment.closed_at = now
    assignment.closed_by_decision = review
    assignment.save(update_fields=["state", "closed_by", "closed_at", "closed_by_decision"])


@transaction.atomic
def decide(record, actor, *, outcome, comment="", token=None) -> Review:
    """
    Decide `record` as the caller's party. Returns the decider's `Review`.
    Raises `DecisionRefused` (403), `DecisionError` (400) or `DecisionStale`
    (409), writing nothing.
    """
    record = routing._locked(record)
    # And every active assignment: a claim or an *Add reviewer* locks only its
    # assignment, not the record, so without this one could land between the
    # token check and the closing below and leave an open seat behind on a
    # withdrawn turn. Everything else that opens work here -- routing, a
    # revision request, a document request -- locks the record.
    list(
        RecordAssignment.objects.select_for_update()
        .filter(record=record, state=AssignmentState.ACTIVE)
    )
    party = _deciding_party(record, actor)
    if party is None:
        raise DecisionRefused(_refusal(record, actor))
    _require_decidable(record)

    if not isinstance(outcome, str) or outcome not in OUTCOMES:
        raise DecisionError("Choose to publish, keep unlisted or reject the record.")
    if outcome not in OUTCOMES_FOR[party]:
        raise DecisionError(
            "Only RDCO may accept a record and keep it unlisted, after specialist review."
        )
    comment = comment.strip() if isinstance(comment, str) else ""
    if outcome == REJECT and not comment:
        raise DecisionError("Say why the record is rejected. The owner reads it as written.")

    seat = _decider_seat(record, actor, party)
    blocked = _blocked_reason(record, seat)
    if blocked:
        raise DecisionError(blocked)
    if not isinstance(token, str) or not token:
        raise DecisionError("Reload the record and decide again.")
    if token != decision_token(record):
        raise DecisionStale(
            "This record changed while you were deciding. Check what deciding "
            "would now close, then decide again."
        )

    verdict, new_status = OUTCOMES[outcome]
    review = Review.objects.create(
        record=record, reviewed_by=actor, stage=party, status=verdict,
        comment=comment, assignment=seat.assignment, version=latest_version(record),
    )

    # Seats are closed here rather than through `seats.complete_seat()` and
    # `seats.withdraw()`: those run the office completion rule and its
    # hand-back, which must not fire on a record the Decision is ending, and
    # `withdraw()` is a coordinator's act with a coordinator's checks.
    now = timezone.now()
    cut_off = []  # reviewers whose open seat the decision withdrew
    for assignment, open_seats in _closing(record):
        own = assignment.pk == seat.assignment_id
        others = [s for s in open_seats if s.pk != seat.pk]
        ReviewerSeat.objects.filter(pk__in=[s.pk for s in others]).update(
            state=SeatState.WITHDRAWN, closed_by_decision=review,
        )
        cut_off.extend(s.reviewer for s in others)
        _close_assignment(
            assignment, actor, now, review,
            AssignmentState.COMPLETED if own else AssignmentState.WITHDRAWN,
        )
    ReviewerSeat.objects.filter(pk=seat.pk).update(state=SeatState.DONE, done_at=now)

    requests = list(_open_document_requests(record).select_for_update())
    for request in requests:
        request.state = DocumentRequestState.WITHDRAWN
        request.closed_at = now
        request.closed_by_decision = review
        request.save(update_fields=["state", "closed_at", "closed_by_decision"])

    # The one status write of a Decision (module note, point 4).
    record.pipeline_status = new_status
    record.save(update_fields=["pipeline_status", "updated_at"])

    _notify(record, actor, party, outcome, review, closed_requests=len(requests), cut_off=cut_off)
    return review


def withdrawn_by_label(review) -> str:
    """
    How the tracker names the Decision that closed something: "RDCO published
    the record". *Published* is told from *kept unlisted* by the record's
    status, the rule My Reviews uses (ADR-032 §9 Amendment), so the two always
    agree; an act that later publishes an unlisted record would reword both.
    """
    outcome = (
        REJECT if review.status == ReviewDecision.REJECTED
        else PUBLISH if review.record.pipeline_status == PipelineStatus.PUBLISHED
        else KEEP_UNLISTED
    )
    return f"{DECIDER_NAME[str(review.stage)]} {_VERB[outcome]}"


def _notify(record, actor, party, outcome, review, *, closed_requests, cut_off):
    from apps.notifications.services import notify_decided

    transaction.on_commit(lambda: notify_decided(
        record,
        actor=actor,
        decided_by=DECIDER_NAME[party],
        outcome=outcome,
        reason=review.comment,
        closed_requests=closed_requests,
        cut_off=cut_off,
    ))
