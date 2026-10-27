"""Exact metadata counts for the `count` lane (IR-543, IR-551 pilot).

A question like "How many papers are in the repository?" asks about stored
metadata, not about a topic. This module answers it with one database
aggregate over the catalogue the asker can browse. No model reads the
question and none writes the number: the interpreter is a closed set of
rules, the count is `COUNT(DISTINCT id)`, and the sentence is assembled here.

Supported predicates are the ones `Record` actually stores: classification,
PSCED area, record type, completion year and the IP flag. A question about a
field IRIS does not store (publication year, authors, ...) is declined by
name rather than answered with a nearby field. A question whose remainder is
a topic ("about flooding") is not a metadata count and is left to the topic
workflow.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable, Mapping, Optional

from django.db.models import Count

from apps.ai.answers.citations import NO_SOURCES, GroundedAnswer
from apps.ai.research.context import RunContext
from apps.ai.research.tools.common import apply_filters, readable_records
from apps.records.models import Classification, PSCEDClassification, RecordType
from core.enums import PUBLICLY_VISIBLE_STATUSES

COMPLETENESS = "exact_count"
POPULATION = "published records you can see"
SCOPED_POPULATION = "published records you can see, limited to the paper this chat is about"

_COUNT_SHAPE = re.compile(r"\b(how many|number of|count of|total number of)\b")
_YEAR = r"(?:19|20)\d{2}"
_PUBLICATION_YEAR = re.compile(
    r"\b(publication (year|date)|year (of )?publication|year published|date published)\b"
    rf"|\bpublished\b[^?.]{{0,25}}\b{_YEAR}\b"
    r"|\bpublished (this|last|next) year\b"
)
#: Only an unmistakable relative date. A bare "recent" or "latest" is more
#: often a topic ("recent advances in ...") than a date, so it is left alone.
_RELATIVE_DATE = re.compile(
    r"\b(this year|last year|next year|current year|recent years"
    r"|(past|last|previous) \d+ (years?|months?))\b"
)
#: Fields IRIS does not store. Declined when the question is only about them or
#: says so structurally ("advised by"), never merely because the word appears
#: inside a topic ("papers about college students").
_OTHER_FIELD = re.compile(
    r"\b(authors?|authored|written|advis(?:er|or)s?|advised|supervis(?:or|ed)s?|panel(?:ists?)?"
    r"|departments?|colleges?|programs?|keywords?|budgets?|grants?|funded|funding"
    r"|submitted|uploaded|approved|reviewed|citations?|cited|downloads?|views?)\b"
)
_OTHER_FIELD_BY = re.compile(
    r"\b(authored|written|advised|supervised|funded|submitted|uploaded|approved|reviewed) by\b"
    r"|\b(by|per|each|every) (author|adviser|advisor|supervisor|department|college|program|keyword)s?\b"
)
_PLACE = re.compile(
    r"\b(in|within|of|on)\s+(the\s+)?(iris|repository|repositories|catalogue|catalog"
    r"|database|system|collection|corpus|library|archive)\b"
)
_YEAR_RANGE = re.compile(rf"\b(?:from|between)\s+({_YEAR})\s+(?:to|and|through|until|-)\s+({_YEAR})\b")
_YEAR_FROM = re.compile(rf"\bfrom\s+{_YEAR}\b")
_YEAR_ANY = re.compile(rf"\b{_YEAR}\b")
_YEAR_SINCE = re.compile(rf"\b(?:since|after)\s+({_YEAR})\b")
_YEAR_BEFORE = re.compile(rf"\b(?:before|until|up to)\s+({_YEAR})\b")
_YEAR_IN = re.compile(rf"\b(?:in|during|of|for|year)?\s*({_YEAR})\b")
_IP = re.compile(r"\b(intellectual property|ip[- ]flagged|ip records?|ip papers?|ip)\b")

#: Words that scaffold a count question without naming a field or a topic.
_NOISE = frozenset("""
a an the of in at to from and or
how many number count total overall all any are is was were be been there here
do does did each per every write wrote have has had we you i can could see seen shown listed
stored recorded record records paper papers thesis theses
research item items document documents entry entries
project projects proposal proposals available exist exists existing currently
now so far published completed finished done year years that which
classified classification categorized categorised category categories area areas type types
psced as under named called labelled labeled tagged filed listed
""".split())


@dataclass(frozen=True)
class Predicate:
    """What was asked: database filters plus the conditions, in words, for the reader."""

    filters: Mapping[str, object]
    conditions: tuple = ()

    def describe(self, population: str) -> str:
        if not self.conditions:
            return f"all {population}"
        return f"{population} where " + " and ".join(self.conditions)


@dataclass(frozen=True)
class Declined:
    """A metadata-shaped question IRIS will not answer with a nearby field."""

    text: str


@dataclass(frozen=True)
class MetadataCount:
    total: int
    visible: int
    ai_assessable: int
    duplicate_groups: int
    undated: Optional[int]
    predicate: Predicate
    population: str
    snapshot: str
    #: Set when the readable set moved between the count and the checks.
    unstable: bool = False


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def _variants(name: str) -> list[str]:
    base = re.escape(_fold(name).strip())
    forms = {base, base + "s", base + "es"}
    if name.casefold().endswith("is"):
        forms.add(re.escape(_fold(name).strip()[:-2]) + "es")
    return sorted(forms, key=len, reverse=True)


def _find_name(text: str, names: Iterable[str]) -> list[tuple[str, tuple[int, int]]]:
    found = []
    for name in names:
        for form in _variants(name):
            match = re.search(rf"(?<!\w){form}(?!\w)", text)
            if match:
                found.append((name, match.span()))
                break
    return found


def _taxonomies() -> dict[str, list[str]]:
    return {
        "classification": list(Classification.objects.values_list("name", flat=True)),
        "psced": list(PSCEDClassification.objects.values_list("name", flat=True)),
        "record_type": list(RecordType.objects.values_list("name", flat=True)),
    }


_LABELS = {"classification": "classification", "psced": "PSCED area", "record_type": "record type"}
_SUPPORTED = ("classification, PSCED area, record type, completion year or the IP flag")


def interpret(
    question: str, taxonomies: Callable[[], Mapping[str, list[str]]]
) -> Optional[object]:
    """`Predicate`, `Declined`, or `None` when this is not a metadata count.

    `taxonomies` is read only once the question has a count shape and no
    declined field, so a question that cannot be a metadata count costs no query.
    """
    text = _fold(question)
    if not _COUNT_SHAPE.search(text):
        return None
    if _PUBLICATION_YEAR.search(text):
        return Declined(
            "IRIS records the year a record was completed, not a publication year, "
            "and the two are not the same. Ask by completion year instead, for "
            "example: how many records were completed in 2023?"
        )
    if _RELATIVE_DATE.search(text):
        return Declined(
            "IRIS cannot resolve a relative date such as 'last year' or 'recent years' "
            "into a count. Name the completion year, for example: how many "
            "records were completed in 2023?"
        )
    if (m := _OTHER_FIELD_BY.search(text)):
        return _unstored(m.group(0))
    text = _PLACE.sub(" ", text)
    working = text
    filters: dict[str, object] = {}
    parts: list[str] = []

    # Taxonomy names first (longest first), so "Software Engineering" is not
    # also read as "Engineering" and a name's own digits are not read as a year.
    matches = []
    for kind, names in taxonomies().items():
        for name, span in _find_name(text, names):
            matches.append((kind, name, span))
    matches.sort(key=lambda m: m[2][1] - m[2][0], reverse=True)
    taken: list[tuple[int, int]] = []
    kinds_seen: Counter = Counter()
    for kind, name, (start, end) in matches:
        if any(start < b and a < end for a, b in taken):
            continue
        taken.append((start, end))
        kinds_seen[kind] += 1
        if kinds_seen[kind] > 1 or any(m[2] == (start, end) and m[0] != kind for m in matches):
            return Declined(
                "That question names more than one value of the same field, or a "
                "name used by two fields, so it has no single exact count. Ask for one "
                f"{_LABELS[kind]} at a time."
            )
        filters[kind] = name
        parts.append(f"{_LABELS[kind]} is {name}")
    for start, end in sorted(taken, reverse=True):
        working = working[:start] + " " + working[end:]

    year_from = year_to = None
    range_match = _YEAR_RANGE.search(working)
    if range_match is None and _YEAR_FROM.search(working):
        return Declined(
            "'from' a year could mean that year only or that year onward. Say 'in "
            "2020' for one year, or 'since 2020' for 2020 or later."
        )
    if (m := range_match):
        year_from, year_to = sorted((int(m.group(1)), int(m.group(2))))
        working = working.replace(m.group(0), " ")
        parts.append(f"completion year is {year_from} to {year_to}")
    elif (m := _YEAR_SINCE.search(working)):
        year_from = int(m.group(1)) + (1 if m.group(0).startswith("after") else 0)
        working = working.replace(m.group(0), " ")
        parts.append(f"completion year is {year_from} or later")
    elif (m := _YEAR_BEFORE.search(working)):
        year_to = int(m.group(1)) - (1 if m.group(0).startswith("before") else 0)
        working = working.replace(m.group(0), " ")
        parts.append(f"completion year is {year_to} or earlier")
    elif (m := _YEAR_IN.search(working)):
        year_from = year_to = int(m.group(1))
        working = working.replace(m.group(0), " ")
        parts.append(f"completion year is {year_from}")
    if year_from is not None:
        filters["year_from"] = year_from
    if year_to is not None:
        filters["year_to"] = year_to
    if _YEAR_ANY.search(working):
        # "in 2020 or 2021", "after 2020 and before 2023": one clause was
        # understood and another was not, so no exact count exists to give.
        return Declined(
            "That question has more than one year condition. Ask for one year, "
            "'since' a year, 'before' a year, or a single range such as 'between "
            "2020 and 2023'."
        )

    if (m := _IP.search(working)):
        filters["is_ip"] = True
        working = working.replace(m.group(0), " ")
        parts.append("flagged as intellectual property")

    # Whatever is left decides the question. A field IRIS does not store is
    # declined by name only when nothing else is left to ask about; any other
    # leftover word is a topic, which the topic workflow handles.
    stored_out = _OTHER_FIELD.search(working)
    if stored_out:
        working = _OTHER_FIELD.sub(" ", working)
    residue = [t for t in re.findall(r"[^\W_]+", working) if t not in _NOISE]
    if residue:
        return None
    if stored_out:
        return _unstored(stored_out.group(0))
    return Predicate(filters, tuple(parts))


def _unstored(word: str) -> Declined:
    return Declined(
        f"IRIS does not store '{word}' as a countable field, so it cannot give an "
        f"exact count for it. It can count by {_SUPPORTED}."
    )


def _normalized_title(title: str) -> str:
    return " ".join(re.findall(r"\w+", _fold(title)))


def _snapshot() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def count(ctx: RunContext, predicate: Predicate) -> MetadataCount:
    """`COUNT(DISTINCT id)` over the catalogue this asker can read.

    The population is the asker's `visible_to` set (and Paper Chat scope)
    narrowed to the public catalogue, so staff and owners get the same number
    a student does and a private draft is never counted. AI eligibility is
    described afterwards over the same Records and never changes the count.
    """
    filters = dict(predicate.filters)
    is_ip = filters.pop("is_ip", None)
    base = readable_records(ctx).filter(pipeline_status__in=PUBLICLY_VISIBLE_STATUSES)
    matched = apply_filters(base, filters)
    if is_ip is not None:
        matched = matched.filter(is_ip=is_ip)
    snapshot = _snapshot()
    total = matched.aggregate(n=Count("pk", distinct=True))["n"]
    visible = base.aggregate(n=Count("pk", distinct=True))["n"]
    undated = None
    if "year_from" in filters or "year_to" in filters:
        undated_base = apply_filters(base, {k: v for k, v in filters.items()
                                            if not k.startswith("year_")})
        if is_ip is not None:
            undated_base = undated_base.filter(is_ip=is_ip)
        undated = undated_base.filter(year_completed__isnull=True).count()

    # One pass over the counted Records, in chunks: the disclosure gate needs
    # the full row, but nothing is held beyond a title and a flag per Record.
    seen: set[int] = set()
    titles: Counter = Counter()
    assessable = 0
    rows = matched.select_related("classification", "record_type").distinct()
    for record in rows.iterator(chunk_size=500):
        seen.add(record.pk)
        if record.title:
            titles[_normalized_title(record.title)] += 1
        assessable += bool(ctx.permits(record))
    return MetadataCount(
        total=total,
        visible=visible,
        ai_assessable=assessable,
        duplicate_groups=sum(1 for n in titles.values() if n > 1),
        undated=undated,
        predicate=predicate,
        population=POPULATION if ctx.scope_record_id is None else SCOPED_POPULATION,
        snapshot=snapshot,
        # The queries are not one transaction; if the readable set moved between
        # them the numbers can disagree, and a disagreeing answer is not given.
        unstable=len(seen) != total or total > visible,
    )


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def render(result: MetadataCount) -> tuple[str, dict]:
    """The reader's sentence, and the structured block the transcript keeps."""
    total = result.total
    description = result.predicate.describe(result.population)
    if total:
        lead = f"**{_plural(total, 'record')}** {'matches' if total == 1 else 'match'}: {description}."
    else:
        lead = (f"No records you can see match: {description}. "
                f"This says nothing about records outside your view.")
    parts = [lead, f"Counted at {result.snapshot} over the {_plural(result.visible, 'record')} "
                   f"among the {result.population}."]
    parts.append("Each count is of distinct IRIS records, not of unique scholarly works: "
                 "the same work can be recorded more than once.")
    if result.duplicate_groups:
        parts.append(f"{_plural(result.duplicate_groups, 'title')} appear on more than one "
                     "counted record, so some may be the same work. They are still counted separately.")
    if result.undated:
        parts.append(f"{_plural(result.undated, 'record')} with no completion year "
                     "recorded could not be matched to the year and are not counted.")
    if total:
        blocked = total - result.ai_assessable
        parts.append(f"AI assessment is a separate question from this count: "
                     f"{result.ai_assessable} of these can be read by AI"
                     + (f" and {blocked} cannot, which does not change the count." if blocked
                        else "."))
    text = " ".join(parts)
    block = {
        "total": total,
        "predicate": description,
        "population": result.population,
        "snapshot": result.snapshot,
        "visible": result.visible,
        "ai_assessable": result.ai_assessable,
        "not_ai_assessable": total - result.ai_assessable,
        "possible_duplicate_titles": result.duplicate_groups,
        "undated": result.undated,
        "unit": "distinct IRIS records, not unique scholarly works",
    }
    return text, {"completeness": COMPLETENESS, "wording": text, "records": [], "count": block}


def answer(ctx: RunContext, question: str):
    """`(GroundedAnswer, listing)` for a metadata count, or `None` for a topic."""
    verdict = interpret(question, _taxonomies)
    if verdict is None:
        return None
    if isinstance(verdict, Declined):
        return GroundedAnswer(text=verdict.text, citations=(), state=NO_SOURCES), None
    result = count(ctx, verdict)
    if result.unstable:
        return GroundedAnswer(
            text="The readable papers changed during counting. Please try again.",
            citations=(), state=NO_SOURCES,
        ), None
    text, listing = render(result)
    return GroundedAnswer(text=text, citations=()), listing
