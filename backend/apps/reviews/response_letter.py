"""
The response to reviewers (ADR-032 §7; IR-876, decided 2026-11-09).

Submitting a Version asks the owner to answer the open threads of the
parties that asked for the revision. IRIS assembles those answers into a
letter, shown while the owner submits (`assemble`) and **frozen** onto the
new Version when they do (`ResponseLetter`), so it records what was said
then, whatever a thread says later.

- **What it holds:** every open, sent thread of a party with an open
  Revision request -- *Must fix* first, then *Suggestion* -- with its answer,
  or none (*"No answer given"*). Drafts and resolved threads are left out.
- **Who reads it:** anyone `may_read_review` admits, whole. Each reviewer
  reads their own party's part first (`letters_payload`).
"""
from __future__ import annotations

from core.enums import ThreadSeverity
from core.permissions import may_read_review

from .models import ResponseLetter
from .threads import is_reviewer_thread, open_threads, party_label


class LetterNotFound(Exception):
    """The caller may not read this review: the same 404 as a missing record."""


def _entry(thread) -> dict:
    return {
        "thread": thread.pk,
        "party": thread.party,
        "party_label": party_label(thread.party),
        "severity": thread.severity,
        "comment": thread.body,
        "version": (thread.anchor_version or thread.version).number
        if (thread.anchor_version_id or thread.version_id) else None,
        "page": thread.anchor_page,
        "quote": thread.anchor_quote,
        "answer": thread.answer or None,
        "note": thread.answer_note,
    }


def assemble(record, requests) -> list[dict]:
    """The letter for a Version answering ``requests``, as it stands now."""
    parties = list(dict.fromkeys(str(r.party) for r in requests))
    threads = [
        t for t in open_threads(record)
        .filter(party__in=parties)
        .select_related("anchor_version", "version")
        .order_by("created_at", "pk")
        if is_reviewer_thread(t)
    ]
    rank = {ThreadSeverity.MUST_FIX: 0, ThreadSeverity.SUGGESTION: 1}
    threads.sort(key=lambda t: (parties.index(t.party), rank.get(t.severity, 2)))
    return [_entry(t) for t in threads]


def freeze(version, requests) -> ResponseLetter | None:
    """Attach the letter to ``version`` as it stands now. None when no open
    thread was asked about, so a Version answering only a request has none."""
    entries = assemble(version.record, requests)
    if not entries:
        return None
    return ResponseLetter.objects.create(version=version, entries=entries)


def letters_payload(record, user) -> list[dict]:
    """`GET /records/<id>/response-letters/`: every letter, newest first,
    each with the viewer's own party's answers first."""
    if not may_read_review(user, record):
        raise LetterNotFound
    from .comments import writer_party

    mine, _ = writer_party(record, user)
    letters = ResponseLetter.objects.filter(version__record=record).select_related("version")
    return [
        {
            "version": letter.version.number,
            "created_at": letter.created_at.isoformat(),
            # Stable: within each part, the letter keeps its own order.
            "entries": sorted(letter.entries, key=lambda e: not (mine and e["party"] == mine)),
        }
        for letter in letters.order_by("-version__number")
    ]
