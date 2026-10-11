"""Literal evidence checks, not a judgement of whether a claim is true (IR-512).

Paper titles in research answers must be marked as «title». Quoted and
emphasized title-shaped spans are checked too. Unmarked prose cannot be
recognized as a title deterministically; semantic claim support stays offline.
"""

import json
import re
from decimal import Decimal

from apps.ai.citation_markers import MARKER, numbers_in
from apps.ai.research.results import Completeness, ToolStatus

_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:,\d{3})*(?:\.\d+)?(?!\w)")
_WORD_NUMBERS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "hundred": "100", "thousand": "1000",
}
_WORDS = re.compile(r"\b(" + "|".join(_WORD_NUMBERS) + r")\b", re.I)
_TITLE = re.compile(r'«([^»\n]+)»|“([^”\n]+)”|"([^"\n]+)"|(?<!\*)\*([^*\n]+)\*(?!\*)|\btitled\s+([^\n.\[]+)', re.I)
_HANDLE = re.compile(r"\[([ER]\d+)\]")
_EXHAUSTIVE = re.compile(r"\b(all (?:the )?(?:papers|records|studies)|every (?:paper|record|study)|there are|exhaustive|complete (?:list|corpus)|only \d+ (?:papers|records|studies))\b", re.I)


def numbers(text):
    values = {Decimal(m.group().replace(",", "")) for m in _NUMBER.finditer(text)}
    values.update(Decimal(_WORD_NUMBERS[m.group().lower()]) for m in _WORDS.finditer(text))
    return values


def validate_answer(text, *, sources, ledger, results):
    """Return reason codes only; no content ever enters the run audit."""
    failures = set()
    markers = list(MARKER.finditer(text))
    valid_markers = {n for m in markers for n in numbers_in(m) if 1 <= n <= len(sources)}
    if any(n < 1 or n > len(sources) for m in markers for n in numbers_in(m)) or _HANDLE.search(text):
        failures.add("unknown_citation")
    # Validate raw markers before parse_citations can silently discard one.
    if re.search(r"\[(?:ref|source|E|R)[:\s]?[^\]]+\]", text, re.I):
        failures.add("unknown_citation")
    body = MARKER.sub("", text)
    computed = set()
    successful = [r for r in results if r.status in (ToolStatus.OK, ToolStatus.EMPTY, ToolStatus.DEGRADED)]
    for result in successful:
        computed.update(numbers(json.dumps(dict(result.detail))))
    supported = set(computed)
    for marker in valid_markers:
        supported.update(numbers(sources[marker - 1].content))
    if numbers(body) - supported:
        failures.add("unsupported_number")
    titles = {item.record_title.casefold().strip() for item in (*ledger.records(), *ledger.passages())}
    for match in _TITLE.finditer(body):
        title = next(value for value in match.groups() if value is not None).casefold().strip()
        if title not in titles:
            failures.add("unknown_title")
    # Any partial result keeps this whole answer conservative. An exact
    # metadata count does not make a passage search exhaustive.
    if _EXHAUSTIVE.search(body) and (
        not successful or any(r.coverage.label is not Completeness.EXHAUSTIVE or r.coverage.truncated for r in successful)
    ):
        failures.add("completeness_overclaim")
    if re.search(r"\bscreened\b", body, re.I) and not any(r.coverage.label is Completeness.SCREENED for r in successful):
        failures.add("completeness_overclaim")
    return tuple(sorted(failures))
