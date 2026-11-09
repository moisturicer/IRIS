"""
Review threads: severity, resolving, the owner's answer, and what an open
*Must fix* blocks (ADR-032 §7, 2026-11-04 amendment; IR-874).

**A thread** is a top-level `ReviewComment` and its replies. It belongs to its
writer's **party**, not the person (`ReviewComment.party`; blank for an
owner's thread), so when a writer's Seat is withdrawn the party's current Seat
holders own it. Posting, editing and drafts are `comments.py`'s; finishing a
review is `finish_review.py`'s.

**Who does what to a published thread:**

- *Change severity*: a holder of an open Seat for the thread's party. Every
  change is recorded (`ReviewThreadEvent`) and audited. A draft's writer
  changes their own draft freely, unrecorded: nobody else has seen it.
- *Resolve* and *Reopen*: anyone who may write in the discussion
  (`is_record_participant`), except that **an owner can't resolve a thread a
  reviewer opened** (403). They answer it instead.
- *Answer*: an owner, on a reviewer's thread: **Addressed**, saying where, or
  **Declined**, with a reason. Answering never resolves; the reviewer checks
  the change and resolves it.

All of it is review content: reads go through `may_read_review`, and a
caller who may not read gets the same 404 as a missing record.

**What an open *Must fix* blocks** -- the three predicates the services call:

- `new_version_blocked_reason`: the owner's next Version, until each open
  *Must fix* of a party with an open Revision request has an answer;
- `approval_blocked_reason`: its own party's approval -- the Adviser's
  *Accept & send to RDCO* or *Accept* (a Proposal), an office's *Clear*.
  *Request revision*, *Record a finding* and *Reject* never are;
- `decision_needs_reason`: no Decision is blocked, but while any *Must fix*
  is open a Decision needs its comment, which `close_by_decision` records as
  the reason each open thread closed.

A *Suggestion* never blocks anything.
"""

from __future__ import annotations

from typing import Iterable, Optional

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit import workflow as audit
from core.enums import (
    ThreadAnswer,
    ThreadEventKind,
    ThreadSeverity,
    ThreadState,
)
from core.permissions import holds_seat, is_record_owner, is_record_participant, may_read_review

from .models import ReviewComment, ReviewThreadEvent

#: The party of an owner's thread.
OWNER = ""

#: Longest note an answer carries: a sentence or two, not a letter.
MAX_NOTE_LENGTH = 2_000

#: The note an *Addressed* answer carries when it accepts suggested wording.
ACCEPTED_WORDING = "Accepted the suggested wording."


class ThreadNotFound(Exception):
    """404: the record's review, or the thread, is not this viewer's to see."""


class ThreadRefused(Exception):
    """403: the viewer reads the thread but may not do this to it."""


class ThreadError(Exception):
    """400: this cannot be done now, or the request is malformed."""


def party_label(party: str) -> str:
    from .seats import _label

    return "The authors" if party == OWNER else _label(party)


# --- which threads ----------------------------------------------------------------

def published(record):
    """Every thread on `record` that has been sent: no drafts, no replies."""
    return ReviewComment.objects.filter(record=record, reply_to__isnull=True, is_draft=False)


def open_threads(record):
    return published(record).filter(state=ThreadState.OPEN)


def open_must_fix(record, parties: Optional[Iterable[str]] = None):
    rows = open_threads(record).filter(severity=ThreadSeverity.MUST_FIX)
    return rows.filter(party__in=list(parties)) if parties is not None else rows


def closing_threads(record, user):
    """
    The open threads a Decision by `user` would close, as `user` sees them:
    every sent one plus their own drafts, which *Finish review* sends just
    before deciding. The decision token covers exactly these.
    """
    rows = ReviewComment.objects.filter(
        record=record, reply_to__isnull=True, state=ThreadState.OPEN,
    )
    viewer = getattr(user, "pk", None)
    return rows.filter(Q(is_draft=False) | Q(author_id=viewer)).order_by("created_at", "pk")


# --- what an open Must fix blocks ------------------------------------------------

def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def approval_blocked_reason(record, party) -> Optional[str]:
    """Why `party`'s Seat holders can't approve yet, or None."""
    n = open_must_fix(record, [str(party)]).count()
    if not n:
        return None
    return (
        f"{party_label(str(party))} has {_count(n, 'open Must fix thread', 'open Must fix threads')}. "
        f"Resolve each one, or change it to Suggestion, before approving."
    )


