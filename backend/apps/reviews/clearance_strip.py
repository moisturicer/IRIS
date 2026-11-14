"""
The clearance strip (IR-1083, `docs/frontend_ui_audit_spec.md` §4.4).

One compact line per specialist office on a record -- *ITSO · Cleared · Kept
from v1*, *IERC · Reviewing v2 · Reset by v2*, *KTTO · Unclaimed* -- so a list
row says which clearances a resubmission kept without the reader opening the
paper. It is ADR-003's contribution (clearance-aware resubmission) stated where
people work, and every word is chosen **here**: the client draws tone and icon
from `kind` and prints `text` and `note` as given (IR-374 invariant 15).

It reads the rules the tracker already applies and adds none of its own:
`clearance_state.carryover` says what a new version kept or reset, an open
`ResubmissionRequest` says an office asked for a revision, and a live
`ReviewerSeat` says someone is reviewing rather than the pool waiting.

**What it never carries is review content** -- no reviewer, comment or reason --
so the same strip is safe on every list that may name the record. It is built
for many records in a fixed number of queries, never per record.

**Visibility is the caller's.** It takes record ids and filters nothing: every
caller passes ids from rows `Record.objects.visible_to(user)` already allowed.

`kind` is a closed set the client styles exhaustively:
`kept` `cleared` `reviewing` `unclaimed` `revision` `not_cleared`.
"""

from __future__ import annotations

from typing import Any, Iterable

from apps.records.models import Record, RecordVersion
from core.enums import AssignmentState, ClearanceStatus, Office, ResubmissionRequestState, SeatState

from .clearance_state import PRESERVED, RESET, carryover
from .models import RecordAssignment, RecordClearance, ResubmissionRequest, ReviewerSeat

#: The offices a strip names, in the tracker's order.
STRIP_OFFICES = tuple(str(o) for o in Office)

#: Two kinds share a word with the clearance they report. They are spelled from
#: the enum, not by hand (`test_enum_vocabulary`), so a rename cannot split them.
KIND_CLEARED = str(ClearanceStatus.CLEARED.value)
KIND_NOT_CLEARED = str(ClearanceStatus.NOT_CLEARED.value)

#: A clearance an office finished with a negative outcome, shown in its own words.
_NEGATIVE = frozenset({
    ClearanceStatus.DECLINED, ClearanceStatus.REJECTED, ClearanceStatus.NOT_CLEARED,
})


def _note(carried) -> str | None:
    """What the latest version did to this office's clearance, in words."""
    if carried is None:
        return None
    if carried.state == PRESERVED:
        return f"Kept from v{carried.version}" if carried.version else "Kept from an earlier version"
    if carried.state == RESET:
        return f"Reset by v{carried.version}" if carried.version else "Reset by the new version"
    return None


def _entry(office, kind, text, *, note=None, version=None) -> dict[str, Any]:
    return {
        "party": office,
        "label": str(Office(office).label),
        "kind": kind,
        "text": text,
        "note": note,
        "version": version,
    }


def _office_entry(
    office, *, assignment, clearance, asking, held, current, record, versions,
) -> dict[str, Any] | None:
    """
    One office's entry, or None when it has nothing to say: it was never routed
    the record, or its work was withdrawn with nothing cleared.
    """
    if assignment is None:
        return None
    carried = carryover(
        status=clearance.status,
        clearance_created_at=clearance.created_at,
        clearance_updated_at=clearance.updated_at,
        last_resubmitted_at=record.last_resubmitted_at,
        versions=versions,
    ) if clearance else None
    note = _note(carried)
    version = carried.version if carried else None

    if office in asking:
        return _entry(office, "revision", "Asked for revision", note=note, version=version)
    if clearance and clearance.status == ClearanceStatus.CLEARED:
        kind = "kept" if carried and carried.state == PRESERVED else KIND_CLEARED
        return _entry(office, kind, "Cleared", note=note, version=version)
    if clearance and clearance.status in _NEGATIVE:
        return _entry(office, KIND_NOT_CLEARED, str(ClearanceStatus(clearance.status).label), note=note)
    if assignment.state != AssignmentState.ACTIVE:
        return None
    # `held` is any live seat, so a Done seat beside a colleague's open one still
    # reads Reviewing: the office has not finished (`seats.office_complete`).
    if assignment.pk in held:
        text = f"Reviewing v{current}" if current else "Reviewing"
        return _entry(office, "reviewing", text, note=note, version=current)
    return _entry(office, "unclaimed", "Unclaimed", note=note)


def clearance_strips(record_ids: Iterable[int]) -> dict[int, list[dict[str, Any]]]:
    """
    `{record id: [entry, ...]}` for each of `record_ids`, in a fixed number of
    queries (six, however many records). An entry is
    `{party, label, kind, text, note, version}`; a record no office has been
    routed gets `[]`.
    """
    ids = sorted(set(record_ids))
    strips: dict[int, list[dict[str, Any]]] = {pk: [] for pk in ids}
    if not ids:
        return strips

    records = {r.pk: r for r in Record.objects.filter(pk__in=ids).only("pk", "last_resubmitted_at")}

    assignments: dict[tuple[int, str], RecordAssignment] = {}
    for assignment in (
        RecordAssignment.objects.filter(record_id__in=ids, party__in=STRIP_OFFICES)
        .order_by("opened_at", "pk")
    ):
        assignments[(assignment.record_id, assignment.party)] = assignment  # the party's latest turn

    clearances = {
        (c.record_id, c.office): c for c in RecordClearance.objects.filter(record_id__in=ids)
    }

    versions: dict[int, list] = {}
    for record_id, number, created_at, cause in (
        RecordVersion.objects.filter(record_id__in=ids)
        .order_by("record_id", "number").values_list("record_id", "number", "created_at", "cause")
    ):
        versions.setdefault(record_id, []).append((number, created_at, cause))

    asking: dict[int, set[str]] = {}
    for record_id, party in ResubmissionRequest.objects.filter(
        record_id__in=ids, state=ResubmissionRequestState.OPEN,
    ).values_list("record_id", "party"):
        asking.setdefault(record_id, set()).add(party)

    held = set(
        ReviewerSeat.objects.filter(assignment__record_id__in=ids)
        .exclude(state=SeatState.WITHDRAWN).values_list("assignment_id", flat=True)
    )

    for record_id in ids:
        record = records.get(record_id)
        if record is None:
            continue
        stamps = versions.get(record_id, [])
        current = stamps[-1][0] if stamps else None
        for office in STRIP_OFFICES:
            entry = _office_entry(
                office,
                assignment=assignments.get((record_id, office)),
                clearance=clearances.get((record_id, office)),
                asking=asking.get(record_id, set()),
                held=held,
                current=current,
                record=record,
                versions=stamps,
            )
            if entry:
                strips[record_id].append(entry)
    return strips


def attach_clearance_strips(rows: list[dict[str, Any]]) -> None:
    """
    Set `clearance_strip` on each row (a dict with a `record` id), for the whole
    page in `clearance_strips`' fixed number of queries. One place, so My
    Reviews and the office console cannot drift apart (IR-1083).
    """
    strips = clearance_strips({row["record"] for row in rows})
    for row in rows:
        row["clearance_strip"] = strips[row["record"]]
