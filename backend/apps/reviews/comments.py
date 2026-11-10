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

**A top-level comment is a thread** (ADR-032 §7, 2026-11-04; IR-874). It
belongs to its writer's party (blank for an owner), may carry an anchor to a
passage of one Version, and -- a reviewer's only -- a severity, *Suggestion*
unless the writer chose *Must fix*. **A reviewer holding an open Seat writes
drafts**, seen by nobody else until *Finish review* sends them
(`finish_review.py`); their writer edits or deletes them. Owners' threads,
former reviewers' threads and every reply post at once, and a reply to a
draft is refused. Resolving, answering and severity changes are
`threads.py`'s.

Public discussion is a different model and never reads these rows.
"""

from __future__ import annotations

from typing import Any, Optional

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.records.versions import latest_version
from core.enums import (
    PipelineStatus, ReviewTextState, ThreadAnswer, ThreadPlaceOutcome, ThreadSeverity, ThreadState,
)
from core.permissions import holds_seat, is_record_owner, is_record_participant, may_read_review

from . import mentions, threads
from .models import ReviewComment

#: Longer than any comment a reviewer writes, short enough that the timeline
#: is never asked to render a pasted manuscript.
MAX_BODY_LENGTH = 10_000

#: Bounds on an anchor: a passage, not a page; a few words either side.
MAX_QUOTE_LENGTH = 2_000
MAX_CONTEXT_LENGTH = 500
MAX_REGIONS = 50


class CommentNotFound(Exception):
    """404: the record's review, or the comment, is not this viewer's to see."""


class CommentRefused(Exception):
    """403: the viewer reads the discussion but may not do this in it."""


class CommentError(Exception):
    """400: this cannot be done now, or the request is malformed."""


# --- what a viewer is told -------------------------------------------------------------

def _name(user) -> Optional[str]:
    return (user.get_full_name() or user.email) if user else None


def _anchor_payload(comment) -> Optional[dict]:
    if comment.anchor_version_id is None:
        return None
    return {
        "version": comment.anchor_version.number,
        "page": comment.anchor_page,
        "quote": comment.anchor_quote,
        "prefix": comment.anchor_prefix,
        "suffix": comment.anchor_suffix,
        "regions": comment.anchor_regions,
    }


def _places(comment) -> list:
    """The thread's places, oldest Version first (`ThreadPlace`, IR-876)."""
    return sorted(comment.places.all(), key=lambda p: p.version.number)


def _place_payload(comment) -> Optional[dict]:
    """Where the passage is in the newest Version it was looked for in."""
    places = _places(comment)
    if not places:
        return None
    place = places[-1]
    return {
        "version": place.version.number, "outcome": place.outcome, "page": place.page,
        "text": place.text, "regions": place.regions, "suggestion_page": place.suggestion_page,
    }


def _wording_check(comment) -> Optional[dict]:
    """Whether accepted wording is in the first Version placed after it was
    accepted: its page there, or None for the page when it isn't (IR-876).
    None until such a Version exists, so an earlier Version is never read
    as the answer to it."""
    if not comment.suggestion or comment.answer != ThreadAnswer.ADDRESSED or not comment.answered_at:
        return None
    after = next((p for p in _places(comment) if p.placed_at > comment.answered_at), None)
    return {"version": after.version.number, "page": after.suggestion_page} if after else None


def _outdated_since(comment) -> Optional[int]:
    """The Version from which the thread is Outdated: its first place that
    wasn't found. Outdated lasts until the thread is resolved (IR-876)."""
    first = next((p for p in _places(comment) if p.outcome != ThreadPlaceOutcome.FOUND), None)
    return first.version.number if first else None


def _not_followed(comment, viewer) -> Optional[dict]:
    """Why an open thread's passage hasn't been followed into the next Version,
    or None (IR-1009). Following needs both Versions' review text (IR-876), so
    a missing one is named; otherwise placing is still to come. A removed
    passage is followed no further, so it needs no note."""
    if comment.is_draft or comment.state != ThreadState.OPEN or not comment.anchor_version_id:
        return None
    if not comment.anchor_quote.strip():
        return None
    places = _places(comment)
    if places and places[-1].outcome == ThreadPlaceOutcome.REMOVED:
        return None
    start = places[-1].version.number if places else comment.anchor_version.number
    later = [v for v in viewer.versions if v.number > start]
    if not later:
        return None
    nxt = later[0]
    for version in [v for v in viewer.versions if v.number == start] + [nxt]:
        state = version.review_text.state if version.review_text else None
        if state == ReviewTextState.NO_TEXT:
            why = f"no text for v{version.number}"
        elif state == ReviewTextState.NOT_KEPT:
            why = f"v{version.number}'s text was not kept"
        else:
            continue
        return {"version": nxt.number, "message": f"Can't follow this passage into v{nxt.number}: {why}."}
    return {"version": nxt.number, "message": f"Looking for this passage in v{nxt.number}."}


