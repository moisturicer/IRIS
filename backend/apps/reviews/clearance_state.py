"""What the clearance payload says, derived once (IR-139).

The thesis contribution is *clearance-aware resubmission*: when one office
declines, only that office's clearance resets and the others survive. That is
implemented in `services.resubmit_record`, and until this module existed it was
**unobservable** — the API never said which clearances had survived, so a user
could not see it and an evaluator could not count it.

**One rule, one place.** `PaperViewPage` used to decide `preserved` in
TypeScript, from a different rule than the one the server applies. Two
definitions of the same word is how a screen ends up confidently wrong, so the
rule lives here and the client reads the answer.

Nothing here needs the declarative transition table (IR-136). `route[]` does,
which is why it is the one acceptance criterion this module deliberately does
not serve — an invented stage order would be worse than an absent one.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, NamedTuple, Optional, Sequence
from core.enums import ClearanceStatus, Office, VersionCause

#: Offices that hold an individual clearance. Mirrors
#: `RecordClearance.OFFICE_CHOICES`; the sequential stages (adviser, RDCO) do
#: not appear because they gate the record rather than clear it.
CLEARANCE_OFFICES = frozenset({Office.ITSO, Office.IERC, Office.KTTO})


def is_preserved(
    *,
    status: str,
    clearance_updated_at: Optional[datetime],
    last_resubmitted_at: Optional[datetime],
) -> bool:
    """True when this clearance survived a resubmission rather than being re-granted.

    Pure, so the rule that carries the contribution can be tested without a
    database, a request, or a workflow run.

    A clearance is preserved when it was already cleared *before* the owner
    resubmitted and was still cleared afterwards. A record that has never been
    resubmitted has nothing to preserve — every clearance on it was granted the
    first time round, which is emphatically not the contribution.
    """
    if status != ClearanceStatus.CLEARED:
        return False
    if last_resubmitted_at is None or clearance_updated_at is None:
        return False
    return clearance_updated_at < last_resubmitted_at


#: What a revision did to an office's clearance (IR-624).
PRESERVED = "preserved"
RESET = "reset"

#: `(number, created_at, cause)` for one of a record's versions.
VersionStamp = tuple[int, datetime, str]


class Carryover(NamedTuple):
    """What a revision did to one clearance, and the version it applies to."""

    state: str
    #: Preserved: the version the office cleared. Reset: the version that set
    #: it back, whose review it awaits. None before versions were recorded.
    version: Optional[int]

    @property
    def label(self) -> str:
        """In words, so the client maps no state to English."""
        if self.state == PRESERVED:
            return f"Cleared on v{self.version}, preserved" if self.version else "Cleared earlier, preserved"
        return f"Reset by v{self.version}" if self.version else "Reset by the new version"


def carryover(
    *,
    status: str,
    clearance_created_at: Optional[datetime],
    clearance_updated_at: Optional[datetime],
    last_resubmitted_at: Optional[datetime],
    versions: Sequence[VersionStamp],
) -> Optional[Carryover]:
    """Preserved, reset, or None: what a revision did to this clearance.

    The other half of `is_preserved`, so the Review section shows both sides
    of the contribution without the client inferring either (IR-624).
    `versions` is `record_versions(record)`, oldest first.

    **Reset** is a `pending` row a revision set back. Only a reset writes
    `pending` to an existing row (`lifecycle.clearance_reset_fields` stamps
    `updated_at`), and `submit_new_version` writes the version just before
    it, so the version is the newest revision written after the row was
    created and no later than its last update. That survives a later revision
    that did not touch the row: the office still awaits its review. A row
    pending since creation, or created after, was never set back; one the
    office has since reviewed is ordinary review. A resubmission the retired
    pipeline made without a version is read from `last_resubmitted_at`.

    **Preserved** is `is_preserved`, naming the version current when the
    office cleared.
    """
    if is_preserved(
        status=status,
        clearance_updated_at=clearance_updated_at,
        last_resubmitted_at=last_resubmitted_at,
    ):
        before = [n for n, at, _ in versions if at <= clearance_updated_at]
        return Carryover(PRESERVED, before[-1] if before else None)
    if (
        status != ClearanceStatus.PENDING
        or clearance_created_at is None or clearance_updated_at is None
    ):
        return None
    reset_by = [
        n for n, at, cause in versions
        if cause == VersionCause.REVISION and clearance_created_at < at <= clearance_updated_at
    ]
    if reset_by:
        return Carryover(RESET, reset_by[-1])
    if (
        last_resubmitted_at is not None
        and clearance_created_at < last_resubmitted_at <= clearance_updated_at
    ):
        return Carryover(RESET, None)
    return None


def carryover_fields(
    clearance, *, last_resubmitted_at: Optional[datetime], versions: Sequence[VersionStamp],
) -> dict[str, Any]:
    """The carryover keys a clearance and a tracker party row both carry."""
    carried = carryover(
        status=clearance.status,
        clearance_created_at=clearance.created_at,
        clearance_updated_at=clearance.updated_at,
        last_resubmitted_at=last_resubmitted_at,
        versions=versions,
    )
    return {
        "preserved": bool(carried and carried.state == PRESERVED),
        # Both sides of the contribution, with the version each applies to,
        # so no client infers either (IR-624).
        "carryover": carried.state if carried else None,
        "carryover_version": carried.version if carried else None,
        "carryover_label": carried.label if carried else None,
    }


def declining_office(latest_decline_stage: Optional[str]) -> Optional[str]:
    """The office whose decline caused the most recent resubmission, if any.

    A revision asked for by the Adviser, RDCO or the retired intake names no
    clearing office, so the answer is honestly None.
    """
    if latest_decline_stage in CLEARANCE_OFFICES:
        return latest_decline_stage
    return None


def record_versions(record) -> list[VersionStamp]:
    """Each of `record`'s versions as a `VersionStamp`, oldest first."""
    return list(record.versions.order_by("number").values_list("number", "created_at", "cause"))


