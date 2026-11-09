"""The AGENT's tools for one run (IR-728, ADR-049 §9, §13, §16).

Research calls go to the local research tools (IR-719) and return original
evidence; no tool calls a model. Arguments name handles, never a reader,
scope or limit, and any undeclared key is refused. The plan and focus are
AI-owned run state that confers nothing.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import asyncpg

from ai.agent.protocol import ToolCall, ToolSpec
from ai.research import metadata
from ai.research.tools import (
    OK, PARTIAL, UNAVAILABLE, Count, PassageRef, Reading, ToolResult as Evidence, valid_filters,
)

log = logging.getLogger(__name__)

PLAN_STEPS = 12
FOCUS_PAPERS = 20
CLARIFICATION_CHARS = 500
STEP_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
STEP_STATUS = ("pending", "in_progress", "done", "blocked")
#: A run cannot continue past these; anything else is the model's to handle.
ENDS_RUN = ("unauthorized", "run_ended")
#: A tool that raised instead of answering: its result is unknown, never empty (IR-731).
TOOL_UNAVAILABLE = "tool_unavailable"
#: What a failed connection, timeout or database error raises; a local bug is not an outage.
OUTAGES = (OSError, asyncio.TimeoutError, asyncpg.PostgresError, asyncpg.InterfaceError)


def _object(properties: dict, required=()) -> dict:
    return {"type": "object", "properties": properties, "required": list(required),
            "additionalProperties": False}


_HANDLE = {"type": "string"}
SEARCH = ToolSpec("search", "Keyword search over the readable papers' passages.", _object(
    {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 20}}, ["query"]))
OPEN_PASSAGE = ToolSpec("open_passage", "Reread one passage by its handle.", _object(
    {"passage": _HANDLE}, ["passage"]))
READ_PAGE = ToolSpec("read_page", "Read the passages on one page of a paper.", _object(
    {"paper": _HANDLE, "page": {"type": "integer"}}, ["paper", "page"]))
OUTLINE = ToolSpec("outline", "List a paper's sections and their pages.", _object(
    {"paper": _HANDLE}, ["paper"]))
UPDATE_PLAN = ToolSpec(
    "update_plan", "Replace the task list for complex research. Keep every earlier step id.", _object({
        "steps": {"type": "array", "maxItems": PLAN_STEPS, "items": _object({
            "id": {"type": "string"}, "title": {"type": "string"},
            "status": {"type": "string", "enum": list(STEP_STATUS)},
        }, ["id", "title", "status"])},
    }, ["steps"]))
UPDATE_FOCUS = ToolSpec(
    "update_focus", "Record which papers the reader selected or excluded.", _object({
        "selected": {"type": "array", "items": _HANDLE, "maxItems": FOCUS_PAPERS},
        "excluded": {"type": "array", "items": _HANDLE, "maxItems": FOCUS_PAPERS},
    }))
ASK_CLARIFICATION = ToolSpec(
    "ask_clarification", "Ask the reader one question when ambiguity blocks useful research.",
    _object({"question": {"type": "string"}}, ["question"]))

RESOLVE_PAPERS = ToolSpec(
    "resolve_papers",
    "Turn papers the reader named, by title, short name or Record id, into paper handles. "
    "Several matches come back as candidates to ask the reader about.", _object({
        "references": {"type": "array", "maxItems": metadata.MAX_REFERENCES, "items": {"type": "string"}},
        "record_ids": {"type": "array", "maxItems": metadata.MAX_REFERENCES, "items": {"type": "integer"}},
    }))
_NAME = {"type": "string"}
_YEAR = {"type": "integer", "minimum": metadata.YEAR_RANGE[0], "maximum": metadata.YEAR_RANGE[1]}
COUNT_RECORDS = ToolSpec(
    "count_records",
    "Exactly how many papers this reader can see match metadata: Area (classification), PSCED "
    "area, record type, completion years or IP flag, optionally grouped. Cannot count by topic.",
    _object({
        "classification": _NAME, "psced": _NAME, "record_type": _NAME,
        "year_from": _YEAR, "year_to": _YEAR, "is_ip": {"type": "boolean"},
        "group_by": {"type": "string", "enum": list(metadata.GROUPS)},
    }))

LIST_RECORDS = ToolSpec(
    "list_records",
    "Every paper this reader can see that matches metadata: Area (classification), PSCED area, record "
    "type, completion years or IP flag, by title, with the exact total. Names at most 50 at a time and says "
    "when more remain; pass offset to continue from where the last page stopped. Cannot list by topic.",
    _object({
        "classification": _NAME, "psced": _NAME, "record_type": _NAME,
        "year_from": _YEAR, "year_to": _YEAR, "is_ip": {"type": "boolean"},
        "offset": {"type": "integer", "minimum": 0},
    }))

#: research-5's search: keyword and meaning together, narrowed by metadata (IR-886).
HYBRID_SEARCH = ToolSpec(
    "search",
    "Search the readable papers' passages by keyword and by meaning, optionally narrowed by Area "
    "(classification), PSCED area, record type or completion years. Returns a sample of matching "
    "passages, never all of them, and says when meaning search was unavailable.",
    _object({
        "query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 20},
        "classification": _NAME, "psced": _NAME, "record_type": _NAME,
        "year_from": _YEAR, "year_to": _YEAR,
    }, ["query"]))
#: Search signal outcomes the model is shown; any other reason is shown as unavailable.
SIGNALS = ("ok", "off", "provider_gated", "provider_failed", "embedding_space_changed")

READ_MANUSCRIPT = ToolSpec(
    "read_manuscript",
    "Read a paper's extracted text in document order, as much as fits now, with what was not read. "
    "Pass the continue_after handle a read returned to go on where it stopped.", _object(
        {"paper": _HANDLE, "continue_after": _HANDLE}, ["paper"]))

RECOVER_TURN = ToolSpec(
    "recover_turn",
    "Read one earlier Turn of this conversation again exactly as it was answered, by its number, with "
    "fresh handles for the passages it cited. Use it when the reader asks for an exact detail from an "
    "earlier Turn, such as one a compacted summary mentions.", _object({"turn": {"type": "integer", "minimum": 1}},
                                                                       ["turn"]))

RESEARCH = (SEARCH, OPEN_PASSAGE, READ_PAGE, OUTLINE)
#: Named papers and exact counts, offered only under the research-2 tool version (IR-750).
METADATA = (RESOLVE_PAPERS, COUNT_RECORDS)
#: Whole-Manuscript reading, offered only under the research-3 tool version (IR-733).
MANUSCRIPTS = (READ_MANUSCRIPT,)
#: Original-Turn recovery, offered only under the research-4 tool version (IR-735).
RECOVERY = (RECOVER_TURN,)


class InvalidArguments(Exception):
    pass


class RunEnded(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Outcome:
    content: str
    #: Whether the call returned evidence this run had not seen.
    progress: bool = False
    clarification: Optional[str] = None
    dependencies: frozenset = frozenset()
    control_only: bool = False
    metadata_only: bool = False


def _str(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _int(value) -> bool:
    return type(value) is int


def _arguments(call: ToolCall, spec: ToolSpec) -> dict:
    try:
        args = json.loads(call.arguments or "{}")
    except ValueError:
        raise InvalidArguments from None
    schema = spec.parameters
    if not isinstance(args, dict) or set(args) - set(schema["properties"]):
        raise InvalidArguments
    if any(name not in args for name in schema["required"]):
        raise InvalidArguments
    return args


def counted(fact: Count) -> dict:
    """An exact count as the model and the reader see it: no Record ids."""
    return {
        "kind": "exact_count", "total": fact.total, "filters": dict(fact.filters),
        "group_by": fact.group_by, "groups": [{"value": v, "count": n} for v, n in fact.groups],
        "ungrouped": fact.ungrouped,
        "scope": "paper_chat" if fact.scope_record_id is not None else "readable_records",
        "relative_to": fact.relative_to,
    }


def _key(passage: PassageRef) -> tuple:
    return (passage.source.revision, passage.page, hashlib.sha256(passage.text.encode()).hexdigest())


def _ranges(positions) -> list[list[int]]:
    """Sorted positions as [first, last] runs."""
    runs: list[list[int]] = []
    for n in sorted(positions):
        if runs and runs[-1][1] == n - 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    return runs


@dataclass
class ManuscriptRead:
    """One Manuscript revision as this run has read it (IR-733).

    Inspected is what a tool returned; visible is what the model was shown,
    which packing may have withheld; the rest is recoverable by its handles
    while the run lasts and the source stands.
    """

    record_id: int
    title: str
    reading: Reading
    #: Position (1-based, document order) -> passage handle.
    handles: dict[int, str] = field(default_factory=dict)
    visible: set[int] = field(default_factory=set)

    @property
    def inspected(self) -> set[int]:
        return set(self.handles)

    @property
    def recoverable(self) -> set[int]:
        return self.inspected - self.visible

    @property
    def complete(self) -> bool:
        return len(self.handles) == self.reading.passages

    def summary(self) -> dict:
        return {
            "passages": self.reading.passages, "read": _ranges(self.inspected),
            "not_read": _ranges(set(range(1, self.reading.passages + 1)) - self.inspected),
        }


@dataclass
class Investigation:
    """Everything one run has read, planned and been told; nothing outlives the run."""

    research: object
    clarify: bool = False
    #: Offer resolve_papers and count_records (the research-2 tool version).
    metadata: bool = False
    #: Offer read_manuscript (the research-3 tool version, IR-733).
    manuscripts: bool = False
    #: Offer recover_turn (the research-4 tool version, IR-735).
    recovery: bool = False
    #: Search by keyword and meaning with metadata filters (the research-5 tool version, IR-886).
    hybrid: bool = False
    #: Offer list_records (the research-6 and research-7 tool versions, IR-994).
    listing: bool = False
    #: Original Turns this run recovered: ordinal -> answer, whose numbers were checked when delivered.
    recovered: dict[int, str] = field(default_factory=dict)
    #: Passage handle -> what was shown for it.
    passages: dict[str, PassageRef] = field(default_factory=dict)
    #: Record id -> (paper handle, title).
    papers: dict[int, tuple[str, str]] = field(default_factory=dict)
    #: Numbers the tools computed (coverage), which an answer may state.
    figures: set[str] = field(default_factory=set)
    #: Evidence reads that returned something.
    reads: int = 0
    plan: tuple[dict, ...] = ()
    plan_revision: int = 0
    selected: Optional[tuple[int, ...]] = None
    excluded: Optional[tuple[int, ...]] = None
    seen: set = field(default_factory=set)
    tool_calls: int = 0
    #: Exact counts this run computed, in order (IR-750).
    counts: list[Count] = field(default_factory=list)
    #: Those counts' totals: the only numbers a completeness claim may rest on.
    exact: set[str] = field(default_factory=set)
    #: Taxonomy names those counts used, casefolded, which an answer may quote.
    terms: set[str] = field(default_factory=set)
    searched: bool = False
    #: Manuscript revision -> what this run read of it (IR-733).
    readings: dict[str, ManuscriptRead] = field(default_factory=dict)
    #: Tool call id -> (revision, positions) a read returned, until packing says whether it was shown.
    unpacked: dict[str, tuple[str, tuple[int, ...]]] = field(default_factory=dict)
    #: Tools that failed during the run, in order of first failure (IR-731).
    outages: list[str] = field(default_factory=list)
    recalled_sources: frozenset = frozenset()

    def specs(self) -> tuple[ToolSpec, ...]:
        extra = (ASK_CLARIFICATION,) if self.clarify else ()
        research = (HYBRID_SEARCH, *RESEARCH[1:]) if self.hybrid else RESEARCH
        return (*research, *(METADATA if self.metadata else ()), *((LIST_RECORDS,) if self.listing else ()),
                *(MANUSCRIPTS if self.manuscripts else ()), *(RECOVERY if self.recovery else ()),
                UPDATE_PLAN, UPDATE_FOCUS, *extra)

    @property
    def researched(self) -> bool:
        return self.reads > 0

    def titles(self) -> set[str]:
        return {title.casefold().strip() for _, title in self.papers.values()}

    def paper(self, handle) -> Optional[int]:
        return next((rid for rid, (h, _) in self.papers.items() if h == handle), None)

    async def recall(self, state: dict, *, also=()) -> dict:
        """Fresh handles for the papers the Conversation showed, still readable now.

        `also` names more Records to give handles to in the same read, such as
        a compact handoff's (IR-734); the state message describes `state` only.
        """
        ids = [*state.get("shown", ()), *state.get("selected", ()), *state.get("excluded", ()), *also]
        if not ids:
            return {}
        found = await self.research.recall(list(dict.fromkeys(ids)))
        self._ended(found)
        self.recalled_sources = found.dependencies
        for record in found.records:
            self.papers[record.record_id] = (record.handle, record.title)

        def listed(name):
            return [self.papers[i][0] for i in state.get(name, ()) if i in self.papers]

        shown = [{"position": n, "paper": self.papers[i][0], "title": self.papers[i][1]}
                 for n, i in enumerate((i for i in state.get("shown", ()) if i in self.papers), start=1)]
        return {"shown": shown, "selected": listed("selected"), "excluded": listed("excluded")}

    async def execute(self, call: ToolCall, *, room: int = 0) -> Outcome:
        """Run one call; `room` is the bytes a manuscript read may return (IR-733)."""
        self.tool_calls += 1
        spec = next((s for s in self.specs() if s.name == call.name), None)
        if spec is None:
            return Outcome(json.dumps({"error": "unknown_tool"}), control_only=True)
        try:
            args = _arguments(call, spec)
            if spec is UPDATE_PLAN:
                return await self._plan(args["steps"])
            if spec is UPDATE_FOCUS:
                return self._focus(args)
            if spec is ASK_CLARIFICATION:
                question = args["question"]
                if not _str(question) or len(question) > CLARIFICATION_CHARS:
                    raise InvalidArguments
                return Outcome("", clarification=question.strip())
            if spec is COUNT_RECORDS:
                filters = {k: v for k, v in args.items() if k != "group_by"}
                return self._counted(await self.research.count(filters, args.get("group_by")))
            if spec is LIST_RECORDS:
                offset = args.get("offset", 0)
                if "offset" in args and (not _int(offset) or offset < 0):
                    raise InvalidArguments
                filters = {k: v for k, v in args.items() if k != "offset"}
                return self._listed(await self.research.list_records(filters, offset=offset))
            if spec is READ_MANUSCRIPT:
                return self._evidence(await self._read(args, room), call.id)
            if spec is RECOVER_TURN:
                if not _int(args["turn"]):
                    raise InvalidArguments
                return self._evidence(await self.research.recover_turn(args["turn"]))
            return self._evidence(await self._research(spec, args))
        except InvalidArguments:
            return Outcome(json.dumps({"error": "invalid_arguments"}), control_only=True)
        except asyncpg.InsufficientPrivilegeError:
            # A policy refusal is not an outage: the reader may no longer read.
            raise RunEnded("unauthorized") from None
        except OUTAGES as failure:
            # An outage leaves what was already read; the model is told the result is unknown.
            log.warning("agent tool %s failed: %s", spec.name, type(failure).__name__)
            if spec.name not in self.outages:
                self.outages.append(spec.name)
            return Outcome(json.dumps({"status": UNAVAILABLE, "reason": TOOL_UNAVAILABLE}), control_only=True)


    async def _research(self, spec: ToolSpec, args: dict) -> Evidence:
        if spec is HYBRID_SEARCH:
            if not _str(args["query"]) or ("limit" in args and not _int(args["limit"])):
                raise InvalidArguments
            filters = {k: v for k, v in args.items() if k not in ("query", "limit")}
            if not valid_filters(filters):
                raise InvalidArguments
            self.searched = True
            return await self.research.hybrid_search(args["query"], args.get("limit", 10), filters)
        if spec is SEARCH:
            if not _str(args["query"]) or ("limit" in args and not _int(args["limit"])):
                raise InvalidArguments
            self.searched = True
            return await self.research.search(args["query"], args.get("limit", 10))
        if spec is RESOLVE_PAPERS:
            references, record_ids = args.get("references", []), args.get("record_ids", [])
            if not (isinstance(references, list) and isinstance(record_ids, list)
                    and all(_str(r) for r in references) and all(_int(i) for i in record_ids)):
                raise InvalidArguments
            return await self.research.resolve(references, record_ids)
        if spec is OPEN_PASSAGE:
            if not _str(args["passage"]):
                raise InvalidArguments
            return await self.research.open_passage(args["passage"])
        if not _str(args["paper"]) or (spec is READ_PAGE and not _int(args["page"])):
            raise InvalidArguments
        if spec is READ_PAGE:
            return await self.research.read_page(args["paper"], args["page"])
        return await self.research.outline(args["paper"])

    async def _read(self, args: dict, room: int) -> Evidence:
        after = args.get("continue_after")
        if not _str(args["paper"]) or (after is not None and not _str(after)):
            raise InvalidArguments
        return await self.research.read_manuscript(args["paper"], after, max_bytes=max(1, room))

    def packed(self, results) -> None:
        """Record which reads the model was shown: a withheld result was inspected, not seen (IR-733)."""
        for result in results:
            pending = self.unpacked.pop(result.call_id, None)
            if pending is None:
                continue
            try:
                body = json.loads(result.content)
            except ValueError:
                body = None
            withheld = isinstance(body, dict) and "withheld" in body
            if not withheld:
                revision, positions = pending
                self.readings[revision].visible.update(positions)

    def reshown(self, contents) -> None:
        """Keep as shown only the Manuscript passages whose handle is still in a result the model has (IR-736).

        Compaction takes whole exchanges out of the history; what they showed
        is then inspected and recoverable by its handles, not shown.
        """
        contents = list(contents)
        for read in self.readings.values():
            read.visible = {n for n, handle in read.handles.items() if any(handle in c for c in contents)}

    def _ended(self, result: Evidence) -> None:
        if result.reason in ENDS_RUN:
            raise RunEnded(result.reason)

    def _evidence(self, result: Evidence, call_id: Optional[str] = None) -> Outcome:
        self._ended(result)
        new = False
        body: dict = {"status": result.status}
        if result.reason:
            body["reason"] = result.reason
        if result.status in (OK, PARTIAL):
            self.reads += 1
        for record in result.records:
            self.papers.setdefault(record.record_id, (record.handle, record.title))
            new = new or ("paper", record.record_id) not in self.seen
            self.seen.add(("paper", record.record_id))
        if result.matches:
            body["matches"] = [{
                "reference": m.reference, "kind": m.kind, "match": m.match,
                **({"basis": m.basis} if m.basis else {}),
                "papers": [{"paper": r.handle, "title": r.title} for r in m.records],
            } for m in result.matches]
        elif result.records:
            body["papers"] = [{"paper": r.handle, "title": r.title} for r in result.records]
        if result.passages:
            body["passages"] = []
        for passage in result.passages:
            self.passages[passage.handle] = passage
            key = _key(passage)
            new = new or key not in self.seen
            self.seen.add(key)
            paper = self.papers.get(passage.record_id)
            # Text repeated from the previous passage is shown once; the passage keeps all of it.
            body["passages"].append({
                "passage": passage.handle, "paper": paper[0] if paper else None,
                "page": passage.page, "section": passage.section, "text": passage.text[passage.overlap:],
                **({"repeats_previous_chars": passage.overlap} if passage.overlap else {}),
            })
        if result.turn is not None:
            turn = result.turn
            self.recovered[turn.ordinal] = turn.answer
            new = new or ("turn", turn.ordinal) not in self.seen
            self.seen.add(("turn", turn.ordinal))
            # The original words, with its citations as this run's handles: never a summary.
            body["turn"] = {"turn": turn.ordinal, "question": turn.question, "answer": turn.answer,
                            "kind": turn.kind, "truncated": turn.truncated}
        if result.reading is not None:
            new = self._read_into(result, call_id, body) or new
        if result.sections:
            outline = ("outline", *sorted(d.revision for d in result.dependencies))
            new = new or outline not in self.seen
            self.seen.add(outline)
            body["sections"] = [{"section": s.section, "heading": s.heading, "level": s.level,
                                 "first_page": s.first_page, "last_page": s.last_page}
                                for s in result.sections]
        if result.signals:
            # How the search ran, so a keyword-only result is never read as a meaning search (IR-886).
            body["search"] = {name: value if value in SIGNALS else UNAVAILABLE for name, value in result.signals}
        coverage = result.coverage
        body["coverage"] = {"returned": coverage.returned, "total": coverage.total,
                            "truncated": coverage.truncated}
        self.figures.update(str(n) for n in (coverage.returned, coverage.total) if n is not None)
        return Outcome(json.dumps(body, ensure_ascii=False), progress=new,
                       dependencies=result.dependencies,
                       control_only=not (result.dependencies or result.records
                                         or result.passages or result.sections))

    def _read_into(self, result: Evidence, call_id: Optional[str], body: dict) -> bool:
        """Fold one manuscript read into the run's coverage and say it to the model (IR-733)."""
        reading = result.reading
        (source,) = result.dependencies
        read = self.readings.get(source.revision)
        if read is None:
            read = self.readings[source.revision] = ManuscriptRead(source.record_id, reading.title, reading)
        read.reading = reading
        start = reading.covered.first if reading.covered else 0
        positions = tuple(range(start, start + len(result.passages)))
        before = read.inspected
        read.handles.update(zip(positions, (p.handle for p in result.passages)))
        if call_id is not None and positions:
            self.unpacked[call_id] = (source.revision, positions)

        def span(s):
            return {"passages": [s.first, s.last], "pages": [s.first_page, s.last_page]}

        body["reading"] = {
            "covered": span(reading.covered) if reading.covered else None,
            "missing": [span(m) for m in reading.missing],
            "read_so_far": read.summary(),
            "pages": reading.pages, "pages_no_passage_starts_on": list(reading.pages_no_passage_starts_on),
            "formula_passages": reading.formulas, "caption_passages": reading.captions,
            # Extracted text only: what a figure or formula shows is never interpreted.
            "visual_content": "not_interpreted",
            "repeated_chars_omitted": reading.overlap_chars,
            "continue_after": reading.continue_after,
        }
        self.figures.update(str(n) for n in (
            reading.passages, reading.pages, reading.formulas, reading.captions, len(read.inspected),
            *reading.pages_no_passage_starts_on,
            *(n for s in (reading.covered, *reading.missing) if s
              for n in (s.first, s.last, s.first_page, s.last_page)),
        ) if n is not None)
        return read.inspected != before

    def _listed(self, result: Evidence) -> Outcome:
        """Every matching paper by title and handle, with the exact total: metadata only (IR-994)."""
        body, fact = self._status(result)
        if fact is None:
            return Outcome(json.dumps(body), control_only=True)
        self._fact(fact)
        new = False
        for record in result.records:
            self.papers.setdefault(record.record_id, (record.handle, record.title))
            new = new or ("paper", record.record_id) not in self.seen
            self.seen.add(("paper", record.record_id))
        body["list"] = {
            "kind": "record_list", "total": fact.total, "filters": dict(fact.filters),
            "truncated": result.coverage.truncated, "relative_to": fact.relative_to,
            "papers": [{"paper": self.papers[r.record_id][0], "title": r.title, "year": r.year}
                       for r in result.records],
        }
        return Outcome(json.dumps(body, ensure_ascii=False), progress=new, metadata_only=True)

    def _status(self, result: Evidence) -> tuple[dict, Optional[Count]]:
        self._ended(result)
        body: dict = {"status": result.status}
        if result.reason:
            body["reason"] = result.reason
        return body, result.count

    def _fact(self, fact: Count) -> None:
        """Record an exact count whose total and filter names an answer may state."""
        self.counts.append(fact)
        # Only the total speaks for the whole population; a group or remainder never does.
        self.exact.add(str(fact.total))
        self.figures.update(str(n) for n in fact.figures)
        # Years a count was filtered by may be stated; they are not totals.
        self.figures.update(str(v) for name, v in fact.filters if name in ("year_from", "year_to"))
        self.terms.update(v.casefold() for _, v in fact.filters if isinstance(v, str))

    def _counted(self, result: Evidence) -> Outcome:
        """An exact count, typed for the model; the counted Records never leave the run (IR-750)."""
        body, fact = self._status(result)
        if fact is None:
            return Outcome(json.dumps(body), control_only=True)
        self._fact(fact)
        if fact.group_by == "year":
            self.figures.update(str(v) for v, _ in fact.groups)
        else:
            self.terms.update(str(v).casefold() for v, _ in fact.groups)
        body["count"] = counted(fact)
        key = ("count", fact.filters, fact.group_by)
        new = key not in self.seen
        self.seen.add(key)
        return Outcome(json.dumps(body, ensure_ascii=False), progress=new, metadata_only=True)

    async def _plan(self, steps) -> Outcome:
        if not isinstance(steps, list) or len(steps) > PLAN_STEPS:
            raise InvalidArguments
        cleaned = []
        for step in steps:
            if not (isinstance(step, dict) and set(step) == {"id", "title", "status"}):
                raise InvalidArguments
            if not (isinstance(step["id"], str) and STEP_ID.match(step["id"])
                    and _str(step["title"]) and len(step["title"]) <= 120
                    and step["status"] in STEP_STATUS):
                raise InvalidArguments
            cleaned.append({"id": step["id"], "title": step["title"].strip(), "status": step["status"]})
        ids = [s["id"] for s in cleaned]
        # Step ids are stable: none is reused or dropped once shown.
        if len(set(ids)) != len(ids) or not {s["id"] for s in self.plan} <= set(ids):
            raise InvalidArguments
        self.plan = tuple(cleaned)
        self.plan_revision += 1
        # Execution counts come from the application, not the model.
        if not await self.research.journal("plan", {
            "revision": self.plan_revision, "steps": list(self.plan),
            # Calls run before this one.
            "executed": {"tool_calls": self.tool_calls - 1, "evidence_reads": self.reads},
        }):
            raise RunEnded("run_ended")
        return Outcome(json.dumps({"status": "ok", "revision": self.plan_revision}),
                       control_only=True)

    def _focus(self, args: dict) -> Outcome:
        chosen = {}
        for name in ("selected", "excluded"):
            if name not in args:
                continue
            handles = args[name]
            if not isinstance(handles, list) or len(handles) > FOCUS_PAPERS:
                raise InvalidArguments
            ids = [self.paper(h) for h in handles]
            if None in ids:
                raise InvalidArguments
            chosen[name] = tuple(dict.fromkeys(ids))
        if "selected" in chosen:
            self.selected = chosen["selected"]
        if "excluded" in chosen:
            self.excluded = chosen["excluded"]
        return Outcome(json.dumps({"status": "ok"}), control_only=True)
