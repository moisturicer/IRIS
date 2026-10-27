"""Title matching shared by the comparison lane and `resolve_papers` (IR-591)."""

from __future__ import annotations

import re
from typing import Iterable, Sequence, TypeVar

T = TypeVar("T")


def title_key(text: str) -> str:
    """Case and spacing folded, trailing punctuation dropped."""
    return " ".join(text.split()).casefold().strip(" .?!;,")


def short_title(text: str) -> str:
    """The name before a subtitle: "MeshKV" for "MeshKV: Caching ..."."""
    return title_key(re.split(r"\s*[:–—]\s+|\s+-\s+", text, maxsplit=1)[0])


def exact_title_matches(records: Iterable[T], reference: str) -> list[T]:
    key = title_key(reference)
    return [r for r in records if r.title and title_key(r.title) == key]


def title_matches(records: Sequence[T], reference: str) -> tuple[str, list[T]]:
    """The strongest tier with any match: exact, then short title, then phrase."""
    key = title_key(reference)
    if not key:
        return "none", []
    exact = exact_title_matches(records, reference)
    if exact:
        return "exact_title", exact
    short = [r for r in records if r.title and short_title(r.title) == key]
    if short:
        return "short_title", short
    if len(key) >= 4:
        pattern = re.compile(r"(?<!\w)" + re.escape(key) + r"(?!\w)")
        phrase = [r for r in records if r.title and pattern.search(title_key(r.title))]
        if phrase:
            return "title_phrase", phrase
    return "none", []
