"""
Readiness: what stands between the viewer and their part of the review
(ADR-032 §10 Amendment, IR-679; built in IR-681).

Record detail's `readiness` block. It re-derives no rule: `build_readiness`
reads the `decision`, `revision`, `office_review`, `my_seats` and
`review_claim` blocks record detail already computed, plus the record's
active assignments and open document requests, and puts them into words.
Every action endpoint still re-checks its own predicate.

- `ready` exactly when the decision block offers outcomes and names no
  blocker, so a Decision would be accepted for this state.
- Every `decision.blocked` (and `office_review.blocked`) reason has at least
  one blocker item, so nothing the services refuse is left unsaid.
- `None` -- not disclosed, which is not an empty list -- to a viewer who may
  not read the review (IR-479).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from django.utils import dateformat, timezone

from core.enums import AssignmentState, DocumentRequestState, ResubmissionRequestState, SeatState

from .models import RecordAssignment
from .seats import _label, _name

BLOCKER, INFO = "blocker", "info"


def _item(kind, severity, label, *, party=None, actor_name=None, since=None,
          paused=None, action=None) -> dict:
    return {
        "kind": kind, "severity": severity, "label": label, "party": party,
        "actor_name": actor_name, "since": since, "paused": paused, "action": action,
    }


def _action(kind, target=None) -> dict:
    return {"kind": kind, "target": None if target is None else str(target)}


def _day(value) -> str:
    return dateformat.format(timezone.localtime(value), "D j M")


def readiness_facts(record, user) -> dict:
    """The active assignments and open document requests readiness reads."""
    from apps.documents.models import DocumentRequest
    from apps.documents.requests import may_read_requests

    from .deadlines import deadline_payload, revision_pending

    assignments = []
    for assignment in (
        RecordAssignment.objects.filter(record=record, state=AssignmentState.ACTIVE)
        .order_by("opened_at", "pk")
    ):
        live = list(
            assignment.seats.exclude(state=SeatState.WITHDRAWN)
            .select_related("reviewer").order_by("assigned_at", "pk")
        )
        # What stopped this party's clock (ADR-043 §4): its own document
        # request, else its own revision request.
        paused_by = (
            "document_request" if assignment.document_pause_started_at
            else "revision_request" if revision_pending(assignment) else None
        )
        assignments.append({
            "paused_by": paused_by,
            "id": assignment.pk,
            "party": assignment.party,
            "label": _label(assignment.party),
            "opened_at": assignment.opened_at.isoformat() if assignment.opened_at else None,
            "seats": [{"reviewer": s.reviewer_id, "name": _name(s.reviewer), "state": s.state}
                      for s in live],
            **deadline_payload(assignment, user),
        })
    # Which party asked the owner for what is its own rule (IR-349).
    requests = [
        {"id": r.pk, "party": r.party, "label": _label(r.party),
         "requested_by": _name(r.requested_by) if r.requested_by else None,
         "created_at": r.created_at.isoformat()}
        for r in DocumentRequest.objects.filter(record=record, state=DocumentRequestState.OPEN)
        .select_related("requested_by").order_by("created_at", "pk")
    ] if may_read_requests(record, user) else []
    return {"assignments": assignments, "document_requests": requests}


def build_readiness(*, user, readable: bool, in_review: bool, decision: dict,
                    revision: dict, office_review: dict, my_seats: list,
                    review_claim: Optional[dict], facts: dict) -> Optional[dict]:
    """The `readiness` block, from blocks record detail already computed."""
    if not readable:
        return None
    if not in_review:
        return {"verdict": "none", "headline": "This record is not in review.", "items": []}

    deciding = bool(decision.get("outcomes"))
    office = office_review.get("party")
    blocked = decision.get("blocked") if deciding else office_review.get("blocked") if office else None
    closing = {a["party"] for a in (decision.get("closes") or {}).get("assignments", [])}
    viewer = getattr(user, "pk", None)
    items: list[dict] = []

    unopened = next((s for s in my_seats if s["state"] == SeatState.ASSIGNED), None)
    if (deciding or office) and unopened is not None:
        items.append(_item(
            "open_review", BLOCKER, "Open the review first.",
            party=unopened["party"], action=_action("open_review", unopened["id"]),
        ))

    # The revision block lists its open requests under the request state's name.
    for request in revision.get(ResubmissionRequestState.OPEN.value) or []:
        # Any open request blocks a Decision; an office only by its own.
        blocks = deciding or request["party"] == office
        items.append(_item(
            "revision_request", BLOCKER if blocks else INFO,
            f"{request['label']} asked the author for a revision.",
            party=request["party"], actor_name=request["requested_by"], since=request["created_at"],
            action=(_action("withdraw_revision", request["id"])
                    if revision.get("withdrawable") == request["id"] else None),
        ))

    for request in facts["document_requests"]:
        # The service refuses an office's finish only on its own request.
        items.append(_item(
            "document_request", BLOCKER if request["party"] == office else INFO,
            f"{request['label']} asked the author for a document.",
            party=request["party"], actor_name=request["requested_by"], since=request["created_at"],
            action=_action("open_documents", request["id"]),
        ))

    for assignment in facts["assignments"]:
        party, label = assignment["party"], assignment["label"]
        if any(s["reviewer"] == viewer for s in assignment["seats"]):
            continue  # the viewer's own turn is the verdict, not a fact beside it
        if not assignment["seats"]:
            claimable = review_claim and review_claim["assignment"] == assignment["id"]
            items.append(_item(
                "pool_unclaimed", INFO, f"Nobody at {label} has claimed this review yet.",
                party=party, since=assignment["opened_at"],
                action=_action("claim", assignment["id"]) if claimable else _action("show_party", party),
            ))
            continue
        label_text = f"{label} is reviewing."
        if deciding and party in closing:
            label_text = f"{label} is reviewing. A Decision now closes its review."
        items.append(_item(
            "party_reviewing", INFO, label_text, party=party,
            actor_name=", ".join(s["name"] for s in assignment["seats"] if s["name"]) or None,
            since=assignment["opened_at"], action=_action("show_party", party),
        ))

    # The viewer's own due date (IR-684): the party they hold a seat for, or
    # the pool they may claim. Other parties' dates stay in the sidebar.
    claim = review_claim["assignment"] if review_claim else None
    for assignment in facts["assignments"]:
        due = assignment["due_at"]
        if not due:
            continue  # no configured Turnaround, no due date
        if assignment["id"] != claim and not any(s["reviewer"] == viewer for s in assignment["seats"]):
            continue
        when = _day(datetime.fromisoformat(due))
        label = assignment["label"]
        text = f"{label} was due {when}." if assignment["is_overdue"] else f"{label} is due {when}."
        if assignment["clock_paused"]:
            why = "document request" if assignment["paused_by"] == "document_request" else "revision request"
            text = f"{label} is due {when}. The clock is paused while {label}'s {why} is open."
        items.append(_item(
            "due_date", INFO, text, party=assignment["party"], paused=assignment["clock_paused"],
        ))

    if blocked and not any(i["severity"] == BLOCKER for i in items):
        # A refusal this builder has no kind for is still said, in the
        # service's own words.
        items.append(_item("refusal", BLOCKER, blocked, party=decision.get("party") or office))

    items.sort(key=lambda i: i["severity"] != BLOCKER)
    if deciding:
        verdict = "blocked" if blocked else "ready"
        headline = "You can't decide yet." if blocked else "Ready for your Decision."
    elif office:
        verdict = "blocked" if blocked else "waiting_on_you"
        headline = (f"{office_review['label']} can't finish yet." if blocked
                    else "Ready to clear or record a finding.")
    elif review_claim:
        verdict = "waiting_on_you"
        headline = f"{review_claim['party_label']} has not claimed this review yet."
    else:
        verdict, headline = "none", "Nothing here waits on you."
    return {"verdict": verdict, "headline": headline, "items": items}