def new_version_blocked_reason(record, requests) -> Optional[str]:
    """
    Why the owner can't submit the Version answering `requests` yet, or None:
    an open *Must fix* of a requesting party with no answer.
    """
    parties = list(dict.fromkeys(str(r.party) for r in requests))
    unanswered = list(
        open_must_fix(record, parties).filter(answer="").values_list("party", flat=True)
    )
    if not unanswered:
        return None
    from .revisions import join_labels

    by_party = [
        f"{_count(unanswered.count(p), 'thread', 'threads')} from {party_label(p)}"
        for p in parties if p in unanswered
    ]
    return (
        f"Answer each open Must fix thread first: {join_labels(by_party)}. "
        f"Mark it Addressed, saying where, or Declined, with a reason."
    )


def decision_needs_reason(record, user=None) -> bool:
    """A Decision now would close an open *Must fix*, so it needs a reason."""
    return closing_threads(record, user).filter(severity=ThreadSeverity.MUST_FIX).exists()


def token_facts(record, user) -> list:
    """What the decision token covers of the threads (`decisions.decision_token`)."""
    return list(closing_threads(record, user).values_list("pk", "severity"))


def closing_payload(record, user) -> list[dict]:
    """The threads a Decision would close, for its dialog (`decision.closes.threads`)."""
    return [
        {"id": t.pk, "party": t.party or None, "label": party_label(t.party), "severity": t.severity,
         "anchored": t.anchor_version_id is not None}
        for t in closing_threads(record, user)
    ]


def party_counts(record) -> list[dict]:
    """
    Readiness's facts: for each party with an open sent thread, its open
    *Must fix* and *Suggestion* counts and how many *Must fix* have no answer.
    """
    rows: dict[str, dict] = {}
    for party, severity, answer in open_threads(record).values_list("party", "severity", "answer"):
        row = rows.setdefault(party, {
            "party": party, "label": party_label(party),
            "must_fix": 0, "suggestions": 0, "unanswered": 0,
        })
        if severity == ThreadSeverity.MUST_FIX:
            row["must_fix"] += 1
            row["unanswered"] += 0 if answer else 1
        else:
            row["suggestions"] += 1
    return list(rows.values())


# --- who may act on a thread -------------------------------------------------------

def is_reviewer_thread(thread) -> bool:
    return thread.party != OWNER


def may_change_severity(thread, user, record) -> bool:
    if not is_reviewer_thread(thread) or thread.state != ThreadState.OPEN:
        return False
    if thread.is_draft:
        return thread.author_id == getattr(user, "pk", None)
    return holds_seat(user, record, thread.party)


def resolve_refusal(thread, user, record) -> Optional[str]:
    """Why `user` may not resolve `thread`, said as a 403, or None."""
    if not is_record_participant(user, record):
        return "Only the record's owners and its reviewers take part in the review discussion."
    if is_reviewer_thread(thread) and is_record_owner(user, record):
        return (
            "An owner can't resolve a reviewer's thread. Mark it Addressed, saying where, "
            "or Declined, with a reason, and the reviewer resolves it."
        )
    return None


def may_answer(thread, user, record) -> bool:
    return (
        is_reviewer_thread(thread) and not thread.is_draft
        and thread.state == ThreadState.OPEN and is_record_owner(user, record)
    )


# --- the acts ------------------------------------------------------------------------

def _thread(record, user, thread_id) -> ReviewComment:
    """A thread `user` may see on `record`, locked, or `ThreadNotFound`."""
    if not may_read_review(user, record):
        raise ThreadNotFound
    thread = (
        ReviewComment.objects.select_for_update()
        .filter(record=record, pk=thread_id, reply_to__isnull=True).first()
    )
    if thread is None or (thread.is_draft and thread.author_id != getattr(user, "pk", None)):
        raise ThreadNotFound
    return thread


def _in_review(record):
    from .routing import is_in_review

    if not is_in_review(record):
        raise ThreadError("This record is not in review.")


def _event(thread, actor, kind, old="", new=""):
    ReviewThreadEvent.objects.create(
        thread=thread, actor=actor, kind=kind, old_value=old or "", new_value=new or "",
    )


@transaction.atomic
def change_severity(record, user, thread_id, severity) -> ReviewComment:
    """`POST .../review-comments/<id>/severity/`: the thread's party changes it."""
    thread = _thread(record, user, thread_id)
    if not is_reviewer_thread(thread):
        raise ThreadError("An owner's thread carries no severity.")
    if severity not in ThreadSeverity.values:
        raise ThreadError("Choose Must fix or Suggestion.")
    if not may_change_severity(thread, user, record):
        if thread.state != ThreadState.OPEN:
            raise ThreadError("Reopen the thread to change its severity.")
        raise ThreadRefused(
            f"Only a reviewer holding {party_label(thread.party)}'s review may change its severity."
        )
    _in_review(record)
    previous = thread.severity
    if previous == severity:
        return thread
    thread.severity = severity
    thread.save(update_fields=["severity"])
    if not thread.is_draft:
        _event(thread, user, ThreadEventKind.SEVERITY_CHANGED, previous, severity)
        audit.review_thread_severity_changed(thread, user, previous=previous)
    return thread


