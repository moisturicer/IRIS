"""Deterministic checks on the AGENT's drafts (IR-728, IR-729, ADR-049 §15).

The rules of Django's research validation (`apps.ai.research.validation`, retired
in IR-957; IR-512), applied to passage handles: cited handles must be ones this run
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
from ai.research.metadata import fold
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
    r"|complete (?:list|corpus)|only \d+ (?:papers|records|studies)"
    # A search is a sample, so it is never complete or comprehensive (IR-731).
    r"|(?<!not a )(?<!not an )(?:complete|comprehensive|exhaustive) (?:literature )?search|search(?:ed|ing)? (?:all|every))\b", re.I)
#: A claim that nothing matched, which a failed tool can never support (IR-731).
_ABSENCE = re.compile(
    r"\b(?:no|zero|0)\s+(?!(?:more|less|fewer)\b)(?:[\w-]+\s+){0,2}?(?:papers?|records?|stud(?:y|ies)|theses|thesis|matches|results)\b"
    r"|\bnone\b|\bnothing\b", re.I)
_LINE = re.compile(r"\n+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def numbers(text: str) -> set[Decimal]:
    values = {Decimal(m.group().replace(",", "")) for m in _NUMBER.finditer(text)}
    values.update(Decimal(_WORD_NUMBERS[m.group().lower()]) for m in _WORDS.finditer(text))
    return values


def cited(text: str) -> list[str]:
    """Cited passage handles in order of first appearance."""
    return list(dict.fromkeys(CITE.findall(text)))


def findings(text: str, investigation: Investigation, *, prior=(), excluded=(),
             clarification: bool = False) -> dict[str, list[str]]:
    """Each failing rule's code and the draft's own items that broke it, in order.

    `prior` Turns were checked when delivered, so their numbers count as supported. A
    `clarification` asks the reader a question, so it states no absence (IR-731).
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
    # A question answered with no repository context is general background; one whose
    # research failed is not, and its claims are still checked (IR-731).
    if not (investigation.researched or investigation.papers or investigation.counts
            or investigation.outages):
        return found
    supported = {Decimal(f) for f in investigation.figures}
    for turn in prior:
        supported |= numbers(turn.answer)
    # An original Turn this run recovered was checked when delivered (IR-735).
    for answer in investigation.recovered.values():
        supported |= numbers(answer)
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
    titles = {fold(t) for t in investigation.titles() | investigation.terms}
    for match in _TITLE.finditer(body):
        title = next(value for value in match.groups() if value is not None).strip()
        if fold(title) not in titles:
            fail("unknown_title", title)
    for match in _INTRODUCED_TITLE.finditer(body):
        if fold(match.group(1)) not in titles:
            fail("unknown_title", match.group(1).strip())
    # Keyword search is a sample of matching passages, never the whole corpus; only a
    # sentence stating an exact count's own figure may speak of a total (IR-750).
    exact = {Decimal(f) for f in investigation.exact}
    for line in _LINE.split(body.strip()):
        for sentence in _SENTENCE.split(line):
            stated = numbers(sentence) & exact
            if not stated:
                for match in _EXHAUSTIVE.finditer(sentence):
                    fail("completeness_overclaim", match.group())
            # A failed tool's result is unknown: only an exact zero may say nothing matched (IR-731).
            if investigation.outages and not clarification and Decimal(0) not in stated:
                for match in _ABSENCE.finditer(sentence):
                    fail("outage_absence", match.group())
    for match in re.finditer(r"\bscreened\b", body, re.I):
        fail("completeness_overclaim", match.group())
    return found


def check(text: str, investigation: Investigation, *, prior=(), excluded=()) -> tuple[str, ...]:
    """Reason codes only; none carries content."""
    return tuple(sorted(findings(text, investigation, prior=prior, excluded=excluded)))


#: What the model is told to fix, per rule; the codes themselves never reach it or the reader.
_FEEDBACK = {
    "unknown_citation": "Cite only passage handles this conversation returned, in square brackets, "
                        "and use no other brackets. Not valid: {items}. If a passage you read supports "
                        "the claim, cite that one; otherwise remove the claim or say the sources read "
                        "do not establish it.",
    "excluded_citation": "The reader ruled out the papers behind {items}; do not cite them. Remove "
                         "what only they supported.",
    "unsupported_number": "These numbers are not stated in the passages you cited, their pages, the paper "
                          "titles or the search coverage: {items}. If a passage you read states the "
                          "number, cite it; otherwise remove the number, or say the sources read do not "
                          "give it.",
    "unknown_title": "These are not titles of papers you read: {items}. If you read the paper, give its "
                     "exact title; otherwise name only papers this conversation returned, or say the "
                     "sources read do not establish it.",
    "outage_absence": "A research step failed, so its result is unknown, not empty; do not say that "
                      "nothing matched, such as {items}. Say what could not be checked instead.",
    "completeness_overclaim": "A search returns a sample of matching passages, never the whole "
                              "repository; qualify claims of completeness such as {items} as what "
                              "the search found. State a total only in the sentence giving the exact "
                              "figure count_records returned.",
}
_ITEMS = 8
_ITEM_CHARS = 80
REPAIR_NOTE = (
    "[IRIS validation] Your draft failed these checks. Rewrite the whole answer once. For each item: "
    "correct it if a passage you read supports it; otherwise remove the claim, qualify it, or say the "
    "sources read do not establish it. Keep everything else, with its citations. Do not refuse or "
    "shorten the answer as a whole; answer as fully as the passages allow. This is your last turn."
)


