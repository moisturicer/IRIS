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
from typing import Any, Iterable, Optional
from core.enums import ClearanceStatus, Office

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


def declining_office(latest_decline_stage: Optional[str]) -> Optional[str]:
    """The office whose decline caused the most recent resubmission, if any.

    A decline at a sequential stage (adviser, `rdco_intake`, `rdco_review`)
    resets everything, so there is no *office* to name — `resubmit_record`
    deletes every clearance in that case and the answer is honestly None.
    """
    if latest_decline_stage in CLEARANCE_OFFICES:
        return latest_decline_stage
    return None


def clearance_payload(clearance, *, last_resubmitted_at: Optional[datetime]) -> dict[str, Any]:
    """One office's clearance, as the API states it."""
    return {
        "office": clearance.office,
        "office_label": clearance.get_office_display(),
        "status": clearance.status,
        "status_label": clearance.get_status_display(),
        "comment": clearance.comment,
        "reviewed_by_name": (
            clearance.reviewed_by.get_full_name() if clearance.reviewed_by else None
        ),
        "updated_at": clearance.updated_at.isoformat(),
        "preserved": is_preserved(
            status=clearance.status,
            clearance_updated_at=clearance.updated_at,
            last_resubmitted_at=last_resubmitted_at,
        ),
    }


def resubmission_payload(record, *, clearances: Iterable, latest_decline_stage: Optional[str]) -> dict[str, Any]:
    """`resubmission{}` — what happened, and what survived it.

    Under a RESTART_ALL policy (IR-137) `offices_preserved` is simply empty,
    because `resubmit_record` deletes every clearance on that path. That is why
    the UI needs no policy branch: the same shape answers both policies.
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
