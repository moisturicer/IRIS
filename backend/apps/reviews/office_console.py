"""
The coordinator console (IR-623): one office's open work, as its coordinator
sees it. Served by `GET /api/v1/reviews/office/`.

- **rows**: every unfinished seat on the office's active assignments, and
  every assignment nobody is seated on (the pool), each with its due date
  (ADR-043). Overdue first, then soonest due; an assignment whose party has
  no Turnaround has no due date and sorts last.
- **load**: every active member of the office, idle ones included, with
  their open and overdue seats -- counted from `rows`, so the two agree.

**It decides nothing.** Its acts are IR-415's seat endpoints and IR-619's
extension, which each re-check the caller; the console only says which of
them a row offers. Only a coordinator of the office may read it, as only a
coordinator may read My Reviews' office view.
"""

from __future__ import annotations

from datetime import datetime

from django.db.models import Prefetch
from django.utils import timezone

from apps.records.models import Record, RecordVersion
from core.enums import (
    OPEN_SEAT_STATES, AssignmentState, Party, PipelineStatus, ResubmissionRequestState, SeatState,
)
from core.permissions import is_office_coordinator, office_parties_of

from .clearance_strip import attach_clearance_strips
from .deadlines import MANILA, deadline_payload, with_deadlines
from .models import RecordAssignment, ResubmissionRequest, ReviewerSeat
from .removal import unresolved_many
from .seats import completes, office_members


class ConsoleRefused(Exception):
    """The caller does not coordinate that office. A 403."""


def _name(user) -> str | None:
    if user is None:
        return None
    return user.get_full_name() or user.email


def _office(user, office) -> str:
    """The office asked for, or the one the caller coordinates; else refused."""
    if not office:
        office = next(
            (p for p in sorted(office_parties_of(user)) if is_office_coordinator(user, p)), None,
        )
    if not office or not is_office_coordinator(user, office):
        raise ConsoleRefused("Only a coordinator of that office may open its console.")
    return str(office)


def _days(n: int) -> str:
    return f"{n} day" if n == 1 else f"{n} days"


def _authors_line(record, version) -> str:
    """"Ada Lovelace, Alan Turing · v2": who wrote it and which Version is under review."""
    names = ", ".join(a.name for a in record.authors.all())
    tag = f"v{version}" if version else None
    return " · ".join(part for part in (names, tag) if part)


def _status(row, *, now) -> dict:
    """
    The row's status chip, worded here (ADR-043): the browser computes no
    "overdue". `kind` is `kept` `overdue` `unassigned` `due` `paused` `no_date`.
    A clearance this office already holds from an earlier Version leads.
    """
    for entry in row["clearance_strip"]:
        if entry["party"] == row["office"] and entry["kind"] == "kept":
            return {"kind": "kept", "text": f"Cleared on v{entry['version']} · kept"
                    if entry["version"] else "Cleared · kept"}
    due = row["due_at"]
    today = now.astimezone(MANILA).date()
    if due and row["is_overdue"]:
        late = (today - datetime.fromisoformat(due).astimezone(MANILA).date()).days
        return {"kind": "overdue", "text": f"Overdue by {_days(max(late, 1))}"}
    if row["kind"] == "pool":
        return {"kind": "unassigned", "text": "Unassigned"}
    if row["clock_paused"]:
        return {"kind": "paused", "text": "Clock paused"}
    if not due:
        return {"kind": "no_date", "text": "No due date"}
    left = (datetime.fromisoformat(due).astimezone(MANILA).date() - today).days
    return {"kind": "due", "text": "Due today" if left <= 0 else f"Due in {_days(left)}"}


def _actions(row) -> list[str]:
    """What the viewer may do to this row, in menu order. The server re-checks each act."""
    # A seat row is an open seat, so it may be withdrawn as well (IR-1226).
    acts = ["assign"] if row["kind"] == "pool" else ["reassign", "withdraw"]
    if row["can_extend"]:
        acts.append("extend")
    return acts