def feedback(found: dict[str, list[str]]) -> str:
    """Actionable instructions for the one repair, naming the draft's own failing items."""
    lines = [REPAIR_NOTE]
    for code in sorted(found):
        items = ", ".join(repr(item[:_ITEM_CHARS]) for item in found[code][:_ITEMS])
        lines.append("- " + _FEEDBACK[code].format(items=items))
    return "\n".join(lines)


_LEADING_CITES = re.compile(r"(?:\[P[0-9a-f]{20}\]\s*)+")
LIMITATION = "The sources IRIS read do not establish the rest of what was drafted, so it is left out."


#: What each tool does, in the reader's words, for the outage limitation (IR-731).
_STEPS = {
    "search": "searching passages", "open_passage": "rereading a passage", "read_page": "reading a page",
    "outline": "listing a paper's sections", "resolve_papers": "finding a named paper",
    "count_records": "counting records", "recover_turn": "rereading an earlier answer", "update_plan": "updating the research plan",
}


def outage_limitation(outages) -> str:
    """The fixed line a delivered answer ends with when a research step failed."""
    steps = ", ".join(_STEPS.get(name, "a research step") for name in outages)
    return (f"A research step failed while this answer was prepared ({steps}), so it covers only "
            "what could be read and is not a complete search.")


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
        # Read, but condensed or withheld before the answer: said only when it happened (IR-736).
        **({"not_in_context": len(read.recoverable)} if read.recoverable else {}),
    } for revision, read in investigation.readings.items() if revision in cited_revisions]


QUALIFIER = "(the sources read do not establish this)"
UNESTABLISHED = "The sources IRIS read do not establish an answer to this question."


def _claims(text: str, investigation: Investigation, *, prior=(), excluded=()) -> bool:
    """Whether `text` still fails a check, ignoring a whole number no larger than the papers read (a list count)."""
    found = dict(findings(text, investigation, prior=prior, excluded=excluded))
    listed = len(investigation.papers)
    numbers_left = [n for n in found.pop("unsupported_number", []) if not (n.isdigit() and 0 < int(n) <= listed)]
    return bool(numbers_left or found)


def qualified(text: str, investigation: Investigation, *, prior=(), excluded=()) -> str:
    """`text` whole: citations that bind to no passage are removed, and a sentence that still fails
    the checks without them (an unsupported number or title) is kept but marked as not established.
    """
    out = []
    for line in _LINE.split(text.strip()):
        units = []
        for unit in _sentences(line):
            if not check(unit, investigation, prior=prior, excluded=excluded):
                units.append(unit)
                continue
            cleaned = bindable(unit, investigation, excluded=excluded)
            # A bad citation alone is just removed; the sentence is qualified only if it still fails.
            still = cleaned and _claims(cleaned, investigation, prior=prior, excluded=excluded)
            units.append(f"{cleaned} {QUALIFIER}" if still else cleaned)
        out.append(" ".join(u for u in units if u))
    return "\n".join(line for line in out if line)


def unmatched_note(found: dict[str, list[str]]) -> str:
    """One line naming the numbers and paper titles a delivered answer states that no passage supports."""
    items = list(found.get("unsupported_number", [])) + [f"\u201c{item}\u201d" for item in found.get("unknown_title", [])]
    if not items:
        return ""
    shown = ", ".join(item[:_ITEM_CHARS] for item in items[:5])
    more = f" and {len(items) - 5} more" if len(items) > 5 else ""
    return f"*The sources IRIS read do not establish: {shown}{more}.*"


_MARKER_LIKE = re.compile(r"\[(?!P[0-9a-f]{20}\])(?:\d+|P[0-9A-Za-z]*)(?:\s*[,–-]\s*\d+)*\]")


def bindable(text: str, investigation: Investigation, *, excluded=()) -> str:
    """`text` without citations that name no passage of this run or a paper the reader ruled out."""
    def keep(match: re.Match) -> str:
        passage = investigation.passages.get(match.group(1))
        return match.group(0) if passage is not None and passage.record_id not in excluded else ""
    # A number or handle the model typed in brackets reads as a citation but points at nothing.
    text = _MARKER_LIKE.sub("", CITE.sub(keep, text))
    # A removed citation leaves no gap before the punctuation that followed it.
    return re.sub(r"[ \t]+([.,;:!?])", r"\1", re.sub(r"[ \t]{2,}", " ", text)).strip()


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