class _Viewer:
    """What `user` may do here, read once per payload rather than per comment."""

    def __init__(self, record, user):
        from .routing import is_in_review

        self.user = user
        self.pk = getattr(user, "pk", None)
        self.record = record
        self.owner = is_record_owner(user, record)
        self.participant = is_record_participant(user, record)
        self.in_review = is_in_review(record)
        self._seats: dict[str, bool] = {}
        self._versions: Optional[list] = None

    @property
    def versions(self) -> list:
        """The record's Versions with their review texts, oldest first, read once."""
        if self._versions is None:
            from apps.records.models import RecordVersion

            self._versions = list(RecordVersion.objects.filter(record=self.record)
                                  .select_related("review_text").order_by("number"))
        return self._versions

    def holds(self, party) -> bool:
        if party not in self._seats:
            self._seats[party] = holds_seat(self.user, self.record, party)
        return self._seats[party]


def comment_payload(comment: ReviewComment, user, viewer: Optional[_Viewer] = None) -> dict[str, Any]:
    """
    One comment, as the API and the tracker state it to `user`. Every `can_*`
    is the server's answer, so the screen offers an act only where it is true
    (`threads.py` holds the same rules for the acts). A reply carries the
    thread fields empty.
    """
    viewer = viewer or _Viewer(comment.record, user)
    mine = comment.author_id is not None and comment.author_id == viewer.pk
    top = comment.reply_to_id is None
    reviewer_thread = top and threads.is_reviewer_thread(comment)
    live = top and viewer.in_review and comment.state == ThreadState.OPEN
    sent = top and not comment.is_draft
    return {
        "id": comment.pk,
        "author": comment.author_id,
        "author_name": comment.author.get_full_name() if comment.author else None,
        "body": comment.body,
        "version": comment.version.number if comment.version else None,
        "reply_to": comment.reply_to_id,
        "created_at": comment.created_at.isoformat(),
        "edited_at": comment.edited_at.isoformat() if comment.edited_at else None,
        "can_edit": mine,
        # The people it mentions (IR-877).
        "mentions": mentions.payload(comment),
        # The thread (ADR-032 §7, IR-874).
        "party": (comment.party or None) if top else None,
        "party_label": threads.party_label(comment.party) if top else None,
        "severity": comment.severity if top else None,
        "is_draft": comment.is_draft,
        "round": comment.round_id,
        "anchor": _anchor_payload(comment) if top else None,
        # Its suggested wording, where its passage is now, and whether it is
        # Outdated (IR-876).
        "suggestion": comment.suggestion if top else "",
        "place": _place_payload(comment) if top else None,
        "outdated_since": _outdated_since(comment) if top else None,
        "wording_check": _wording_check(comment) if top else None,
        "not_followed": _not_followed(comment, viewer) if top else None,
        "state": comment.state if top else None,
        "resolved_by": _name(comment.resolved_by) if top and comment.state == ThreadState.RESOLVED else None,
        "resolved_at": comment.resolved_at.isoformat() if top and comment.resolved_at else None,
        "closed_by_decision": comment.closed_by_decision_id if top else None,
        "closed_reason": comment.closed_reason if top and comment.closed_by_decision_id else None,
        "answer": {
            "kind": comment.answer, "note": comment.answer_note,
            "by": _name(comment.answered_by),
            "at": comment.answered_at.isoformat() if comment.answered_at else None,
        } if top and comment.answer else None,
        "events": [
            {"kind": e.kind, "actor_name": _name(e.actor), "from": e.old_value or None,
             "to": e.new_value or None, "at": e.created_at.isoformat()}
            for e in comment.events.all()
        ] if sent else [],
        "can_delete": mine and comment.is_draft,
        "can_change_severity": live and reviewer_thread and (
            mine if comment.is_draft else viewer.holds(comment.party)
        ),
        "can_resolve": live and sent and viewer.participant and not (reviewer_thread and viewer.owner),
        "can_reopen": sent and viewer.in_review and comment.state == ThreadState.RESOLVED
        and viewer.participant,
        "can_answer": live and sent and reviewer_thread and viewer.owner,
    }


def _visible(record, user):
    """Every comment `user` may see: all sent ones, and their own drafts."""
    return ReviewComment.objects.filter(record=record).filter(
        Q(is_draft=False) | Q(author_id=getattr(user, "pk", None))
    )


