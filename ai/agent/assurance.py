"""Deterministic checks on the AGENT's drafts (IR-728, IR-729, ADR-049 §15).

The rules of Django's research validation (`apps.ai.research.validation`,
IR-512), applied to passage handles: cited handles must be ones this run
was shown, numbers must come from cited text or tool coverage, marked
titles must be papers the run saw, and completeness is never claimed from
keyword search. They catch literal mistakes, never prove a claim true.
A failing draft gets the failing items back as feedback for one repair; a
failing repair keeps only the sentences that pass on their own citations.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Optional

from ai.agent.tools import Investigation, counted
from ai.research.tools import Count
from ai.runs.executor import Citation

CITE = re.compile(r"\[(P[0-9a-f]{20})\]")
_MARKER = re.compile(r"\[\d+\]")
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
_LINE = re.compile(r"\n+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def numbers(text: str) -> set[Decimal]:
    values = {Decimal(m.group().replace(",", "")) for m in _NUMBER.finditer(text)}
    values.update(Decimal(_WORD_NUMBERS[m.group().lower()]) for m in _WORDS.finditer(text))
    return values


def cited(text: str) -> list[str]:
    """Cited passage handles in order of first appearance."""
    return list(dict.fromkeys(CITE.findall(text)))


def findings(text: str, investigation: Investigation, *, prior=(), excluded=()) -> dict[str, list[str]]:
    """Each failing rule's code and the draft's own items that broke it, in order.

    `prior` Turns were checked when delivered, so their numbers count as supported.
    """
    found: dict[str, list[str]] = {}

    def fail(code, item):
        items = found.setdefault(code, [])
        if item not in items:
            items.append(item)

    handles = cited(text)
    for h in handles:
        if h not in investigation.passages:
            fail("unknown_citation", f"[{h}]")
        elif investigation.passages[h].record_id in excluded:
            fail("excluded_citation", f"[{h}]")
    body = CITE.sub("", text)
    # Passage handles are the only citation namespace.
    for label in re.findall(r"\[[^\]\n]+\]", body):
        fail("unknown_citation", label)
    # A question answered with no repository context is general background.
    if not (investigation.researched or investigation.papers or investigation.counts):
        return found
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
    for value in sorted(numbers(body) - supported):
        fail("unsupported_number", format(value, "f"))
    # Area and other catalogue names an exact count used may be quoted like titles (IR-750).
    titles = investigation.titles() | investigation.terms
    for match in _TITLE.finditer(body):
        title = next(value for value in match.groups() if value is not None).strip()
        if title.casefold() not in titles:
            fail("unknown_title", title)
    for match in _INTRODUCED_TITLE.finditer(body):
        if match.group(1).casefold().strip() not in titles:
            fail("unknown_title", match.group(1).strip())
    # Keyword search is a sample of matching passages, never the whole corpus; only a
    # sentence stating an exact count's own figure may speak of a total (IR-750).
    exact = {Decimal(f) for f in investigation.exact}
    for line in _LINE.split(body.strip()):
        for sentence in _SENTENCE.split(line):
            if numbers(sentence) & exact:
                continue
            for match in _EXHAUSTIVE.finditer(sentence):
                fail("completeness_overclaim", match.group())
    for match in re.finditer(r"\bscreened\b", body, re.I):
        fail("completeness_overclaim", match.group())
    return found


def check(text: str, investigation: Investigation, *, prior=(), excluded=()) -> tuple[str, ...]:
    """Reason codes only; none carries content."""
    return tuple(sorted(findings(text, investigation, prior=prior, excluded=excluded)))


#: What the model is told to fix, per rule; the codes themselves never reach it or the reader.
_FEEDBACK = {
    "unknown_citation": "Cite only passage handles this conversation returned, in square brackets, "
                        "and use no other brackets. Not valid: {items}.",
    "excluded_citation": "The reader ruled out the papers behind {items}; do not cite them.",
    "unsupported_number": "These numbers are not stated in the passages you cited, their pages, the paper "
                          "titles or the search coverage: {items}. Correct each one from a passage you "
                          "cite, or leave it out.",
    "unknown_title": "These are not titles of papers you read: {items}. Name only papers this "
                     "conversation returned, exactly as titled.",
    "completeness_overclaim": "A search returns a sample of matching passages, never the whole "
                              "repository; remove claims of completeness such as {items}. State a "
                              "total only in the sentence giving the exact figure count_records returned.",
}
_ITEMS = 8
_ITEM_CHARS = 80
REPAIR_NOTE = (
    "[IRIS validation] Your draft was not delivered because it failed these checks. Rewrite the whole "
    "answer once, keeping every supported finding with its citation. This is your last turn."
)


def feedback(found: dict[str, list[str]]) -> str:
    """Actionable instructions for the one repair, naming the draft's own failing items."""
    lines = [REPAIR_NOTE]
    for code in sorted(found):
        items = ", ".join(repr(item[:_ITEM_CHARS]) for item in found[code][:_ITEMS])
        lines.append("- " + _FEEDBACK[code].format(items=items))
    return "\n".join(lines)


