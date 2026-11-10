"""
Comments on published papers (ADR-032 §7, amendment 2026-10-31; IR-690).

    GET    /records/<id>/comments/              → {"comments": [...], "count": n}
    POST   /records/<id>/comments/              {"body": str, "reply_to"?: id} → 201 comment
    PATCH  /records/<id>/comments/<comment_id>/ {"body": str}                   → comment
    DELETE /records/<id>/comments/<comment_id>/                                 → 204

**Published papers only.** The record comes from `RecordViewSet.get_object`,
so a record the caller may not read is already a 404; one they may read that
is not published answers the same 404 here, word for word. A paper that
stops being public keeps its comments, unseen until it is public again.

**Any signed-in account** writes and replies. The thread is flat and oldest
first; `reply_to` names a comment on the same paper that is not deleted.
Plain text up to 2,000 characters, line breaks kept; no response carries
HTML. The API takes JSON, so `reply_to` is a number. **Only the writer** edits (`edited_at`, no earlier wording kept) or
deletes, not the paper's owners. Posting has its own request budget.

**What a deleted comment leaves** (IR-690 build note, Hermoine Zozobrado,
2026-11-10). A deleted comment that is part of a conversation -- it has a
reply, deleted or not, or it is itself a reply -- stays as a marker with no
name and no text. Only a standalone comment with no replies disappears. The
text stays stored and no response ever carries it. `count` is the comments
not deleted.

**Notifications,** in-app only: the paper's owners on each new top-level
comment by someone else, and a writer when someone else replies to them
(IR-690 build note: owners are not told of replies). Ask IRIS never reads
comments. Reporting is IR-691, so nothing offers it yet (`can_report`).
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rest_framework.throttling import UserRateThrottle

from core.enums import PUBLICLY_VISIBLE_STATUSES, CommentDeletion

from .models import PUBLIC_COMMENT_MAX_LENGTH, PublicComment

FORMER_USER = "Former user"
#: An account with no name on file. Never its email: the page is public.
UNNAMED_USER = "IRIS user"


class CommentNotFound(Exception):
    """404: no such comment on a paper the caller may comment on."""


class CommentRefused(Exception):
    """403: the caller sees the comment but may not change it."""


class CommentError(Exception):
    """400: what was asked cannot be done."""


class _PostOnly:
    """A budget spent only by posting: reading, editing and deleting are free."""

    def allow_request(self, request, view):
        if request.method != "POST":
            return True
        return super().allow_request(request, view)


class CommentPostBurstThrottle(_PostOnly, UserRateThrottle):
    """Posting's per-minute burst (IR-999); `CommentPostThrottle` is its daily backstop."""

    scope = "public_comment_burst"


class CommentPostThrottle(_PostOnly, UserRateThrottle):
    scope = "public_comment"


def _paper(record) -> None:
    if record.pipeline_status not in PUBLICLY_VISIBLE_STATUSES:
        raise CommentNotFound


def _body(value) -> str:
    body = value.strip() if isinstance(value, str) else ""
    if not body:
        raise CommentError("Write a comment first.")
    if len(body) > PUBLIC_COMMENT_MAX_LENGTH:
        raise CommentError(f"A comment is at most {PUBLIC_COMMENT_MAX_LENGTH:,} characters.")
    return body


def _owner_ids(record) -> set:
    return set(record.owners.values_list("user_id", flat=True))


def _writer_name(comment: PublicComment) -> str:
    if comment.author is None:
        return FORMER_USER
    return comment.author.get_full_name().strip() or UNNAMED_USER


def comment_payload(comment: PublicComment, user, owners: set) -> dict:
    """One comment as `user` reads it. A deleted one is a marker: no name, no text."""
    shared = {
        "id": comment.pk,
        "created_at": comment.created_at.isoformat(),
        "reply_to": comment.reply_to_id,
        "deletion_kind": comment.deletion_kind,
        # Reporting is IR-691's; nothing is offered before it exists.
        "can_report": False,
    }
    if comment.deletion_kind:
        return {**shared, "author_name": None, "body": None, "edited_at": None,
                "is_author": False, "can_edit": False}
    return {
        **shared,
        "author_name": _writer_name(comment),
        "body": comment.body,
        "edited_at": comment.edited_at.isoformat() if comment.edited_at else None,
        "is_author": comment.author_id is not None and comment.author_id in owners,
        "can_edit": comment.author_id is not None and comment.author_id == user.pk,
    }


def _shown(comments: list) -> list:
    """Every comment the thread shows: a deleted one only while it is part of a conversation."""
    answered = {c.reply_to_id for c in comments if c.reply_to_id}
    return [c for c in comments if not c.deletion_kind or c.pk in answered or c.reply_to_id]


def thread(record, user) -> dict:
    _paper(record)
    comments = list(record.public_comments.select_related("author"))
    owners = _owner_ids(record)
    return {
        "comments": [comment_payload(c, user, owners) for c in _shown(comments)],
        "count": sum(1 for c in comments if not c.deletion_kind),
    }


def _comment(record, comment_id) -> PublicComment:
    try:
        return record.public_comments.select_for_update().get(pk=int(comment_id))
    except (TypeError, ValueError, PublicComment.DoesNotExist):
        raise CommentNotFound from None


@transaction.atomic
def post(record, user, *, body, reply_to=None) -> dict:
    _paper(record)
    text = _body(body)
    parent = None
    if reply_to not in (None, ""):
        if not isinstance(reply_to, int) or isinstance(reply_to, bool):
            raise CommentError("Reply to a comment on this paper.")
        parent = (record.public_comments.select_for_update()
                  .filter(pk=reply_to, deletion_kind__isnull=True).first())
        if parent is None:
            raise CommentError("Reply to a comment on this paper.")
    comment = PublicComment.objects.create(record=record, author=user, body=text, reply_to=parent)
    _notify(record, comment, user)
    return comment_payload(comment, user, _owner_ids(record))


def _own(record, user, comment_id) -> PublicComment:
    _paper(record)
    comment = _comment(record, comment_id)
    if comment.deletion_kind:
        raise CommentError("This comment was deleted.")
    if comment.author_id != user.pk:
        raise CommentRefused("Only the person who wrote a comment may change it.")
    return comment


@transaction.atomic
def edit(record, user, comment_id, *, body) -> dict:
    comment = _own(record, user, comment_id)
    text = _body(body)
    if text != comment.body:
        comment.body = text
        comment.edited_at = timezone.now()
        comment.save(update_fields=["body", "edited_at"])
    return comment_payload(comment, user, _owner_ids(record))


@transaction.atomic
def delete(record, user, comment_id) -> None:
    comment = _own(record, user, comment_id)
    comment.deletion_kind = CommentDeletion.WRITER
    comment.deleted_at = timezone.now()
    comment.deleted_by = user
    comment.save(update_fields=["deletion_kind", "deleted_at", "deleted_by"])


def _notify(record, comment, actor) -> None:
    from apps.notifications.services import notify_comment_replied, notify_paper_commented

    if comment.reply_to_id is None:
        transaction.on_commit(lambda: notify_paper_commented(record, comment, actor=actor))
    elif comment.reply_to.author_id not in (None, actor.pk):
        transaction.on_commit(lambda: notify_comment_replied(record, comment, actor=actor))
