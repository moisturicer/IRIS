"""
What someone taken off a paper leaves behind (IR-1226, ADR-032 §10,
*Amendment, 2026-11-18*, points 4 to 6).

A seat ends withdrawn in four ways: RDCO replaces the Adviser
(`rdco_acts.replace_adviser`), a coordinator reassigns or withdraws it
(`seats.reassign`, `seats.withdraw`), or a Decision closes it while it is open
(`decisions.decide`). Each of them:

- first **warns** what the person leaves unresolved, with counts the server
  states beside the act's offer (`unresolved`, `leaving`), so the screen never
  counts. The warning never blocks;
- then **discards their unsent drafts**, in the same transaction
  (`discard_drafts`). A draft is visible only to its writer, and without a
  seat they could never send it. A draft document thread goes with it; its
  upload stays.

Everything is counted **for the party the person is taken off**: a draft, a
thread and a request each belong to the party they were written as, so the
warning's draft count is exactly what `discard_drafts` removes, even for
someone who also reviews the paper for another party.

Their requests stay open for whoever holds the party's seat, and nothing they
sent is removed or hidden.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from django.db.models import Count, Q

from core.enums import DocumentRequestState, ResubmissionRequestState, ReviewCommentKind, ThreadState

from .models import ResubmissionRequest, ReviewComment


@dataclass
class Unresolved:
    """What one person leaves as one party: drafts go, the rest stays open."""

    drafts: int = 0
    open_threads: int = 0
    document_requests: int = 0
    revision_requests: int = 0


def unresolved(record, user, party) -> dict:
    """What `user` leaves unresolved on `record` if taken off `party`."""
    key = (record.pk, user.pk, str(party))
    return unresolved_many([key])[key]


def unresolved_many(keys) -> dict:
    """
    `unresolved` for many `(record_id, user_id, party)` keys, in three queries
    whatever their number, so a list of seats (the office console) costs the
    same for ten rows as for one.
    """
    from apps.documents.models import DocumentRequest

    keys = {(r, u, str(p)) for r, u, p in keys}
    counts = {key: Unresolved() for key in keys}
    if keys:
        records = {r for r, _, _ in keys}
        users = {u for _, u, _ in keys}

        def add(rows, user_field, *fields):
            for row in rows:
                key = (row["record_id"], row[user_field], str(row["party"]))
                if key in counts:
                    for field in fields:
                        setattr(counts[key], field, getattr(counts[key], field) + row[field])

        open_thread = Q(
            is_draft=False, reply_to__isnull=True, kind=ReviewCommentKind.THREAD, state=ThreadState.OPEN,
        )
        add(
            ReviewComment.objects.filter(record_id__in=records, author_id__in=users)
            .values("record_id", "author_id", "party")
            .annotate(drafts=Count("pk", filter=Q(is_draft=True)), open_threads=Count("pk", filter=open_thread)),
            "author_id", "drafts", "open_threads",
        )
        add(
            DocumentRequest.objects.filter(
                record_id__in=records, requested_by_id__in=users, state=DocumentRequestState.OPEN,
            ).values("record_id", "requested_by_id", "party").annotate(document_requests=Count("pk")),
            "requested_by_id", "document_requests",
        )
        add(
            ResubmissionRequest.objects.filter(
                record_id__in=records, requested_by_id__in=users, state=ResubmissionRequestState.OPEN,
            ).values("record_id", "requested_by_id", "party").annotate(revision_requests=Count("pk")),
            "requested_by_id", "revision_requests",
        )
    return {key: asdict(value) for key, value in counts.items()}


def leaving(record, user, party) -> dict:
    """`{name, unresolved}`: one person a removal would take off `record`'s `party`."""
    return {"name": user.get_full_name() or user.email, "unresolved": unresolved(record, user, party)}


def discard_drafts(record, user, party) -> int:
    """
    Delete `user`'s unsent drafts written as `party` on `record`: draft
    comments, and draft document requests (ADR-022 Amendment 9, IR-1325),
    which only their *Finish review* could have sent. Called inside each
    removal's transaction, after the seat is withdrawn. Returns how many
    comments went.
    """
    from apps.documents.models import DocumentRequest
    from core.enums import DocumentRequestState

    if user is None:
        return 0
    DocumentRequest.objects.filter(
        record=record, requested_by=user, party=str(party), state=DocumentRequestState.DRAFT,
    ).delete()
    deleted, _ = ReviewComment.objects.filter(
        record=record, author=user, party=str(party), is_draft=True,
    ).delete()
    return deleted
