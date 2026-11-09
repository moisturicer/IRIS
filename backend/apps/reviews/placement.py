"""
Finding a thread's passage again in a later Version (ADR-032 §7, *Outdated
threads*; IR-876). Pure: two readings in, one place out.

- **Found:** the text appears in the new reading. The thread moves to it.
- **Changed:** it doesn't, but the comparison pairs the passage it was in with
  an edited passage. The thread is Outdated, beside the new passage.
- **Removed:** neither. The thread is Outdated, *passage removed*.

Matching is the comparison's own (`comparison.norm`, `appears_in`,
`_diff_passages`), so a thread and the Changes tab never disagree about what
changed. Moving never resolves anything: this module only says where.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.enums import ThreadPlaceOutcome

from . import comparison

FOUND = ThreadPlaceOutcome.FOUND
CHANGED = ThreadPlaceOutcome.CHANGED
REMOVED = ThreadPlaceOutcome.REMOVED


@dataclass(frozen=True)
class Place:
    outcome: str
    page: int | None = None
    #: The text at the place: the quote when found, the edited passage when changed.
    text: str = ""
    regions: list = field(default_factory=list)


def place(old: dict, new: dict, text: str) -> Place:
    """Where ``text``, a passage of reading ``old``, is in reading ``new``."""
    found = comparison.appears_in(new, text)
    if found:
        spot = found[0]
        return Place(FOUND, spot[0]["page"], text, [r for p in spot for r in p["regions"]])
    touched = _touched(old, text)
    edited = [
        change["to"] for change in comparison._diff_passages(comparison._flat(old), comparison._flat(new))
        if change["kind"] == comparison.CHANGED and _key(change["from"]) in touched
    ]
    if edited:
        return Place(CHANGED, edited[0]["page"], " ".join(p["text"] for p in edited),
                     [r for p in edited for r in p["regions"]])
    return Place(REMOVED)


def _key(ref) -> tuple:
    return (ref["section"], ref["page"], ref["text"])


def _touched(reading: dict, text: str) -> set:
    """The passages of ``reading`` that ``text`` falls in, as the comparison
    names them: matched the way `comparison.appears_in` matches."""
    wanted = comparison.norm(text).lower()
    flat = comparison._flat(reading)
    pieces = [comparison.norm(p["text"]).lower() for _, p in flat]
    whole, spans, at = " ".join(pieces), [], 0
    for piece in pieces:
        spans.append((at, at + len(piece)))
        at += len(piece) + 1
    start = whole.find(wanted) if wanted else -1
    if start == -1:
        return set()
    end = start + len(wanted)
    return {
        (key, p["page"], p["text"])
        for (key, p), (s, e) in zip(flat, spans) if s < end and e > start
    }