_LEADING_CITES = re.compile(r"(?:\[P[0-9a-f]{20}\]\s*)+")
LIMITATION = "Part of the drafted answer could not be checked against its sources and was left out."


def _sentences(line: str) -> list[str]:
    """Sentences, each keeping citations placed after its full stop; a citation never stands alone."""
    units: list[str] = []
    for piece in _SENTENCE.split(line.strip()):
        lead = _LEADING_CITES.match(piece)
        if lead and units:
            units[-1] = f"{units[-1]} {lead.group().strip()}"
            piece = piece[lead.end():]
        if piece.strip():
            units.append(piece)
    return units


def supported_units(text: str, investigation: Investigation, *, prior=(), excluded=()) -> Optional[str]:
    """The draft's sentences that cite a passage and pass every check on their own, or None.

    Each kept sentence is supported by its own citations alone; nothing is reworded.
    """
    lines = []
    for line in _LINE.split(text.strip()):
        kept = [unit for unit in _sentences(line)
                if cited(unit) and not check(unit, investigation, prior=prior, excluded=excluded)]
        if kept:
            lines.append(" ".join(kept))
    return "\n".join(lines) if lines else None


def stated_counts(answer: str, investigation: Investigation) -> list[Count]:
    """The latest count per question whose total or group size the answer states (IR-750)."""
    # Citation handles and delivered [n] markers are not numbers the answer states.
    stated = numbers(_MARKER.sub("", CITE.sub("", answer)))
    latest: dict = {}
    for fact in investigation.counts:
        latest[(fact.filters, fact.group_by, fact.scope_record_id)] = fact
    return [fact for fact in latest.values() if stated & {Decimal(n) for n in fact.stated}]


def facts(answer: str, citations, investigation: Investigation) -> tuple[dict, ...]:
    """What kind of number the delivered answer rests on, kept with its Turn (IR-750).

    A stated exact count is kept with the Records it counted, so a reopen can withhold
    it once any is no longer readable. A cited keyword search is a sample, never exhaustive.
    """
    kept = []
    for fact in stated_counts(answer, investigation):
        stored = counted(fact)
        stored.pop("scope")
        kept.append({**stored, "scope_record_id": fact.scope_record_id,
                     "population": sorted(fact.population)})
    if investigation.searched and citations:
        papers = len({c.record_id for c in citations})
        kept.append({"kind": "keyword_sample", "papers": papers, "exhaustive": False})
    kept += reading_coverage(citations, investigation)
    return tuple(kept)


def reading_coverage(citations, investigation: Investigation) -> list[dict]:
    """How much of each cited Manuscript the run read, and what text cannot show (IR-733).

    Never a claim of exhaustive research, nor of a figure or formula interpreted.
    """
    cited_revisions = {c.revision for c in citations}
    return [{
        "kind": "reading_coverage", "title": read.title, "passages": read.reading.passages,
        "read": len(read.inspected), "complete": read.complete, "pages": read.reading.pages,
        "pages_no_passage_starts_on": len(read.reading.pages_no_passage_starts_on),
        "formula_passages": read.reading.formulas, "caption_passages": read.reading.captions,
        "visual_interpretation": False, "exhaustive": False,
    } for revision, read in investigation.reads.items() if revision in cited_revisions]


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
