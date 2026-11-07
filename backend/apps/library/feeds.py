"""
What a saved feed may hold, and what has gone stale in it (IR-577).

A feed's `query` is Discover's own query in the spelling Discover writes into
its URL (`frontend/src/features/discover/discoverQuery.ts`), so there is no
second filter representation. This module checks one on the way in, and says
which of its taxonomy values no longer exist; it never rewrites a stored query,
because dropping a value would silently widen the feed.

The keys and their spelling are the frontend's, restated here because the
server has to refuse what Discover could not have written. `feed` (the tab) is
deliberately not a key: a tab is not a criterion.
"""

import re

from rest_framework.exceptions import ValidationError

from apps.accounts.models import College
from apps.records.models import Classification, RecordType
from core.enums import IPType

from .models import SavedFeed

MAX_NAME_LENGTH = 60
#: Sanity bound on the search text kept in a feed: it is stored, so it needs a
#: ceiling. Not a product decision; Discover's own box has none.
MAX_SEARCH_LENGTH = 200

SORTS = ("newest", "viewed")
#: Discover's default sort. Left out of a stored query, as it is from the URL.
DEFAULT_SORT = "newest"
#: `has_ip` is Discover's "any IP" option; the rest are the IP types.
IP_VALUES = frozenset({"has_ip", *IPType.values})
QUERY_KEYS = ("q", "type", "college", "classification", "year", "ip", "sort")

EMPTY_FEED = "Add at least one Area, keyword, college, type, year or IP filter."

# At most 18 digits, so an absurd id is a 400 and never a database overflow.
_ID = re.compile(r"^\d{1,18}$")
_YEAR = re.compile(r"^\d{4}$")

#: The taxonomy-backed keys, and the model whose rows a value must still name.
_TAXONOMY = (
    ("type", RecordType, False),
    ("college", College, True),
    ("classification", Classification, True),
)


def clean_name(raw) -> str:
    name = raw.strip() if isinstance(raw, str) else ""
    if not name:
        raise ValidationError({"name": ["Give the feed a name."]})
    if len(name) > MAX_NAME_LENGTH:
        raise ValidationError({"name": [f"Use {MAX_NAME_LENGTH} characters or fewer."]})
    return name


def name_taken(owner, name: str, *, excluding=None) -> bool:
    """Does `owner` already have a feed called `name`, ignoring case?"""
    taken = SavedFeed.objects.filter(owner=owner, name__iexact=name)
    if excluding is not None:
        taken = taken.exclude(pk=excluding)
    return taken.exists()


def duplicate_name() -> ValidationError:
    return ValidationError({"name": ["You already have a saved feed with that name."]})


def _ids(value: str) -> list[int]:
    return sorted({int(part) for part in value.split(",")})


def clean_query(raw) -> dict:
    """The query as it will be stored: Discover's spelling, defaults omitted."""
    if not isinstance(raw, dict):
        raise ValidationError({"query": ["Provide the feed's filters as an object."]})

    problems = []
    unknown = sorted(set(raw) - set(QUERY_KEYS))
    if unknown:
        problems.append(f"Not a Discover filter: {', '.join(unknown)}.")

    cleaned = {}
    for key in QUERY_KEYS:
        if key not in raw:
            continue
        value = raw[key]
        if not isinstance(value, str):
            problems.append(f"{key} must be text.")
            continue
        value = value.strip()
        if not value:
            continue
        if key == "q":
            if len(value) > MAX_SEARCH_LENGTH:
                problems.append(f"Keywords must be {MAX_SEARCH_LENGTH} characters or fewer.")
            else:
                cleaned[key] = value
        elif key in ("college", "classification"):
            if all(_ID.match(part) for part in value.split(",")):
                cleaned[key] = ",".join(str(i) for i in _ids(value))
            else:
                problems.append(f"{key} must be a list of ids.")
        elif key == "type":
            if _ID.match(value):
                cleaned[key] = value
            else:
                problems.append("type must be an id.")
        elif key == "year":
            if _YEAR.match(value):
                cleaned[key] = value
            else:
                problems.append("year must be four digits.")
        elif key == "ip":
            if value in IP_VALUES:
                cleaned[key] = value
            else:
                problems.append("ip is not an IP filter Discover offers.")
        elif key == "sort":
            if value not in SORTS:
                problems.append("sort must be newest or viewed.")
            elif value != DEFAULT_SORT:
                cleaned[key] = value

    for key, model, many in _TAXONOMY:
        if key not in cleaned:
            continue
        wanted = set(_ids(cleaned[key])) if many else {int(cleaned[key])}
        missing = wanted - set(model.objects.filter(pk__in=wanted).values_list("pk", flat=True))
        if missing:
            problems.append(f"{key} names a value that no longer exists. Choose it again.")

    if problems:
        raise ValidationError({"query": problems})
    if not any(key != "sort" for key in cleaned):
        raise ValidationError({"query": [EMPTY_FEED]})
    return cleaned


def stale_values(queries: list[dict]) -> list[dict]:
    """For each stored query, the taxonomy ids it names that no longer exist.

    One answer per query, in order: `{"classification": [id, ...]}`, empty when
    nothing is stale. The stored queries themselves are not touched.
    """
    named = {key: set() for key, _, _ in _TAXONOMY}
    for query in queries:
        for key, _, many in _TAXONOMY:
            value = query.get(key)
            if value:
                named[key].update(_ids(value) if many else [int(value)])

    alive = {
        key: set(model.objects.filter(pk__in=named[key]).values_list("pk", flat=True))
        for key, model, _ in _TAXONOMY
        if named[key]
    }
    answers = []
    for query in queries:
        stale = {}
        for key, _, many in _TAXONOMY:
            value = query.get(key)
            if not value:
                continue
            gone = sorted((set(_ids(value)) if many else {int(value)}) - alive.get(key, set()))
            if gone:
                stale[key] = gone
        answers.append(stale)
    return answers
