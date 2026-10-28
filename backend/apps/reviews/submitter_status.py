"""
What a submitter is told about their own record (IR-625).

`submitter_status` is one block, sent to an owner only, on My Library's list
and on Record detail:

- `line`: one plain sentence saying where the record is -- *With your
  Adviser*, *In specialist review: IERC, KTTO*, *Revision requested by IERC:
  action needed*. The frontend shows it as sent and words nothing itself
  (IR-342's rule).
- `waiting_on_you`: one item per party with an open revision request or
  document request, each naming the act that answers it. It is non-empty
  exactly when `workflow_state` is in `OWNER_ACTION_STATES`, the states
  IR-534's My Library dot counts, so the two cannot disagree.
- `history` (Record detail only): each version, when it was submitted, and
  what each party decided on it.

Nothing here carries a reviewer's name or words. A party is named by its
label; why it asked lives in the revision banner and the document-request
panel, under their own read rules.
"""

from __future__ import annotations

from typing import Iterable

from core.enums import (
    ClearanceStatus,
    DocumentRequestState,
    Office,
    Party,
    PipelineStatus,
    ResubmissionRequestState,
    ReviewDecision,
    WorkflowState,
)

#: The `workflow_state`s in which a record waits on its owner.
OWNER_ACTION_STATES = frozenset({
    WorkflowState.AWAITING_RESUBMISSION.value,
    WorkflowState.AWAITING_DOCUMENT.value,
})

_OFFICES = frozenset(str(o) for o in Office)

#: The party vocabulary as a submitter reads it. RDCO's own label, "RDCO
#: Final", names its seat for staff; the owner only needs the office.
_OWNER_PARTY_LABELS = {str(Party.RDCO): str(Party.RDCO).upper()}

#: A verdict as the owner reads it. An office clears its own question rather
#: than approving the record (`tracker._seat_rows` says the same).
_VERDICT_LABELS = {
    str(ReviewDecision.APPROVED): "Approved",
    str(ReviewDecision.DECLINED): "Revision requested",
    str(ReviewDecision.REJECTED): "Rejected",
    str(ReviewDecision.NEGATIVE_FINDING): "Negative finding",
}


def party_label(party) -> str:
    party = str(party)
    return _OWNER_PARTY_LABELS.get(party, str(Party(party).label))


def _ordered(parties: Iterable) -> list[str]:
    """Distinct parties, in the tracker's order."""
    from .tracker import TRACKER_ORDER

    present = {str(p) for p in parties}
    return [str(p) for p in TRACKER_ORDER if str(p) in present]


def _named(parties: list[str]) -> str:
    return ", ".join(party_label(p) for p in parties)


def status_line(
    *, record, workflow_state: str, holders: Iterable, revision_parties: Iterable,
    document_parties: Iterable,
) -> str:
    """Where the record is, in one sentence. `record` names terminal states."""
    if workflow_state == WorkflowState.AWAITING_RESUBMISSION:
        return f"Revision requested by {_named(_ordered(revision_parties))}: action needed"
    if workflow_state == WorkflowState.AWAITING_DOCUMENT:
        return f"Documents requested by {_named(_ordered(document_parties))}: action needed"
    if workflow_state == PipelineStatus.DRAFT:
        return "Draft: not yet submitted"
    if workflow_state in (
        WorkflowState.SUBMITTED, WorkflowState.IN_REVIEW, WorkflowState.FINAL_REVIEW,
    ):
        held = _ordered(holders)
        offices = [p for p in held if p in _OFFICES]
        if offices:
            return f"In specialist review: {_named(offices)}"
        if str(Party.RDCO) in held:
            return "With RDCO for a decision"
        if str(Party.ADVISER) in held:
            return "With your Adviser"
        return "In review"
    from .tracker import record_state_label

    return record_state_label(record, workflow_state)


def waiting_on_you(*, workflow_state: str, revision_parties: Iterable, document_parties: Iterable) -> list[dict]:
    """
    What the owner owes, one item per asking party. Empty outside
    `OWNER_ACTION_STATES`: a request on a record no longer in review waits on
    nobody.
    """
    if workflow_state not in OWNER_ACTION_STATES:
        return []
    return [
        {
            "kind": "revision", "party": p,
            "label": f"Revision requested by {party_label(p)}",
            "action_label": "Submit a new version",
        }
        for p in _ordered(revision_parties)
    ] + [
        {
            "kind": "document", "party": p,
            "label": f"Documents requested by {party_label(p)}",
            "action_label": "Upload the documents",
        }
        for p in _ordered(document_parties)
    ]


def submitter_status(
    *, record, workflow_state: str, holders: Iterable, revision_parties: Iterable,
    document_parties: Iterable,
) -> dict:
    revision_parties, document_parties = list(revision_parties), list(document_parties)
    return {
        "line": status_line(
            record=record, workflow_state=workflow_state, holders=holders,
            revision_parties=revision_parties, document_parties=document_parties,
        ),
        "waiting_on_you": waiting_on_you(
            workflow_state=workflow_state, revision_parties=revision_parties,
            document_parties=document_parties,
        ),
    }


def open_request_parties(record) -> tuple[list[str], list[str]]:
    """The parties with an open revision request, and with an open document request."""
    from apps.documents.models import DocumentRequest

    from .models import ResubmissionRequest

    revisions = ResubmissionRequest.objects.filter(
        record=record, state=ResubmissionRequestState.OPEN,
    ).values_list("party", flat=True)
    documents = DocumentRequest.objects.filter(
        record=record, state=DocumentRequestState.OPEN,
    ).values_list("party", flat=True)
    return list(revisions), list(documents)


def version_history(record) -> list[dict]:
    """
    Each version, oldest first, with each party's latest verdict on it. A
    party is shown once per version, where it first decided; a later verdict
    by the same party on the same version replaces the earlier one.
    """
    from .models import Review

    versions = list(record.versions.order_by("number"))
    decided: dict[int, dict[str, str]] = {v.pk: {} for v in versions}
    for version_id, stage, verdict in (
        Review.objects.filter(record=record, version__isnull=False)
        .order_by("created_at", "pk").values_list("version_id", "stage", "status")
    ):
        if version_id in decided:
            decided[version_id][stage] = verdict

    def verdict_label(party: str, verdict: str) -> str:
        if verdict == ReviewDecision.APPROVED and party in _OFFICES:
            return str(ClearanceStatus.CLEARED.label)
        return _VERDICT_LABELS.get(verdict, verdict)

    return [
        {
            "number": v.number,
            "cause_label": v.get_cause_display(),
            "submitted_at": v.created_at.isoformat(),
            "decisions": [
                {
                    "party": party, "label": party_label(party),
                    "verdict": verdict, "verdict_label": verdict_label(party, verdict),
                }
                for party, verdict in decided[v.pk].items()
            ],
        }
        for v in versions
    ]


def detail_status(record, *, workflow_state: str, holders: Iterable) -> dict:
    """Record detail's block: the list's, plus the version history."""
    revisions, documents = open_request_parties(record)
    return {
        **submitter_status(
            record=record, workflow_state=workflow_state, holders=holders,
            revision_parties=revisions, document_parties=documents,
        ),
        "history": version_history(record),
    }
