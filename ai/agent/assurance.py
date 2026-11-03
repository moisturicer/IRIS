"""Deterministic checks on the AGENT's first draft (IR-728, ADR-049 §15).

The rules of Django's research validation (`apps.ai.research.validation`,
IR-512), applied to passage handles: cited handles must be ones this run
was shown, numbers must come from cited text or tool coverage, marked
titles must be papers the run saw, and completeness is never claimed from
keyword search. They catch literal mistakes, never prove a claim true.
"""

from __future__ import annotations

import re
from decimal import Decimal

from ai.agent.tools import Investigation
from ai.runs.executor import Citation

CITE = re.compile(r"\[(P[0-9a-f]{20})\]")
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:,\d{3})*(?:\.\d+)?(?!\w)")
_WORD_NUMBERS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "hundred": "100", "thousand": "1000",
}
_WORDS = re.compile(r"\b(" + "|".join(_WORD_NUMBERS) + r")\b", re.I)
_TITLE = re.compile(r'«([^»\n]+)»|“([^”\n]+)”|"([^"\n]+)"|(?<!\*)\*([^*\n]+)\*(?!\*)|\btitled\s+([^\n.\[]+)', re.I)
_INTRODUCED_TITLE = re.compile(
    r"\b(?:paper|study|thesis|record)\s+(?:(?:titled|called|named)\s+)?"
    r"([A-Z][\w'-]*(?:\s+(?:(?:of|the|for|and|in|on|with|a|to)\s+)?[A-Z][\w'-]*)+)"
)
_EXHAUSTIVE = re.compile(
    r"\b(all (?:the )?(?:papers|records|studies)|every (?:paper|record|study)|there are|exhaustive"
    r"|complete (?:list|corpus)|only \d+ (?:papers|records|studies))\b", re.I)


def numbers(text: str) -> set[Decimal]:
    values = {Decimal(m.group().replace(",", "")) for m in _NUMBER.finditer(text)}
    values.update(Decimal(_WORD_NUMBERS[m.group().lower()]) for m in _WORDS.finditer(text))
    return values


def cited(text: str) -> list[str]:
    """Cited passage handles in order of first appearance."""
    return list(dict.fromkeys(CITE.findall(text)))


def check(text: str, investigation: Investigation, *, prior=(), excluded=()) -> tuple[str, ...]:
    """Reason codes only; none carries content.

    `prior` Turns were checked when delivered, so their numbers count as supported.
    """
    failures = set()
    handles = cited(text)
    if any(h not in investigation.passages for h in handles):
        failures.add("unknown_citation")
    if any(investigation.passages[h].record_id in excluded for h in handles if h in investigation.passages):
        failures.add("excluded_citation")
    body = CITE.sub("", text)
    # Passage handles are the only citation namespace.
    if re.search(r"\[[^\]\n]+\]", body):
        failures.add("unknown_citation")
    # A question answered with no repository context is general background.
    if not (investigation.researched or investigation.papers):
        return tuple(sorted(failures))
    supported = {Decimal(f) for f in investigation.figures}
    for turn in prior:
        supported |= numbers(turn.answer)
    for handle in handles:
        passage = investigation.passages.get(handle)
        if passage is not None:
            supported |= numbers(passage.text)
            if passage.page is not None:
                supported.add(Decimal(passage.page))
    for _, title in investigation.papers.values():
        supported |= numbers(title)
    if numbers(body) - supported:
        failures.add("unsupported_number")
    titles = investigation.titles()
    for match in _TITLE.finditer(body):
        title = next(value for value in match.groups() if value is not None).casefold().strip()
        if title not in titles:
            failures.add("unknown_title")
    for match in _INTRODUCED_TITLE.finditer(body):
        if match.group(1).casefold().strip() not in titles:
            failures.add("unknown_title")
    # Keyword search is a sample of matching passages, never the whole corpus.
    if _EXHAUSTIVE.search(body) or re.search(r"\bscreened\b", body, re.I):
        failures.add("completeness_overclaim")
    return tuple(sorted(failures))


def deliver(text: str, investigation: Investigation) -> tuple[str, tuple[Citation, ...]]:
    """Handles become [1], [2], ... in first-appearance order, each bound to its source."""
    handles = cited(text)
    numbering = {h: n for n, h in enumerate(handles, start=1)}
    answer = CITE.sub(lambda m: f"[{numbering[m.group(1)]}]", text)
    citations = tuple(
        Citation(record_id=p.record_id, quote=p.text, page=p.page, revision=p.source.revision)
        for p in (investigation.passages[h] for h in handles)
    )
    return answer, citations
