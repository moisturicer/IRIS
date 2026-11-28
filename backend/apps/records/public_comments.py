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
comments.

**Reports** (IR-691). Any signed-in reader reports someone else's comment, once:

    POST   /records/<id>/comments/<comment_id>/reports/ {"reason": str, "note"?: str} → 204

A repeat answers 204 and stores nothing. *Other* needs a note. The report keeps
the comment's text as it was; RDCO hears of a comment's first open report, and
nobody else ever learns of one. Reporting spends the posting budget (decision
2026-11-15). The writer deleting their comment closes its open reports; an
edit changes nothing (decision 2026-11-15). Removing and dismissing are
`apps.records.comment_moderation`'s; `can_remove` offers removal to RDCO and
the System Admin on every comment still standing.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rest_framework.throttling import UserRateThrottle

from core.enums import PUBLICLY_VISIBLE_STATUSES, CommentDeletion, CommentReportReason, CommentReportState
from core.permissions import is_comment_moderator

from .models import COMMENT_REPORT_NOTE_MAX_LENGTH, PUBLIC_COMMENT_MAX_LENGTH, CommentReport, PublicComment

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
    """A budget spent only by posting and reporting: reading, editing and deleting are free."""

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


def writer_name(comment: PublicComment) -> str:
    if comment.author is None:
        return FORMER_USER
    return comment.author.get_full_name().strip() or UNNAMED_USER


def comment_payload(comment: PublicComment, user, owners: set, reported: frozenset = frozenset()) -> dict:
    """
    One comment as `user` reads it. A deleted one is a marker: no name, no text.
    `reported` holds the ids of the comments `user` has reported, once each.
    """
    shared = {
        "id": comment.pk,
        "created_at": comment.created_at.isoformat(),
        "reply_to": comment.reply_to_id,
        "deletion_kind": comment.deletion_kind,
    }
    if comment.deletion_kind:
        return {**shared, "author_name": None, "body": None, "edited_at": None,
                "is_author": False, "can_edit": False, "can_report": False, "can_remove": False}
    mine = comment.author_id is not None and comment.author_id == user.pk
    return {
        **shared,
        "author_name": writer_name(comment),
        "body": comment.body,
        "edited_at": comment.edited_at.isoformat() if comment.edited_at else None,
        "is_author": comment.author_id is not None and comment.author_id in owners,
        "can_edit": mine,
        "can_report": not mine and comment.pk not in reported,
        "can_remove": is_comment_moderator(user),
    }


def _shown(comments: list) -> list:
    """Every comment the thread shows: a deleted one only while it is part of a conversation."""
    answered = {c.reply_to_id for c in comments if c.reply_to_id}
    return [c for c in comments if not c.deletion_kind or c.pk in answered or c.reply_to_id]


def thread(record, user) -> dict:
    _paper(record)
    comments = list(record.public_comments.select_related("author"))
    owners = _owner_ids(record)
    reported = frozenset(
        CommentReport.objects.filter(reporter_id=user.pk, comment__record=record).values_list("comment_id", flat=True)
    )
    return {
        "comments": [comment_payload(c, user, owners, reported) for c in _shown(comments)],
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
    # Nothing is left to judge (decision 2026-11-15).
    close_reports(comment, CommentReportState.WRITER_DELETED, by=user, at=comment.deleted_at)


def close_reports(comment, state, *, by, at) -> int:
    """Close `comment`'s open reports as `state`; how many closed."""
    closed = comment.reports.filter(state=CommentReportState.OPEN).update(
        state=state, resolved_by=by, resolved_at=at,
    )
    if closed:
        # A bulk update sends no signal, so the queue is told here (IR-1350).
        from apps.live.signals import comment_reports_changed

        comment_reports_changed()
    return closed


def _reason(reason, note) -> tuple[str, str]:
    if reason not in CommentReportReason.values:
        raise CommentError("Choose a reason for reporting this comment.")
    text = note.strip() if isinstance(note, str) else ""
    if reason == CommentReportReason.OTHER and not text:
        raise CommentError("Say what is wrong with this comment.")
    if len(text) > COMMENT_REPORT_NOTE_MAX_LENGTH:
        raise CommentError(f"A note is at most {COMMENT_REPORT_NOTE_MAX_LENGTH:,} characters.")
    return reason, text if reason == CommentReportReason.OTHER else ""


@transaction.atomic
def report(record, user, comment_id, *, reason, note=None) -> None:
    """`user` reports someone else's comment (module note). Nothing to answer with."""
    _paper(record)
    comment = _comment(record, comment_id)
    if comment.deletion_kind:
        raise CommentError("This comment was deleted.")
    if comment.author_id == user.pk:
        raise CommentRefused("You can't report your own comment.")
    reason, note = _reason(reason, note)
    if comment.reports.filter(reporter=user).exists():
        return
    waiting = comment.reports.filter(state=CommentReportState.OPEN).exists()
    CommentReport.objects.create(
        comment=comment, reporter=user, reason=reason, note=note, reported_text=comment.body,
    )
    if not waiting:
        from apps.notifications.services import notify_comment_reported

        transaction.on_commit(lambda: notify_comment_reported(record, comment), robust=True)


def _notify(record, comment, actor) -> None:
    from apps.notifications.services import notify_comment_replied, notify_paper_commented

    if comment.reply_to_id is None:
        transaction.on_commit(lambda: notify_paper_commented(record, comment, actor=actor))
    elif comment.reply_to.author_id not in (None, actor.pk):
        transaction.on_commit(lambda: notify_comment_replied(record, comment, actor=actor))