def comments_payload(record, user) -> list[dict[str, Any]]:
    """
    Every comment on `record` `user` may see, oldest first: another person's
    draft is never listed. Callers check who may read at all.
    """
    rows = (
        _visible(record, user)
        .select_related("author", "version", "anchor_version", "resolved_by", "answered_by", "record")
        .prefetch_related("events__actor", "places__version", "mentions__user")
    )
    viewer = _Viewer(record, user)
    return [comment_payload(c, user, viewer) for c in rows.order_by("created_at", "pk")]


def readable_comments(record, user) -> list[dict[str, Any]]:
    """`GET /records/<id>/review-comments/`."""
    if not may_read_review(user, record):
        raise CommentNotFound
    return comments_payload(record, user)


# --- writing -----------------------------------------------------------------------------

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


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _anchor(record, value) -> dict:
    """An anchor's model fields, validated, or `CommentError`."""
    if not isinstance(value, dict):
        raise CommentError("An anchor names a Version, a page and the quoted text.")
    number, page = value.get("version"), value.get("page")
    if not _is_int(number):
        raise CommentError("Say which Version the passage is in.")
    version = record.versions.filter(number=number).first()
    if version is None:
        raise CommentError(f"This record has no v{number}.")
    if not _is_int(page) or page < 1:
        raise CommentError("Say which page the passage is on.")
    quote = value.get("quote")
    quote = quote.strip() if isinstance(quote, str) else ""
    if not quote:
        raise CommentError("Quote the passage you're commenting on.")
    if len(quote) > MAX_QUOTE_LENGTH:
        raise CommentError(f"A quoted passage is at most {MAX_QUOTE_LENGTH} characters.")
    context = {}
    for key in ("prefix", "suffix"):
        text = value.get(key, "")
        if not isinstance(text, str) or len(text) > MAX_CONTEXT_LENGTH:
            raise CommentError(
                f"The text around a passage is at most {MAX_CONTEXT_LENGTH} characters."
            )
        context[key] = text
    return {
        "anchor_version": version, "anchor_page": page, "anchor_quote": quote,
        "anchor_prefix": context["prefix"], "anchor_suffix": context["suffix"],
        "anchor_regions": _regions(value.get("regions", [])),
    }


def _regions(value) -> list[dict]:
    """ADR-031's page-fraction rectangles, `{page, left, top, right, bottom}`, each 0-1."""
    if not isinstance(value, list) or len(value) > MAX_REGIONS:
        raise CommentError(f"A passage has at most {MAX_REGIONS} regions.")
    regions = []
    for region in value:
        try:
            page = region["page"]
            box = [float(region[k]) for k in ("left", "top", "right", "bottom")]
        except (TypeError, KeyError, ValueError):
            raise CommentError("Each region names its page and its left, top, right and bottom.")
        left, top, right, bottom = box
        if (not _is_int(page) or page < 1 or not all(0.0 <= v <= 1.0 for v in box)
                or left >= right or top >= bottom):
            raise CommentError("A region is a rectangle on its page, measured in fractions of it.")
        regions.append({"page": page, "left": left, "top": top, "right": right, "bottom": bottom})
    return regions


def writer_party(record, user) -> tuple[str, bool]:
    """
    The party `user` writes a thread as, and whether they hold an open Seat
    for it -- which makes their thread a draft. An owner writes as the
    authors; a reviewer as the party of their open Seat, else of their latest.
    """
    from .models import ReviewerSeat
    from .revisions import _open_seat

    if is_record_owner(user, record):
        return threads.OWNER, False
    seat = _open_seat(record, user)
    if seat is not None:
        return str(seat.assignment.party), True
    last = (
        ReviewerSeat.objects.select_related("assignment")
        .filter(assignment__record=record, reviewer=user)
        .order_by("-assigned_at", "-pk").first()
    )
    return (str(last.assignment.party) if last else threads.OWNER), False


def _suggestion(value) -> str:
    """Suggested wording, validated, or `CommentError`."""
    if value in (None, ""):
        return ""
    if not isinstance(value, str) or not value.strip():
        raise CommentError("Suggested wording is the text you'd put in the passage's place.")
    if len(value) > MAX_QUOTE_LENGTH:
        raise CommentError(f"Suggested wording is at most {MAX_QUOTE_LENGTH} characters.")
    return value.strip()


def _mentioned(record, value, comment=None) -> Optional[list]:
    """The people `value` mentions, or None when the request leaves them out."""
    if value is None:
        return None
    try:
        return mentions.people(record, value, comment)
    except mentions.MentionError as exc:
        raise CommentError(str(exc)) from None


def _with_mentions(comment, user, people) -> ReviewComment:
    if people is not None:
        mentions.replace(comment, people)
        mentions.tell_now(comment, user)
    return comment


