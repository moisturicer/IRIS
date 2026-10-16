"""The typed answer contract and its checks (IR-594, ADR-042, spec §5).

The answer model writes Markdown and may append one fenced ``bindings`` JSON
block naming the numbers and papers it states. Checks run per sentence, so a
failure removes that sentence rather than the answer. Passing a check is not
proof a claim is true; semantic quality stays human-reviewed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional, Sequence

from apps.ai.citation_markers import MARKER, numbers_in

#: Fenced, never repaired: the content may quote what the reader lost.
FENCED = frozenset({"source_withdrawn"})

_TRAILER = re.compile(r"```bindings[ \t]*\n(.*?)(?:\n```|\Z)", re.DOTALL)
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:,\d{3})*(?:\.\d+)?(?!\w)")
_WORD_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
_COUNT = re.compile(
    r"(?<![\w.])(\d+(?:,\d{3})*|" + "|".join(_WORD_NUMBERS) + r")\s+(?:[A-Za-z-]+\s+){0,2}?"
    r"(?:papers|records|studies|theses|documents|articles|publications)\b", re.I)
_PERCENT = re.compile(r"\s?(?:%|percent\b)")
_HANDLE = re.compile(r"\[(?:[ER]\d+|ref|source)[^\]]*\]", re.I)
_EXHAUSTIVE = re.compile(
    r"\b(?:all (?:of )?(?:the )?(?:papers|records|studies|theses)|every (?:paper|record|study|thesis)"
    r"|exhaustive(?:ly)?|complete (?:list|set|corpus)|the only (?:papers|records|studies|theses)"
    r"|no other (?:papers|records|studies|theses))\b", re.I)
# Presentation, not research figures: math, code, quotes, figure labels.
_HARMLESS = re.compile(
    r"\$\$.*?\$\$|\$[^$\n]+\$|`[^`\n]+`|“[^”\n]*”|\"[^\"\n]*\"|«[^»\n]*»"
    r"|\b(?:Figure|Fig\.|Table|Section|Chapter|Equation|Eq\.|Step|Appendix|Part|Phase|Stage)"
    r"\s*\(?\d+(?:\.\d+)*\)?", re.I)
_PREFIX = re.compile(r"\s*(?:#{1,6}\s+(?:\d+(?:\.\d+)*\.?\s+)?|[-*+]\s+|\d+[.)]\s+|>\s+)?")
_STOP = re.compile(r"[.!?](?:\s*\[[^\]\n]{1,24}\])*(?=\s+[A-Z*_\"“«(])")
_ABBREVIATION = re.compile(r"(?:\bet al|\be\.g|\bi\.e|\bvs|\bcf|\bFig|\bNo|\bEq)\.$", re.I)
_YEAR = re.compile(r"(?:19|20)\d{2}")
_BARE_PREFIX = re.compile(r"\s*(?:#{1,6}|[-*+]|\d+[.)]|>)?\s*")
_TABLE_RULE = re.compile(r"\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*")
_INTERNAL = re.compile(
    r"\b[a-z]+_[a-z_]+\b|\b(?:tools?|tool calls?|planner|lanes?|routing|router|route|classifier"
    r"|prompt|function calls?)\b|\bI (?:searched|called|ran|used|invoked|queried)\b", re.I)


@dataclass(frozen=True)
class Draft:
    text: str
    facts: tuple = ()
    papers: tuple = ()
    summary: str = ""
    malformed: bool = False


@dataclass(frozen=True)
class Unit:
    start: int
    end: int
    text: str
    verbatim: bool = False


@dataclass(frozen=True)
class Issue:
    code: str
    #: Index into `units(draft.text)`; None when no sentence carries it.
    unit: Optional[int]


def parse_draft(raw: str) -> Draft:
    """Split the answer from its bindings; the block never reaches a reader."""
    match = None
    for match in _TRAILER.finditer(raw):
        pass
    if match is None:
        return Draft(raw.strip())
    text = (raw[:match.start()] + raw[match.end():]).strip()
    try:
        data = json.loads(match.group(1))
    except ValueError:
        return Draft(text, malformed=True)
    facts, papers, summary = (data.get(k) if isinstance(data, dict) else None
                              for k in ("facts", "papers", "summary"))
    ok = (isinstance(data, dict) and _dicts(facts) and _dicts(papers)
          and isinstance(summary, (str, type(None))))
    if not ok:
        return Draft(text, malformed=True)
    return Draft(text, tuple(facts or ()), tuple(papers or ()), (summary or "").strip())


def _dicts(value) -> bool:
    return value is None or (isinstance(value, list) and all(isinstance(v, dict) for v in value))


def units(text: str) -> list[Unit]:
    """Sentences, table rows and verbatim math/code lines, with offsets."""
    out, pos, fenced = [], 0, None
    for line in text.splitlines(keepends=True):
        start, pos = pos, pos + len(line)
        body = line.rstrip("\r\n")
        stripped = body.strip()
        if not stripped:
            continue
        toggle = "```" if stripped.startswith("```") else "$$" if stripped == "$$" else None
        if fenced or toggle:
            out.append(Unit(start, start + len(body), body, verbatim=True))
            if toggle and fenced in (None, toggle):
                fenced = None if fenced else toggle
            continue
        if stripped.startswith("|"):
            out.append(Unit(start, start + len(body), body))
            continue
        cursor = _PREFIX.match(body).end()
        bounds = [m.end() for m in _STOP.finditer(body, cursor)
                  if not _ABBREVIATION.search(body[:m.start() + 1])] + [len(body)]
        for end in bounds:
            piece = body[cursor:end]
            lead = len(piece) - len(piece.lstrip())
            if piece.strip():
                out.append(Unit(start + cursor + lead, start + end, piece.strip()))
            cursor = end
    return out


def numbers(text: str) -> set[Decimal]:
    return {Decimal(m.group().replace(",", "")) for m in _NUMBER.finditer(text)}


def _value(raw) -> Optional[Decimal]:
    if isinstance(raw, bool):
        return None
    try:
        return Decimal(str(raw).replace(",", "").rstrip("%").strip())
    except (InvalidOperation, ValueError):
        return None


def _count_value(token: str) -> Decimal:
    word = _WORD_NUMBERS.get(token.lower())
    return Decimal(word) if word is not None else Decimal(token.replace(",", ""))


def _clean(text: str) -> str:
    return MARKER.sub(" ", _HARMLESS.sub(" ", text))


def check(draft: Draft, sources: Sequence, *, facts=(), limitations=(), live=None) -> tuple[Issue, ...]:
    """Issues in ``draft``: citation identity, access/version, numeric
    bindings and completeness. ``live`` holds chunk ids still readable and
    current; None means every source is."""
    live = {s.chunk_id for s in sources} if live is None else set(live)
    parts = units(draft.text)
    issues: list[Issue] = []
    if draft.malformed:
        issues.append(Issue("malformed_bindings", None))
    computed = set().union(*(numbers(json.dumps(f.get("value"), default=str)) for f in facts))
    exact = not limitations and any(
        (f.get("provenance") or {}).get("kind") == "metadata" for f in facts)

    def cited(unit):
        return [n for m in MARKER.finditer(unit.text) for n in numbers_in(m)]

    def holding(predicate):
        return [i for i, u in enumerate(parts) if not u.verbatim and predicate(u)] or [None]

    typed = set()
    for fact in draft.facts:
        value = _value(fact.get("value"))
        where = holding(lambda u: value is not None and value in numbers(_clean(u.text)))
        code = None
        if value is None:
            code = "wrong_binding"
        elif "source" in fact:
            n = fact["source"]
            if not isinstance(n, int) or not 1 <= n <= len(sources):
                code = "unknown_citation"
            elif sources[n - 1].chunk_id not in live:
                code = "source_withdrawn"
            else:
                content = sources[n - 1].content
                metric = str(fact.get("metric") or "").casefold()
                words = re.findall(r"[a-z0-9]{3,}", metric)
                elsewhere = any(cited(parts[i]) and n not in cited(parts[i])
                                for i in where if i is not None)
                if (value not in numbers(content) or elsewhere
                        or not all(w in content.casefold() for w in words)):
                    code = "wrong_binding"
        elif not any(f.get("name") == fact.get("fact")
                     and value in numbers(json.dumps(f.get("value"), default=str)) for f in facts):
            code = "wrong_binding"
        if code:
            issues.extend(Issue(code, i) for i in where)
        else:
            typed.add(value)

    for paper in draft.papers:
        title = str(paper.get("title") or "").casefold().strip()
        n = paper.get("source")
        where = holding(lambda u: bool(title) and title in u.text.casefold())
        if not isinstance(n, int) or not 1 <= n <= len(sources):
            issues.extend(Issue("unknown_citation", i) for i in where)
        elif sources[n - 1].record_title.casefold().strip() != title:
            issues.extend(Issue("wrong_binding", i) for i in where)

    for index, unit in enumerate(parts):
        if unit.verbatim:
            continue
        markers = cited(unit)
        valid = [n for n in markers if 1 <= n <= len(sources)]
        if len(valid) != len(markers) or _HANDLE.search(unit.text):
            issues.append(Issue("unknown_citation", index))
        if any(sources[n - 1].chunk_id not in live for n in valid):
            issues.append(Issue("source_withdrawn", index))
            continue
        clean = _clean(unit.text)
        pool = computed | typed
        for n in valid:
            pool |= numbers(sources[n - 1].content)
        records = len({sources[n - 1].record_id for n in valid})
        counted = []
        for match in _COUNT.finditer(clean):
            counted.append(match.span(1))
            value = _count_value(match.group(1))
            if value not in pool and value != records:
                issues.append(Issue("unsupported_count", index))
        for match in _NUMBER.finditer(clean):
            if any(a <= match.start() < b for a, b in counted):
                continue
            year = _YEAR.fullmatch(match.group())
            factual = (valid and not year) or "." in match.group() or _PERCENT.match(clean, match.end())
            if factual and Decimal(match.group().replace(",", "")) not in pool:
                issues.append(Issue("unsupported_number", index))
        if _EXHAUSTIVE.search(clean) and not exact:
            issues.append(Issue("completeness_overclaim", index))
    return tuple(dict.fromkeys(issues))


def without_units(text: str, drop: set[int]) -> str:
    """``text`` with the given units removed and the seams tidied."""
    parts = units(text)
    for index in sorted(drop, reverse=True):
        unit = parts[index]
        text = text[:unit.start] + text[unit.end:]
    lines = [line.rstrip() for line in text.splitlines()]
    lines = [line for line in lines if not line or not _BARE_PREFIX.fullmatch(line)]
    # A table left with no data rows loses its header too.
    for i in range(len(lines) - 1, 0, -1):
        rows_after = i + 1 < len(lines) and lines[i + 1].lstrip().startswith("|")
        if _TABLE_RULE.fullmatch(lines[i]) and not rows_after:
            del lines[i - 1:i + 1]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return re.sub(r"(?<=\S) {2,}", " ", text).strip()


#: Narration, markup and vendor names a reader-facing summary may not carry.
_NARRATION = re.compile(
    r"<\s*/?\s*\w[^>]*>|\b(?:I|we|let me|let's)\b|\b(?:searched|searching|calling|called|invoked"
    r"|queried|retrieved|fetched|looked up|tool|tools|step \d+)\b"
    r"|\b(?:openai|anthropic|groq|openrouter|voyage|gpt[\w.-]*|claude|gemini|llama|mistral"
    r"|deepseek|qwen)\b", re.I)
_QUOTED = re.compile(r"\"([^\"\n]+)\"|“([^”\n]+)”")
_SENTENCE_START = re.compile(r"(?:^|(?<=[.!?])\s+)(\S+)")
_CAPITALISED = re.compile(r"\b[A-Z][A-Za-z0-9-]*\b")


def _words(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-z0-9-]+", text)}


def safe_summary(summary: str, answer: str, evidence: str = "") -> str:
    """The analytical summary, or "" when it is not safe to show (spec §6.2).

    Deterministic, no model call. Dropped, never repaired, when it narrates
    tools or process, carries markup, citations or a vendor name, or states a
    number, quoted phrase or proper noun that neither the answer nor the cited
    passages (`evidence`) contain.
    """
    summary = (summary or "").strip()
    if (not summary or len(summary) > 600 or "[" in summary or "]" in summary
            or _INTERNAL.search(summary) or _NARRATION.search(summary)):
        return ""
    support = f"{answer}\n{evidence}"
    if not numbers(summary) <= numbers(support):
        return ""
    if any((a or b).lower() not in support.lower() for a, b in _QUOTED.findall(summary)):
        return ""
    starts = {m.start(1) for m in _SENTENCE_START.finditer(summary)}
    known = _words(support)
    for m in _CAPITALISED.finditer(summary):
        if m.start() not in starts and m.group().lower() not in known:
            return ""
    return summary