def clearance_payload(
    clearance, *, last_resubmitted_at: Optional[datetime], readable: bool,
    versions: Sequence[VersionStamp],
) -> dict[str, Any]:
    """
    One office's clearance, as the API states it.

    `readable` is `core.permissions.may_read_review` for the viewer, and is
    required so no caller can forget it: the comment and who signed are review
    content, `None` -- not disclosed -- to anyone else; the outcome is not
    (IR-479). What a revision kept or reset is an outcome too.

    `versions` is `record_versions(record)`, read once by the caller.
    """
    return {
        "office": clearance.office,
        "office_label": clearance.get_office_display(),
        "status": clearance.status,
        "status_label": clearance.get_status_display(),
        "comment": clearance.comment if readable else None,
        "reviewed_by_name": (
            clearance.reviewed_by.get_full_name()
            if readable and clearance.reviewed_by else None
        ),
        "updated_at": clearance.updated_at.isoformat(),
        **carryover_fields(
            clearance, last_resubmitted_at=last_resubmitted_at, versions=versions,
        ),
    }


def resubmission_payload(record, *, clearances: Iterable, latest_decline_stage: Optional[str]) -> dict[str, Any]:
    """`resubmission{}` — what happened, and what survived it.

    Under a RESTART_ALL policy (IR-137) `offices_preserved` is simply empty —
    not because anything here knows the policy, but because that arm resets
    every clearance to `pending`, and `is_preserved` requires `CLEARED`. The
    rows themselves survive (ADR-004 resets rather than deletes, so the record
    keeps the office set ADR-018 put on it). That is why the UI needs no policy
    branch: the same shape answers both policies, and `PreservationNotice`
    renders off an empty array rather than off a flag.
    """
    last = record.last_resubmitted_at
    return {
        "count": record.resubmission_count,
        "last_resubmitted_at": last.isoformat() if last else None,
        "declining_office": declining_office(latest_decline_stage),
        "offices_preserved": [
            c.office
            for c in clearances
            if is_preserved(
                status=c.status,
                clearance_updated_at=c.updated_at,
                last_resubmitted_at=last,
            )
        ],
    }


def peer_summary(clearances: Iterable, *, excluding: Optional[str] = None) -> list[dict[str, Any]]:
    """The other offices' clearance state, for a reviewer deciding their own.

    `excluding` drops the viewer's own office, so a KTTO reviewer sees what ITSO
    and IERC have done and not a row telling them what they already know.

    Peer *status* only — never the peer's comment. A reviewer forming a view
    should see that a peer has decided without reading their reasoning first,
    which is what keeps the parallel clearances independent enough to compare.
    """
    return [
        {
            "office": c.office,
            "office_label": c.get_office_display(),
            "status": c.status,
            "status_label": c.get_status_display(),
        }
        for c in clearances
        if c.office != excluding
    ]
