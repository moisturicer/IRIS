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


def title_matches(rows: Sequence, reference: str) -> tuple[str, list]:
    """The strongest tier with any match: exact, then short title, then phrase."""
    key = title_key(reference)
    if not key:
        return "none", []
    exact = [r for r in rows if r["title"] and title_key(r["title"]) == key]
    if exact:
        return "exact_title", exact
    short = [r for r in rows if r["title"] and short_title(r["title"]) == key]
    if short:
        return "short_title", short
    if len(key) >= 4:
        pattern = re.compile(r"(?<!\w)" + re.escape(key) + r"(?!\w)")
        phrase = [r for r in rows if r["title"] and pattern.search(title_key(r["title"]))]
        if phrase:
            return "title_phrase", phrase
    return "none", []
