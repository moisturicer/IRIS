"""The Changes tab's comparison of two Versions (ADR-058 §3 as amended
2026-11-08, IR-873): which pair, which readings, and what the reviewer is told.

`comparison.py` compares two readings and knows nothing else. This module
picks the pair (the Version this reviewer last finished a review on, then the
latest), asks `readings.pair` for two readings by one reader, and words each
state. **No message names a reader** (ADR-058 §3 as amended, point 5).
"""
from __future__ import annotations

from apps.records.models import RecordVersion
from apps.records.review_text import readings, store

from . import comparison
from .models import ReviewRound

PREPARING_MESSAGE = "Preparing the comparison…"
UNAVAILABLE_MESSAGE = "This comparison isn't available right now."
#: What the reviewer is told while there is no comparison to show yet.
WAITING = {readings.PREPARING: PREPARING_MESSAGE, readings.UNAVAILABLE: UNAVAILABLE_MESSAGE}


class BadPair(ValueError):
    """The request names no pair that can be compared; the message says why."""


def _versions(record):
    return (RecordVersion.objects.filter(record=record).select_related("review_text")
            .prefetch_related("documents__upload__slot"))


def default_pair(record, user, by_number) -> tuple:
    """ADR-058 §3: the Version this reviewer last finished a review on →
    latest; without one, or when that is the latest, previous → latest."""
    *_, previous, latest = sorted(by_number)
    last = (
        ReviewRound.objects.filter(record=record, actor=user, version__isnull=False)
        .order_by("-created_at", "-pk").values_list("version__number", flat=True).first()
    )
    old = last if last in by_number and last < latest else previous
    return by_number[old], by_number[latest]


def _number(value, name):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise BadPair(f"`{name}` must be a Version number.") from None


def choose(record, user, old_number=None, new_number=None) -> tuple:
    """The two Versions to compare, earlier first. Raises `BadPair`."""
    by_number = {v.number: v for v in _versions(record)}
    if len(by_number) < 2:
        raise BadPair("This paper has one Version, so there is nothing to compare yet.")
    if old_number is None and new_number is None:
        return default_pair(record, user, by_number)
    if old_number is None or new_number is None:
        raise BadPair("Give both `from` and `to`, or neither.")
    old, new = (by_number.get(_number(old_number, "from")),
                by_number.get(_number(new_number, "to")))
    if old is None or new is None:
        raise BadPair("No such Version of this paper.")
    if old.number == new.number:
        raise BadPair("Choose two different Versions.")
    return (old, new) if old.number < new.number else (new, old)


def _reading(text) -> dict:
    return {"page_count": text.page_count, "warnings": text.warnings,
            "sections": store.sections(text)}


def _documents(version) -> list:
    return [{"slot": d.upload.slot.name, "upload_id": d.upload_id} for d in version.documents.all()]


def _notice_message(notice, old, new) -> str:
    n = f"v{(old if notice['side'] == 'from' else new).number}"
    if notice["code"] == "sections_unidentified":
        return f"Sections couldn't be identified in {n}, so changes are listed by page."
    which = "removed" if notice["side"] == "to" else "added"
    return (f"Parts of this comparison may be unreliable. Some text in {n} may not have "
            f"been read. Check {which} passages against the PDF before relying on them.")


def payload(record, user, old_number=None, new_number=None) -> dict:
    """The comparison as `GET /records/<id>/versions/compare/` serves it."""
    old, new = choose(record, user, old_number, new_number)
    body = {
        "from": old.number,
        "to": new.number,
        "documents": comparison.compare_documents(_documents(old), _documents(new)),
    }
    pair = readings.pair(old, new)
    body["state"] = pair.state
    if pair.state in WAITING:
        return {**body, "message": WAITING[pair.state]}
    if pair.state == readings.NO_TEXT:
        version = pair.without_text
        said = (store.message(version, version.review_text) if version.manuscript
                else f"v{version.number} has no manuscript, so it can't be compared.")
        return {**body, "message": said}
    result = comparison.compare(_reading(pair.old), _reading(pair.new))
    for notice in result["notices"]:
        notice["message"] = _notice_message(notice, old, new)
    return {**body, "message": None, **result}