@transaction.atomic
def resolve(record, user, thread_id) -> ReviewComment:
    """`POST .../review-comments/<id>/resolve/`."""
    thread = _thread(record, user, thread_id)
    refusal = resolve_refusal(thread, user, record)
    if refusal:
        raise ThreadRefused(refusal)
    if thread.is_draft:
        raise ThreadError("Finish your review to send this thread first.")
    _in_review(record)
    if thread.state != ThreadState.OPEN:
        raise ThreadError("Only an open thread can be resolved.")
    thread.state = ThreadState.RESOLVED
    thread.resolved_by = user
    thread.resolved_at = timezone.now()
    thread.save(update_fields=["state", "resolved_by", "resolved_at"])
    _event(thread, user, ThreadEventKind.RESOLVED)
    audit.review_thread_resolved(thread, user)
    return thread


@transaction.atomic
def reopen(record, user, thread_id) -> ReviewComment:
    """`POST .../review-comments/<id>/reopen/`: any participant reopens a resolved thread."""
    thread = _thread(record, user, thread_id)
    if not is_record_participant(user, record):
        raise ThreadRefused(
            "Only the record's owners and its reviewers take part in the review discussion."
        )
    _in_review(record)
    if thread.state != ThreadState.RESOLVED:
        raise ThreadError("Only a resolved thread can be reopened.")
    thread.state = ThreadState.OPEN
    thread.resolved_by = None
    thread.resolved_at = None
    thread.save(update_fields=["state", "resolved_by", "resolved_at"])
    _event(thread, user, ThreadEventKind.REOPENED)
    audit.review_thread_reopened(thread, user)
    return thread


@transaction.atomic
def answer(record, user, thread_id, *, kind, note) -> ReviewComment:
    """
    `POST .../review-comments/<id>/answer/` `{"answer": "addressed" | "declined", "note": str}`:
    an owner answers a reviewer's thread. Answering again replaces the answer,
    and each answer is recorded.
    """
    thread = _thread(record, user, thread_id)
    if not is_record_owner(user, record):
        raise ThreadRefused("Only an owner of this record answers a reviewer's thread.")
    if not is_reviewer_thread(thread):
        raise ThreadError("Your own thread needs no answer. Resolve it when it's settled.")
    _in_review(record)
    if thread.state != ThreadState.OPEN:
        raise ThreadError("Only an open thread can be answered.")
    if kind not in ThreadAnswer.values:
        raise ThreadError("Mark the thread Addressed or Declined.")
    note = note.strip() if isinstance(note, str) else ""
    if not note and kind == ThreadAnswer.ADDRESSED and thread.suggestion:
        # Accepting the suggested wording is the Addressed answer (IR-876):
        # a promise, since IRIS can't edit the PDF.
        note = ACCEPTED_WORDING
    if not note:
        raise ThreadError(
            "Say where you addressed it." if kind == ThreadAnswer.ADDRESSED
            else "Say why you're declining it. The reviewer reads it as written."
        )
    if len(note) > MAX_NOTE_LENGTH:
        raise ThreadError(f"An answer is at most {MAX_NOTE_LENGTH} characters.")
    previous = thread.answer
    thread.answer = kind
    thread.answer_note = note
    thread.answered_by = user
    thread.answered_at = timezone.now()
    thread.save(update_fields=["answer", "answer_note", "answered_by", "answered_at"])
    _event(thread, user, ThreadEventKind.ANSWERED, previous, kind)
    audit.review_thread_answered(thread, user)
    return thread


def close_by_decision(record, actor, decision, *, reason) -> list[int]:
    """
    A Decision ends the review: every open thread its dialog listed closes,
    naming the Decision and its reason (ADR-032 §7) -- exactly
    `closing_threads(record, actor)`, which the token, `reason_required` and
    `closes.threads` read. The decider's own drafts are among them, so they
    are sent as they close: the dialog showed them as closing. Called inside
    `decisions.decide`'s transaction. Other people's drafts stay drafts, seen
    by their writer only.
    """
    rows = list(closing_threads(record, actor).select_for_update())
    if not rows:
        return []
    now = timezone.now()
    ReviewComment.objects.filter(pk__in=[t.pk for t in rows]).update(
        state=ThreadState.CLOSED, closed_by_decision=decision, closed_reason=reason,
        is_draft=False,
    )
    ReviewThreadEvent.objects.bulk_create([
        ReviewThreadEvent(thread=t, actor=actor, kind=ThreadEventKind.CLOSED_BY_DECISION, created_at=now)
        for t in rows
    ])
    audit.review_threads_closed(
        record, actor, decision=decision, threads=[t.pk for t in rows],
        must_fix=sum(1 for t in rows if t.severity == ThreadSeverity.MUST_FIX),
    )
    return [t.pk for t in rows]