def _row(assignment, user, seat=None) -> dict:
    record = assignment.record
    return {
        "key": f"seat:{seat.pk}" if seat else f"pool:{assignment.pk}",
        "kind": "seat" if seat else "pool",
        "record": record.pk,
        "title": record.title,
        "office": str(assignment.party),
        "assignment": assignment.pk,
        "seat": seat.pk if seat else None,
        "reviewer": seat.reviewer_id if seat else None,
        "reviewer_name": _name(seat.reviewer) if seat else None,
        "seat_state": seat.state if seat else None,
        "seat_state_label": seat.get_state_display() if seat else None,
        # When the office received the record. Not `clock_started_at`, which a
        # new Version restarts (ADR-043 §5): "opened" is when it arrived.
        "opened_at": assignment.opened_at.isoformat(),
        **deadline_payload(assignment, user),
        # Filled for the whole console at once (`_attach_removal`); None on a pool row.
        "unresolved": None,
        "withdraw_completes_office": None,
    }


def _attach_removal(rows, assignments, office) -> None:
    """
    What each seat holder leaves if reassigned or withdrawn, and whether
    withdrawing their seat finishes the office (IR-1226), in a fixed number of
    queries however many rows there are. Every console assignment is active
    and in review, so the seats already loaded decide it; `seats.withdraw`
    decides it again under its lock.
    """
    seat_rows = [r for r in rows if r["kind"] == "seat"]
    counts = unresolved_many((r["record"], r["reviewer"]) for r in seat_rows if r["reviewer"])
    asked = {(a.record_id, a.party) for a in assignments}
    open_resubmission = set(
        ResubmissionRequest.objects.filter(
            record_id__in={record for record, _ in asked}, party=office,
            state=ResubmissionRequestState.OPEN,
        ).values_list("record_id", "party")
    ) if asked else set()
    by_pk = {a.pk: a for a in assignments}
    for row in seat_rows:
        assignment = by_pk[row["assignment"]]
        row["unresolved"] = counts.get((row["record"], row["reviewer"]))
        row["withdraw_completes_office"] = completes(
            [s.state for s in assignment.console_seats if s.pk != row["seat"]],
            open_resubmission=lambda a=assignment: (a.record_id, a.party) in open_resubmission,
        )


def _order(row):
    return (not row["is_overdue"], row["due_at"] is None, row["due_at"] or "", row["opened_at"], row["key"])


def office_console(user, *, office=None) -> dict:
    """`{office, office_label, rows, load}` for a coordinator; `ConsoleRefused` otherwise."""
    office = _office(user, office)
    live = ReviewerSeat.objects.exclude(state=SeatState.WITHDRAWN).select_related("reviewer")
    assignments = with_deadlines(
        RecordAssignment.objects.filter(
            party=office,
            state=AssignmentState.ACTIVE,
            record__pipeline_status=PipelineStatus.IN_REVIEW,
            record__in=Record.objects.visible_to(user),
        ).select_related("record").prefetch_related(
            "record__authors",
            Prefetch("seats", queryset=live.order_by("assigned_at", "pk"), to_attr="console_seats"),
        )
    )

    rows = []
    for assignment in assignments:
        seats = assignment.console_seats
        if not seats:
            rows.append(_row(assignment, user))
        # A seat already done is history; an assignment whose seats are all
        # done (waiting on its author, say) has no open work to show.
        rows.extend(_row(assignment, user, s) for s in seats if s.state in OPEN_SEAT_STATES)
    rows.sort(key=_order)
    _attach_removal(rows, assignments, office)
    attach_clearance_strips(rows)  # which clearances each record holds (IR-1083)

    version_of = {}
    for record_id, number in RecordVersion.objects.filter(
        record_id__in={r["record"] for r in rows},
    ).order_by("record_id", "number").values_list("record_id", "number"):
        version_of[record_id] = number
    authors = {a.record_id: a.record for a in assignments}
    now = timezone.now()
    for row in rows:
        row["authors_line"] = _authors_line(authors[row["record"]], version_of.get(row["record"]))
        row["status"] = _status(row, now=now)
        row["actions"] = _actions(row)

    load = []
    for member in office_members(office):
        mine = [r for r in rows if r["reviewer"] == member.pk]
        load.append({
            "reviewer": member.pk,
            "name": _name(member),
            "open_count": len(mine),
            "overdue": sum(r["is_overdue"] for r in mine),
        })
    return {
        "office": office,
        "office_label": str(Party(office).label),
        "rows": rows,
        "load": load,
    }
