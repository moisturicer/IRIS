"""
The review discussion: participants comment on a record under review
(ADR-032 §7, IR-419).

**Who reads.** `may_read_review` (ADR-032 §10, IR-479 Amendment): an owner,
anyone who has ever held a seat, or a member of an office holding the record
now. Anyone else is told nothing, not even that a discussion exists: the
refusal is the same 404 as a missing record (IR-153).

**Who writes.** The record's participants (`is_record_participant`, §7): its
owners and anyone who has ever held a seat. A pool member about to claim may
read the history but not write in it -- 403, since they may see it.

**On which records.** Every submitted one. A draft is not under review, so a
comment on it is refused.

**Versions.** A comment is made against the record's latest version when it
is written, and a record with no version yet gets none (spec §4.11).

**Threads are one level deep**, as on a pull request: a reply to a reply
joins the thread it is in. **An edit** is the author's alone, and stamps
`edited_at` only when it changed the body.

Public discussion is a different model and never reads these rows.
"""

from __future__ import annotations

from typing import Any, Optional

from django.utils import timezone

from apps.records.versions import latest_version
from core.enums import PipelineStatus
from core.permissions import is_record_participant, may_read_review

from .models import ReviewComment

#: Longer than any comment a reviewer writes, short enough that the timeline
#: is never asked to render a pasted manuscript.
MAX_BODY_LENGTH = 10_000


class CommentNotFound(Exception):
    """404: the record's review, or the comment, is not this viewer's to see."""


class CommentRefused(Exception):
    """403: the viewer reads the discussion but may not do this in it."""


class CommentError(Exception):
    """400: this cannot be done now, or the request is malformed."""


def comment_payload(comment: ReviewComment, user) -> dict[str, Any]:
    """
    One comment, as the API and the tracker state it to `user`. `can_edit`
    is the server's answer, so the screen offers Edit only where it is true.
    """
    return {
        "id": comment.pk,
        "author": comment.author_id,
        "author_name": comment.author.get_full_name() if comment.author else None,
        "body": comment.body,
        "version": comment.version.number if comment.version else None,
        "reply_to": comment.reply_to_id,
        "created_at": comment.created_at.isoformat(),
        "edited_at": comment.edited_at.isoformat() if comment.edited_at else None,
        "can_edit": comment.author_id is not None and comment.author_id == user.pk,
    }


def comments_payload(record, user) -> list[dict[str, Any]]:
    """Every comment on `record`, oldest first. Callers check who may read."""
    rows = ReviewComment.objects.filter(record=record).select_related("author", "version")
    return [comment_payload(c, user) for c in rows.order_by("created_at", "pk")]


def readable_comments(record, user) -> list[dict[str, Any]]:
    """`GET /records/<id>/review-comments/`."""
    if not may_read_review(user, record):
        raise CommentNotFound
    return comments_payload(record, user)


def _writer(record, user) -> None:
    if not may_read_review(user, record):
        raise CommentNotFound
    if not is_record_participant(user, record):
        raise CommentRefused(
            "Only the record's owners and its reviewers take part in the review discussion."
        )


def _body(value) -> str:
    body = value.strip() if isinstance(value, str) else ""
    if not body:
        raise CommentError("Write a comment first.")
    if len(body) > MAX_BODY_LENGTH:
        raise CommentError(f"A comment is at most {MAX_BODY_LENGTH} characters.")
    return body


def post_comment(record, user, *, body, reply_to: Optional[int] = None) -> ReviewComment:
    """`POST /records/<id>/review-comments/`: a participant comments."""
    _writer(record, user)
    if record.pipeline_status == PipelineStatus.DRAFT:
        raise CommentError("A draft is not under review. Comments open once it is submitted.")
    text = _body(body)

    parent = None
    if reply_to not in (None, ""):
        try:
            parent = ReviewComment.objects.get(record=record, pk=int(reply_to))
        except (TypeError, ValueError, ReviewComment.DoesNotExist):
            raise CommentError("That comment is not in this record's review discussion.")
        # One level deep: a reply to a reply joins its thread.
        if parent.reply_to_id is not None:
            parent = parent.reply_to

    return ReviewComment.objects.create(
        record=record, author=user, body=text,
        version=latest_version(record), reply_to=parent,
    )


def edit_comment(record, user, comment_id, *, body) -> ReviewComment:
    """`PATCH /records/<id>/review-comments/<comment_id>/`: the author edits."""
    _writer(record, user)
    comment = ReviewComment.objects.filter(record=record, pk=comment_id).first()
    if comment is None:
        raise CommentNotFound
    if comment.author_id != user.pk:
        raise CommentRefused("Only the person who wrote a comment may edit it.")
    text = _body(body)
    if text != comment.body:
        comment.body = text
        comment.edited_at = timezone.now()
        comment.save(update_fields=["body", "edited_at"])
    return comment
