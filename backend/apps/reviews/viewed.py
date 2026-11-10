"""
Viewed marks (ADR-032 §7 Conveniences and its IR-877 build notes; ADR-058 §3
as amended, point 7).

    POST /records/<id>/versions/compare/viewed/
    {"from": n, "to": m, "side": "from" | "to", "key": str, "viewed": bool}
    → {"viewed": bool}

A person ticks a section of the comparison they are looking at. The section
is found in the **same two readings** that comparison uses (`readings.pair`),
so a mark is always made on the text the person saw, and it stores that
reading, its Version, and the section's `key` and `text_hash`. A section is
marked on the side it has in the later Version, or on the earlier side when
the later Version removed it.

**A mark follows its text** (build note 1). The comparison shows a section
as Viewed when this person marked a section with its `text_hash` on this
record, whichever Version or reading it is in (`Marks`; an empty section is
matched by its key as well).
So an unchanged section stays Viewed into later Versions, and one a later
Version changes reads not viewed. Unticking removes every mark of that text,
or another mark of the same text would keep it ticked.

**Private and decides nothing.** Only the caller's own marks are read or
written; anyone `may_read_review` refuses gets the 404 a missing paper gets
(the view checks first). No reader or reading is ever named in a response.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import IntegrityError, transaction

from apps.records.review_text import readings

from . import comparison, version_comparison
from .models import ViewedMark

FROM, TO = "from", "to"


class ViewedError(ValueError):
    """400: the request names no section of a comparison that can be marked."""


def identity(*, key: str, text_hash: str, empty: bool) -> tuple:
    """What a mark is matched by: a section's `text_hash`, and also its `key`
    when it has no text of its own (a chapter heading before its first
    subsection), whose hash is the hash of nothing that every such section
    shares. The one rule both reading and unticking a mark follow."""
    return (text_hash, key if empty else None)


class Marks:
    """What `user` has marked viewed on a record, read once per comparison."""

    def __init__(self, record, user):
        rows = ViewedMark.objects.filter(record=record, user=user).values_list("text_hash", "section_key")
        self.ids = {(text_hash, k) for text_hash, key in rows for k in (key, None)}

    def has(self, **section) -> bool:
        return identity(**section) in self.ids


def mark_side(section: dict) -> str:
    """The side a compared section is marked on: the later one unless removed."""
    return TO if section[TO] else FROM


def annotate(result: dict, compared: tuple, record, user) -> None:
    """Give each compared section `viewed`, for `user` alone."""
    marks = Marks(record, user)
    by_key = {side: {s["key"]: s for s in reading["sections"]}
              for side, reading in zip((FROM, TO), compared)}
    for section in result["sections"]:
        side = mark_side(section)
        stored = by_key[side][section[side]["key"]]
        section["viewed"] = marks.has(key=stored["key"], text_hash=stored["text_hash"],
                                      empty=not stored["passages"])


@dataclass(frozen=True)
class MarkRequest:
    old_number: object
    new_number: object
    side: str
    key: str
    viewed: bool

    @classmethod
    def read(cls, data) -> "MarkRequest":
        if not isinstance(data, dict):
            raise ViewedError("Say which section to mark.")
        side, key, viewed = data.get("side"), data.get("key"), data.get("viewed")
        if side not in (FROM, TO):
            raise ViewedError("`side` is `from` or `to`.")
        if not isinstance(key, str) or not key:
            raise ViewedError("Say which section to mark.")
        if not isinstance(viewed, bool):
            raise ViewedError("`viewed` is true or false.")
        if data.get("from") is None or data.get("to") is None:
            raise ViewedError("Give both `from` and `to`.")
        return cls(data["from"], data["to"], side, key, viewed)


def set_viewed(record, user, data) -> bool:
    """Mark or unmark one section of a comparison for `user`. Returns the new state."""
    asked = MarkRequest.read(data)
    try:
        old, new = version_comparison.choose(record, user, asked.old_number, asked.new_number)
    except version_comparison.BadPair as exc:
        raise ViewedError(str(exc)) from None
    pair = readings.pair(old, new)
    if pair.state != readings.READY:
        raise ViewedError("This comparison isn't ready, so nothing in it can be marked yet.")
    compared = version_comparison.as_reading(pair.old), version_comparison.as_reading(pair.new)
    if comparison.by_page(*compared):
        raise ViewedError("This comparison is listed by page, so it has no sections to mark.")
    # The section as this comparison shows it, so it is marked on the side the
    # comparison reads it from (`mark_side`), never one the request chose.
    shown = next((s for s in comparison.compare(*compared)["sections"]
                  if s[asked.side] and s[asked.side]["key"] == asked.key), None)
    if shown is None or mark_side(shown) != asked.side:
        raise ViewedError("That section isn't in this comparison.")
    version, reading = (old, pair.old) if asked.side == FROM else (new, pair.new)
    section = reading.sections.get(key=asked.key)
    text_hash, key = identity(key=section.key, text_hash=section.text_hash, empty=not section.passages)

    if not asked.viewed:
        same = ViewedMark.objects.filter(record=record, user=user, text_hash=text_hash)
        if key is not None:
            same = same.filter(section_key=key)
        same.delete()
        return False
    try:
        with transaction.atomic():
            ViewedMark.objects.get_or_create(
                user=user, reading=reading, section_key=section.key,
                defaults={"record": record, "version": version, "text_hash": section.text_hash},
            )
    except IntegrityError:
        pass  # a simultaneous mark of the same section won: it is marked either way
    return True
