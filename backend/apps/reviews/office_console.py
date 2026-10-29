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

from django.db.models import Prefetch

from apps.records.models import Record
from core.enums import OPEN_SEAT_STATES, AssignmentState, Party, PipelineStatus, SeatState
from core.permissions import is_office_coordinator, office_parties_of

from .deadlines import deadline_payload, with_deadlines
from .models import RecordAssignment, ReviewerSeat
from .seats import office_members


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


def _row(assignment, user, seat=None) -> dict:
    record = assignment.record
    return {
        "key": f"seat:{seat.pk}" if seat else f"pool:{assignment.pk}",
        "kind": "seat" if seat else "pool",
        "record": record.pk,
        "title": record.title,
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
    }


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

    load = []
    for member in office_members(office):
        mine = [r for r in rows if r["reviewer"] == member.pk]
        load.append({
            "reviewer": member.pk,
            "name": _name(member),
            "open": len(mine),
            "overdue": sum(r["is_overdue"] for r in mine),
        })
    return {
        "office": office,
        "office_label": str(Party(office).label),
        "rows": rows,
        "load": load,
    }