def mentionable(record, user) -> list[dict[str, Any]]:
    """`GET /records/<id>/review-mentionable/`: whom a writer may mention, but themselves."""
    _writer(record, user)
    return [{"id": u.pk, "name": u.get_full_name()}
            for u in mentions.candidates(record) if u.pk != user.pk]


@transaction.atomic
def post_comment(record, user, *, body, reply_to: Optional[int] = None,
                 severity=None, anchor=None, suggestion=None, mentioned=None) -> ReviewComment:
    """`POST /records/<id>/review-comments/`: a participant comments."""
    _writer(record, user)
    if record.pipeline_status == PipelineStatus.DRAFT:
        raise CommentError("A draft is not under review. Comments open once it is submitted.")
    text = _body(body)
    people = _mentioned(record, mentioned)

    if reply_to not in (None, ""):
        try:
            parent = ReviewComment.objects.get(record=record, pk=int(reply_to))
        except (TypeError, ValueError, ReviewComment.DoesNotExist):
            raise CommentError("That comment is not in this record's review discussion.")
        # One level deep: a reply to a reply joins its thread.
        if parent.reply_to_id is not None:
            parent = parent.reply_to
        if parent.is_draft:
            if parent.author_id != user.pk:
                # Someone else's draft does not exist, as far as this caller knows.
                raise CommentError("That comment is not in this record's review discussion.")
            raise CommentError("Finish your review to send this thread before replying to it.")
        if severity not in (None, "") or anchor is not None or suggestion not in (None, ""):
            raise CommentError(
                "A reply belongs to its thread: it has no severity, anchor or suggested wording."
            )
        # Replies post immediately and are never held (ADR-032 §7).
        return _with_mentions(ReviewComment.objects.create(
            record=record, author=user, body=text,
            version=latest_version(record), reply_to=parent,
        ), user, people)

    party, seated = writer_party(record, user)
    wording = _suggestion(suggestion)
    if wording and anchor is None:
        raise CommentError("Suggest wording on a passage: select the text it would replace.")
    if party == threads.OWNER:
        if severity not in (None, ""):
            raise CommentError("An owner's thread carries no severity.")
        if wording:
            raise CommentError("Only a reviewer suggests wording.")
        severity = None
    else:
        severity = severity or ThreadSeverity.SUGGESTION
        if severity not in ThreadSeverity.values:
            raise CommentError("Choose Must fix or Suggestion.")
    return _with_mentions(ReviewComment.objects.create(
        record=record, author=user, body=text, version=latest_version(record),
        party=party, severity=severity, is_draft=seated, suggestion=wording,
        **(_anchor(record, anchor) if anchor is not None else {}),
    ), user, people)


def _own(record, user, comment_id) -> ReviewComment:
    """`user`'s own comment `comment_id`, or the refusal its author check gives."""
    _writer(record, user)
    comment = _visible(record, user).filter(pk=comment_id).first()
    if comment is None:
        raise CommentNotFound
    if comment.author_id != user.pk:
        raise CommentRefused("Only the person who wrote a comment may edit it.")
    return comment


@transaction.atomic
def edit_comment(record, user, comment_id, *, body=None, suggestion=None,
                 mentioned=None) -> ReviewComment:
    """`PATCH /records/<id>/review-comments/<comment_id>/`: the author edits
    the body, a draft's suggested wording, or whom it mentions (IR-877; a
    change of mentions alone stamps no `edited_at`). Sent wording is fixed
    (IR-876), so the owner always answers the wording they read."""
    comment = _own(record, user, comment_id)
    people = _mentioned(record, mentioned, comment)
    fields = []
    if suggestion is not None:
        if not comment.is_draft:
            raise CommentError("Suggested wording is fixed once it's sent. Reply to change it.")
        if comment.anchor_version_id is None:
            raise CommentError("Suggest wording on a passage: select the text it would replace.")
        wording = _suggestion(suggestion)
        if wording != comment.suggestion:
            comment.suggestion = wording
            fields.append("suggestion")
    if body is not None or suggestion is None:
        text = _body(body)
        if text != comment.body:
            comment.body = text
            comment.edited_at = timezone.now()
            fields += ["body", "edited_at"]
    if fields:
        comment.save(update_fields=fields)
    return _with_mentions(comment, user, people)


def delete_draft(record, user, comment_id) -> None:
    """`DELETE /records/<id>/review-comments/<comment_id>/`: a writer drops their own draft."""
    comment = _own(record, user, comment_id)
    if not comment.is_draft:
        raise CommentError("A sent comment stays in the discussion. Edit it instead.")
    comment.delete()
