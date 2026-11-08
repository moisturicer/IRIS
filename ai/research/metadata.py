"""Title matching and the metadata count vocabulary (IR-750).

Ports Django's `apps.ai.research.titles` and `aggregate_records` filters, so
both runtimes name papers and count them alike; the runtime cannot import Django.
"""

from __future__ import annotations

import re
from typing import Sequence

#: How many candidates an ambiguous reference shows.
MAX_CANDIDATES = 5
#: References one call may resolve.
MAX_REFERENCES = 8
#: Most papers one listing names; the total is exact whatever the cap (IR-994).
MAX_LISTED = 50
#: Every count is relative to the asker (ADR-027 §3).
RELATIVE_TO = "of the records you can see"

#: Taxonomy filter -> (table, Record column). Names match case-insensitively.
TAXONOMIES = {
    "classification": ("records_classification", "classification_id"),
    "psced": ("records_pscedclassification", "psced_id"),
    "record_type": ("records_recordtype", "record_type_id"),
}
YEAR_RANGE = (1900, 2100)
FILTERS = (*TAXONOMIES, "year_from", "year_to", "is_ip")
#: Group name -> the counted row's column.
GROUPS = ("classification", "psced", "record_type", "year")


def title_key(text: str) -> str:
    """Case and spacing folded, trailing punctuation dropped."""
    return " ".join(text.split()).casefold().strip(" .?!;,")


def short_title(text: str) -> str:
    """The name before a subtitle: "MeshKV" for "MeshKV: Caching ..."."""
    return title_key(re.split(r"\s*[:–—]\s+|\s+-\s+", text, maxsplit=1)[0])


def fold(text: str) -> str:
    """Case folded, every run of punctuation, hyphens or spaces made one space (IR-995)."""
    return " ".join(re.sub(r"[\W_]+", " ", text.casefold()).split())


#: Words that say what kind of thing is named, not which one.
_GENERIC = frozenset({"the", "a", "an", "and", "of", "on", "in", "for", "to", "with", "about", "paper",
                      "papers", "study", "work", "article", "project", "one"})
#: Share of a reference's distinctive words a close title must contain.
CLOSE_SHARE = 0.75


def _close(rows: Sequence, reference: str) -> list:
    """Titles containing most of the reference's distinctive words, best first."""
    words = [w for w in fold(reference).split() if w not in _GENERIC]
    if len(words) < 2:
        return []

    def present(word, title_words):
        return word in title_words or (len(word) >= 5 and any(t.startswith(word[:5]) for t in title_words))

    scored = []
    for row in rows:
        if not row["title"]:
            continue
        title_words = set(fold(row["title"]).split())
        share = sum(present(w, title_words) for w in words) / len(words)
        if share >= CLOSE_SHARE:
            scored.append((-share, fold(row["title"]), row))
    return [row for *_, row in sorted(scored, key=lambda s: s[:2])]


def title_matches(rows: Sequence, reference: str) -> tuple[str, list]:
    """The strongest tier with any match: exact, short title, phrase, then close titles to choose from."""
    key = title_key(reference)
    if not key:
        return "none", []
    exact = [r for r in rows if r["title"] and title_key(r["title"]) == key]
    if exact:
        return "exact_title", exact
    short = [r for r in rows if r["title"] and short_title(r["title"]) == key]
    if short:
        return "short_title", short
    folded = fold(reference)
    if len(folded) >= 4:
        pattern = re.compile(r"(?<!\w)" + re.escape(folded) + r"(?!\w)")
        phrase = [r for r in rows if r["title"] and pattern.search(fold(r["title"]))]
        if phrase:
            return "title_phrase", phrase
    close = _close(rows, reference)
    if close:
        return "close_title", close
    return "none", []
