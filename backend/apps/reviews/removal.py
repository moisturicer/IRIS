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

Their requests stay open for whoever holds the party's seat, and nothing they
sent is removed or hidden.
"""

from __future__ import annotations

from django.db.models import Count, Q

from core.enums import DocumentRequestState, ResubmissionRequestState, ReviewCommentKind, ThreadState
from core.permissions import may_act_on_review

from .models import ResubmissionRequest, ReviewComment


def unresolved(record, user) -> dict:
    """
    What `user` leaves unresolved on `record` if taken off it: their unsent
    drafts (discarded), and the open threads and open requests they made
    (which stay open).
    """
    return unresolved_many([(record.pk, user.pk)])[(record.pk, user.pk)]


def unresolved_many(pairs) -> dict:
    """
    `unresolved` for many `(record_id, user_id)` pairs, in three queries
    whatever their number, so a list of seats (the office console) costs the
    same for ten rows as for one.
    """
    from apps.documents.models import DocumentRequest

    pairs = set(pairs)
    counts = {pair: dict(drafts=0, open_threads=0, document_requests=0, revision_requests=0) for pair in pairs}
    if not pairs:
        return counts
    records = {r for r, _ in pairs}
    users = {u for _, u in pairs}

    def add(rows, key, *fields):
        for row in rows:
            pair = (row[key[0]], row[key[1]])
            if pair in counts:
                for field in fields:
                    counts[pair][field] += row[field]

    open_thread = Q(
        is_draft=False, reply_to__isnull=True, kind=ReviewCommentKind.THREAD, state=ThreadState.OPEN,
    )
    add(
        ReviewComment.objects.filter(record_id__in=records, author_id__in=users)
        .values("record_id", "author_id")
        .annotate(drafts=Count("pk", filter=Q(is_draft=True)), open_threads=Count("pk", filter=open_thread)),
        ("record_id", "author_id"), "drafts", "open_threads",
    )
    add(
        DocumentRequest.objects.filter(
            record_id__in=records, requested_by_id__in=users, state=DocumentRequestState.OPEN,
        ).values("record_id", "requested_by_id").annotate(document_requests=Count("pk")),
        ("record_id", "requested_by_id"), "document_requests",
    )
    add(
        ResubmissionRequest.objects.filter(
            record_id__in=records, requested_by_id__in=users, state=ResubmissionRequestState.OPEN,
        ).values("record_id", "requested_by_id").annotate(revision_requests=Count("pk")),
        ("record_id", "requested_by_id"), "revision_requests",
    )
    return counts


def leaving(record, user) -> dict:
    """`{name, unresolved}`: one person a removal would take off `record`."""
    return {"name": user.get_full_name() or user.email, "unresolved": unresolved(record, user)}


def discard_drafts(record, user) -> int:
    """
    Delete `user`'s unsent drafts on `record`, unless they still act on its
    review through another seat or as an owner. Called inside each removal's
    transaction, after the seat is withdrawn. Returns how many went.
    """
    if user is None or may_act_on_review(user, record):
        return 0
    deleted, _ = ReviewComment.objects.filter(record=record, author=user, is_draft=True).delete()
    return deleted
