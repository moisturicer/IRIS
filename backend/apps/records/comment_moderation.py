"""
RDCO and the System Admin act on Comments (ADR-032 §7, amendment 2026-10-31;
IR-691). Decided 2026-11-15 (Hermoine Zozobrado): both roles share the queue,
and either removes any comment, reported or not, from the queue or from the
paper (`can_remove`).

    GET  /moderation/comments/                    → {"comments": [...]}
    POST /moderation/comments/<comment_id>/remove/  {"reason": str} → 204
    POST /moderation/comments/<comment_id>/dismiss/                 → 204

**The queue** lists every comment with an open report, the most recently
reported first: the text as reported (each distinct wording), the text now,
its paper, the reasons with how many gave each, *Other*'s notes, and when it
was first reported. It never names who reported.

**Remove** marks the comment removed by a moderator ("[removed]"), keeps its
text unseen, closes its open reports, tells the writer in-app with the reason,
and is audited. **Dismiss** closes the open reports and leaves the comment.
Whoever acts second on a comment is told it is already handled (409), and
nothing changes. Who may act is the view's (`IsCommentModerator`).
"""

from __future__ import annotations

from collections import Counter

from django.db import transaction
from django.db.models import Max, Min
from django.utils import timezone

from core.enums import CommentDeletion, CommentReportReason, CommentReportState

from .models import PublicComment
from .public_comments import _writer_name, close_reports

#: A moderator's reason, like a comment, is plain text.
REMOVAL_REASON_MAX_LENGTH = 500


class CommentNotFound(Exception):
    """404: no such comment."""


class CommentError(Exception):
    """400: what was asked cannot be done."""


class AlreadyHandled(Exception):
    """409: someone else acted on this comment first."""


def queue() -> dict:
    """Every comment with an open report, the most recently reported first (module note)."""
    comments = (
        PublicComment.objects.filter(reports__state=CommentReportState.OPEN)
        .annotate(first_reported=Min("reports__created_at"), last_reported=Max("reports__created_at"))
        .select_related("author", "record")
        .order_by("-last_reported", "-pk")
        .distinct()
    )
    return {"comments": [_row(comment) for comment in comments]}


def _row(comment) -> dict:
    reports = list(comment.reports.filter(state=CommentReportState.OPEN).order_by("created_at", "pk"))
    reasons = Counter(r.reason for r in reports)
    order = list(CommentReportReason.values)
    return {
        "id": comment.pk,
        "record": {"id": comment.record_id, "title": comment.record.title},
        "author_name": _writer_name(comment),
        "reported_texts": list(dict.fromkeys(r.reported_text for r in reports)),
        "current_text": None if comment.deletion_kind else comment.body,
        "deletion_kind": comment.deletion_kind,
        "report_count": len(reports),
        "reasons": [{"reason": reason, "count": reasons[reason]}
                    for reason in sorted(reasons, key=lambda r: (-reasons[r], order.index(r)))],
        "notes": [r.note for r in reports if r.note],
        "first_reported_at": reports[0].created_at.isoformat(),
    }


def _locked(comment_id) -> PublicComment:
    try:
        return PublicComment.objects.select_for_update().select_related("record").get(pk=int(comment_id))
    except (TypeError, ValueError, PublicComment.DoesNotExist):
        raise CommentNotFound from None


@transaction.atomic
def remove(user, comment_id, *, reason) -> None:
    text = reason.strip() if isinstance(reason, str) else ""
    if not text:
        raise CommentError("Say why this comment is removed. The writer is told.")
    if len(text) > REMOVAL_REASON_MAX_LENGTH:
        raise CommentError(f"A reason is at most {REMOVAL_REASON_MAX_LENGTH:,} characters.")
    comment = _locked(comment_id)
    if comment.deletion_kind:
        raise AlreadyHandled("This comment was already removed or deleted.")
    now = timezone.now()
    comment.deletion_kind = CommentDeletion.MODERATOR
    comment.deleted_at = now
    comment.deleted_by = user
    comment.removal_reason = text
    comment.save(update_fields=["deletion_kind", "deleted_at", "deleted_by", "removal_reason"])
    closed = close_reports(comment, CommentReportState.REMOVED, by=user, at=now)

    from apps.audit import workflow as audit
    from apps.notifications.services import notify_comment_removed

    audit.comment_removed(comment, user, reason=text, reports_closed=closed)
    transaction.on_commit(
        lambda: notify_comment_removed(comment.record, comment, actor=user, reason=text), robust=True,
    )


@transaction.atomic
def dismiss(user, comment_id) -> None:
    comment = _locked(comment_id)
    closed = close_reports(comment, CommentReportState.DISMISSED, by=user, at=timezone.now())
    if not closed:
        raise AlreadyHandled("This comment's reports were already handled.")

    from apps.audit import workflow as audit

    audit.comment_reports_dismissed(comment, user, reports_closed=closed)
