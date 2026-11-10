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

from django.db import IntegrityError, transaction

from apps.records.review_text import readings

from . import comparison, version_comparison
from .models import ViewedMark

SIDES = ("from", "to")


class ViewedError(ValueError):
    """400: the request names no section of a comparison that can be marked."""


class Marks:
    """What `user` has marked viewed on a record, read once per comparison.

    A section is matched by its `text_hash`. A section with no text of its own
    (a chapter heading before its first subsection) has the hash of nothing,
    which every empty section shares, so it is matched by its `key` as well.
    """

    def __init__(self, record, user):
        rows = ViewedMark.objects.filter(record=record, user=user).values_list("text_hash", "section_key")
        self.pairs = set(rows)
        self.hashes = {text_hash for text_hash, _ in self.pairs}

    def has(self, *, key: str, text_hash: str, empty: bool) -> bool:
        return (text_hash, key) in self.pairs if empty else text_hash in self.hashes


def mark_side(section: dict) -> str:
    """The side a compared section is marked on: the later one unless removed."""
    return "to" if section["to"] else "from"


def _request(data) -> tuple:
    if not isinstance(data, dict):
        raise ViewedError("Say which section to mark.")
    side, key, viewed = data.get("side"), data.get("key"), data.get("viewed")
    if side not in SIDES:
        raise ViewedError("`side` is `from` or `to`.")
    if not isinstance(key, str) or not key:
        raise ViewedError("Say which section to mark.")
    if not isinstance(viewed, bool):
        raise ViewedError("`viewed` is true or false.")
    if data.get("from") is None or data.get("to") is None:
        raise ViewedError("Give both `from` and `to`.")
    return data["from"], data["to"], side, key, viewed


def set_viewed(record, user, data) -> bool:
    """Mark or unmark one section of a comparison for `user`. Returns the new state."""
    old_number, new_number, side, key, viewed = _request(data)
    try:
        old, new = version_comparison.choose(record, user, old_number, new_number)
    except version_comparison.BadPair as exc:
        raise ViewedError(str(exc)) from None
    pair = readings.pair(old, new)
    if pair.state != readings.READY:
        raise ViewedError("This comparison isn't ready, so nothing in it can be marked yet.")
    if comparison.by_page(version_comparison.as_reading(pair.old), version_comparison.as_reading(pair.new)):
        raise ViewedError("This comparison is listed by page, so it has no sections to mark.")
    version, reading = (old, pair.old) if side == "from" else (new, pair.new)
    section = reading.sections.filter(key=key).first()
    if section is None:
        raise ViewedError("That section isn't in this comparison.")

    if not viewed:
        same = ViewedMark.objects.filter(record=record, user=user, text_hash=section.text_hash)
        if not section.passages:
            same = same.filter(section_key=section.key)
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
