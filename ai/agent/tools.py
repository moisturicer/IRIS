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
from datetime import date
from typing import Optional

import asyncpg

from ai.agent.prompts import TOOL_DESCRIPTIONS as _SAYS, quoted
from ai.agent.protocol import ToolCall, ToolSpec
from ai.research import metadata, recency
from ai.research.tools import (
    MAX_DETAILS_PAPERS, OK, PARTIAL, UNAVAILABLE, Count, PaperDetails, PassageRef, Reading, ToolResult as Evidence,
    valid_filters,
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
SEARCH = ToolSpec("search", _SAYS["search"], _object(
    {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 20}}, ["query"]))
OPEN_PASSAGE = ToolSpec("open_passage", _SAYS["open_passage"], _object(
    {"passage": _HANDLE}, ["passage"]))
READ_PAGE = ToolSpec("read_page", _SAYS["read_page"], _object(
    {"paper": _HANDLE, "page": {"type": "integer"}}, ["paper", "page"]))
OUTLINE = ToolSpec("outline", _SAYS["outline"], _object(
    {"paper": _HANDLE}, ["paper"]))
UPDATE_PLAN = ToolSpec(
    "update_plan", _SAYS["update_plan"], _object({
        "steps": {"type": "array", "maxItems": PLAN_STEPS, "items": _object({
            "id": {"type": "string"}, "title": {"type": "string"},
            "status": {"type": "string", "enum": list(STEP_STATUS)},
        }, ["id", "title", "status"])},
    }, ["steps"]))
UPDATE_FOCUS = ToolSpec(
    "update_focus", _SAYS["update_focus"], _object({
        "selected": {"type": "array", "items": _HANDLE, "maxItems": FOCUS_PAPERS},
        "excluded": {"type": "array", "items": _HANDLE, "maxItems": FOCUS_PAPERS},
    }))
ASK_CLARIFICATION = ToolSpec(
    "ask_clarification", _SAYS["ask_clarification"],
    _object({"question": {"type": "string"}}, ["question"]))

RESOLVE_PAPERS = ToolSpec(
    "resolve_papers", _SAYS["resolve_papers"], _object({
        "references": {"type": "array", "maxItems": metadata.MAX_REFERENCES, "items": {"type": "string"}},
        "record_ids": {"type": "array", "maxItems": metadata.MAX_REFERENCES, "items": {"type": "integer"}},
    }))
_NAME = {"type": "string"}
_YEAR = {"type": "integer", "minimum": metadata.YEAR_RANGE[0], "maximum": metadata.YEAR_RANGE[1]}
COUNT_RECORDS = ToolSpec(
    "count_records", _SAYS["count_records"],
    _object({
        "classification": _NAME, "psced": _NAME, "record_type": _NAME,
        "year_from": _YEAR, "year_to": _YEAR, "is_ip": {"type": "boolean"},
        "group_by": {"type": "string", "enum": list(metadata.GROUPS)},
    }))

LIST_RECORDS = ToolSpec(
    "list_records", _SAYS["list_records"],
    _object({
        "classification": _NAME, "psced": _NAME, "record_type": _NAME,
        "year_from": _YEAR, "year_to": _YEAR, "is_ip": {"type": "boolean"},
        "offset": {"type": "integer", "minimum": 0},
    }))

#: research-5's search: keyword and meaning together, narrowed by metadata (IR-886).
HYBRID_SEARCH = ToolSpec(
    "search", _SAYS["hybrid_search"],
    _object({
        "query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 20},
        "classification": _NAME, "psced": _NAME, "record_type": _NAME,
        "year_from": _YEAR, "year_to": _YEAR,
    }, ["query"]))
#: Search signal outcomes the model is shown; any other reason is shown as unavailable.
SIGNALS = ("ok", "off", "provider_gated", "provider_failed", "embedding_space_changed")

READ_MANUSCRIPT = ToolSpec(
    "read_manuscript", _SAYS["read_manuscript"], _object(
        {"paper": _HANDLE, "continue_after": _HANDLE}, ["paper"]))

RECOVER_TURN = ToolSpec(
    "recover_turn", _SAYS["recover_turn"], _object({"turn": {"type": "integer", "minimum": 1}}, ["turn"]))

#: What the Publish form recorded for named papers, under the research-13 tool version (IR-1278).
PAPER_DETAILS = ToolSpec(
    "paper_details", _SAYS["paper_details"], _object({
        "papers": {"type": "array", "minItems": 1, "maxItems": MAX_DETAILS_PAPERS, "items": _HANDLE},
    }, ["papers"]))

#: research-14's tools: the three dates to filter, sort and group by (IR-1316).
_DAY = {"type": "string", "description": "YYYY-MM-DD"}
_DATE_FILTERS = {"year_from": _YEAR, "year_to": _YEAR, "published_from": _YEAR, "published_to": _YEAR,
                 "added_from": _DAY, "added_to": _DAY}
DATED_SEARCH = ToolSpec("search", _SAYS["dated_search"], _object({
    "query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 20},
    "classification": _NAME, "psced": _NAME, "record_type": _NAME, **_DATE_FILTERS,
}, ["query"]))
DATED_COUNT = ToolSpec("count_records", _SAYS["dated_count"], _object({
    "classification": _NAME, "psced": _NAME, "record_type": _NAME, **_DATE_FILTERS,
    "is_ip": {"type": "boolean"}, "group_by": {"type": "string", "enum": list(metadata.DATED_GROUPS)},
}))
DATED_LIST = ToolSpec("list_records", _SAYS["dated_list"], _object({
    "classification": _NAME, "psced": _NAME, "record_type": _NAME, **_DATE_FILTERS,
    "is_ip": {"type": "boolean"}, "sort": {"type": "string", "enum": list(metadata.SORTS)},
    "offset": {"type": "integer", "minimum": 0},
}))
DATED_DETAILS = ToolSpec("paper_details", _SAYS["dated_details"], PAPER_DETAILS.parameters)
SEARCHES, COUNTS = (HYBRID_SEARCH, DATED_SEARCH), (COUNT_RECORDS, DATED_COUNT)
LISTS, DETAILS = (LIST_RECORDS, DATED_LIST), (PAPER_DETAILS, DATED_DETAILS)

#: Read-only calls a tool group may fetch together (IR-1003). Not `read_manuscript`,
#: whose room depends on the results before it, nor plan, focus or clarification.
PREFETCHABLE = (SEARCH, HYBRID_SEARCH, OPEN_PASSAGE, READ_PAGE, OUTLINE, RESOLVE_PAPERS,
                COUNT_RECORDS, LIST_RECORDS, RECOVER_TURN, PAPER_DETAILS,
                DATED_SEARCH, DATED_COUNT, DATED_LIST, DATED_DETAILS)

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


def _handles(value) -> list[str]:
    """`paper_details`' paper handles, each once and in order; anything else is invalid (IR-1278)."""
    if not isinstance(value, list) or not 0 < len(value) <= MAX_DETAILS_PAPERS or not all(_str(h) for h in value):
        raise InvalidArguments
    return list(dict.fromkeys(value))


def shown_details(found: PaperDetails, *, dated: bool = False) -> dict:
    """One paper's recorded details as the model reads them (IR-1278)."""
    if dated:
        shown = shown_details(found)
        for name in ("year_completed", "year_accomplished"):
            del shown[name]
        return {**shown, "completion_year": found.completion_year,
                "date_added": found.date_added.isoformat() if found.date_added else None}
    return {
        "paper": found.handle, "title": found.title, "authors": list(found.authors), "adviser": found.adviser,
        "year_completed": found.year_completed, "year_accomplished": found.year_accomplished,
        "publication_year": found.publication_year, "record_type": found.record_type,
        "classification": found.classification, "psced": found.psced, "keywords": list(found.keywords),
        "abstract": found.abstract or None, "origin": found.origin, "is_ip": found.is_ip, "ip_type": found.ip_type,
        "for_commercialization": found.for_commercialization, "community_extension": found.community_extension,
        "requires_ethics_review": found.requires_ethics_review,
        "requested_offices": list(found.requested_offices),
    }


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
    #: Wrap paper text in the paper-text markers (the research-11 tool version, IR-1196).
    delimit: bool = False
    #: Offer paper_details (the research-13 tool version, IR-1278).
    details: bool = False
    #: The day the three dates are read on, under the research-14 tool version; None offers no dates (IR-1316).
    today: Optional[date] = None
    #: Recorded days, and the ends of ranges used, that an answer may state (IR-1316).
    dates: set[date] = field(default_factory=set)

    def specs(self) -> tuple[ToolSpec, ...]:
        extra = (ASK_CLARIFICATION,) if self.clarify else ()
        dated = self.today is not None
        search = DATED_SEARCH if dated else HYBRID_SEARCH
        research = (search, *RESEARCH[1:]) if self.hybrid else RESEARCH
        counting = (RESOLVE_PAPERS, DATED_COUNT) if dated else METADATA
        return (*research, *(counting if self.metadata else ()),
                *((DATED_LIST if dated else LIST_RECORDS,) if self.listing else ()),
                *((DATED_DETAILS if dated else PAPER_DETAILS,) if self.details else ()),
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

    def fetcher(self, call: ToolCall):
        """The read-only fetch `call` would make, to start early; None when it must wait its turn (IR-1003).

        Only reads whose outcome does not depend on the calls before them. The
        fetch changes nothing the model sees; `execute` folds it in call order.
        """
        spec = next((s for s in self.specs() if s.name == call.name), None)
        if spec is None or spec not in PREFETCHABLE:
            return None
        try:
            args = _arguments(call, spec)
        except InvalidArguments:
            return None
        return self._fetch(spec, args)

    async def _fetch(self, spec: ToolSpec, args: dict):
        if spec in COUNTS:
            filters = {k: v for k, v in args.items() if k != "group_by"}
            return await self.research.count(filters, args.get("group_by"))
        if spec in LISTS:
            return await self._list(args)
        if spec is RECOVER_TURN:
            if not _int(args["turn"]):
                raise InvalidArguments
            return await self.research.recover_turn(args["turn"])
        if spec in DETAILS:
            return await self.research.details(_handles(args["papers"]))
        return await self._research(spec, args)

    async def _list(self, args: dict):
        if ("offset" in args and (not _int(args["offset"]) or args["offset"] < 0)
                or "sort" in args and args["sort"] not in metadata.SORTS):
            raise InvalidArguments
        filters = {k: v for k, v in args.items() if k not in ("offset", "sort")}
        sort = {"sort": args["sort"]} if "sort" in args else {}
        if sort and self.today:
            self._recent()
        return await self.research.list_records(filters, offset=args.get("offset", 0), **sort)

    async def execute(self, call: ToolCall, *, room: int = 0, fetched=None) -> Outcome:
        """Run one call; `room` is the bytes a manuscript read may return (IR-733).

        `fetched` is a fetch `fetcher` started early; its result is folded here,
        exactly as if the call had run now (IR-1003).
        """
        self.tool_calls += 1
        spec = next((s for s in self.specs() if s.name == call.name), None)
        if spec is None:
            return Outcome(json.dumps({"error": "unknown_tool"}), control_only=True)
        try:
            args = _arguments(call, spec)
            if fetched is not None:
                raw = await fetched
                if spec in COUNTS:
                    return self._counted(raw)
                if spec in LISTS:
                    return self._listed(raw)
                if spec in DETAILS:
                    return self._detailed(raw, _handles(args["papers"]))
                return self._evidence(raw)
            if spec is UPDATE_PLAN:
                return await self._plan(args["steps"])
            if spec is UPDATE_FOCUS:
                return self._focus(args)
            if spec is ASK_CLARIFICATION:
                question = args["question"]
                if not _str(question) or len(question) > CLARIFICATION_CHARS:
                    raise InvalidArguments
                return Outcome("", clarification=question.strip())
            if spec in COUNTS:
                return self._counted(await self._fetch(spec, args))
            if spec in LISTS:
                return self._listed(await self._list(args))
            if spec in DETAILS:
                papers = _handles(args["papers"])
                return self._detailed(await self.research.details(papers), papers)
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
        if spec in SEARCHES:
            if not _str(args["query"]) or ("limit" in args and not _int(args["limit"])):
                raise InvalidArguments
            filters = {k: v for k, v in args.items() if k not in ("query", "limit")}
            if not valid_filters(filters):
                raise InvalidArguments
            self.searched = True
            if self.today:
                self._ranged(filters.items())
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
            body["papers"] = [{"paper": r.handle, "title": r.title, **self._dated(r)} for r in result.records]
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
                # Read as continuous text with the passage it continues (IR-397).
                **({"continues": passage.continues} if passage.continues else {}),
                # Context from the hit's section; search did not rank it (IR-1055).
                **({"section_context": True} if passage.section_mate else {}),
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
        if self.today and result.undated is not None:
            body["undated"] = result.undated
            self.figures.add(str(result.undated))
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
        return Outcome(self._dump(body), progress=new,
                       dependencies=result.dependencies,
                       control_only=not (result.dependencies or result.records
                                         or result.passages or result.sections))

    def _dump(self, body: dict) -> str:
        return json.dumps(_framed(body) if self.delimit else body, ensure_ascii=False)

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
            "papers": [{"paper": self.papers[r.record_id][0], "title": r.title,
                        **(self._dated(r) if self.today else {"year": r.year})} for r in result.records],
            **self._left_out(fact),
        }
        return Outcome(self._dump(body), progress=new, metadata_only=True)

    def _detailed(self, result: Evidence, requested: list[str]) -> Outcome:
        """What the submitter recorded for each readable paper: Record metadata, never Manuscript text (IR-1278).

        Its years may then be stated without a passage handle; they are kept in `figures`, so a
        resumed run (IR-724) allows the same. A number in the abstract still needs a cited passage.
        """
        body, _ = self._status(result)
        new = False
        for found in result.details:
            self.papers.setdefault(found.record_id, (found.handle, found.title))
            new = new or ("details", found.record_id) not in self.seen
            self.seen.add(("details", found.record_id))
            years = found.years if self.today is None else {found.completion_year, found.publication_year} - {None}
            self.figures.update(str(year) for year in years)
            # Catalogue names an answer may quote like titles (IR-750).
            self.terms.update(v.casefold() for v in (found.record_type, found.classification, found.psced) if v)
        if result.details:
            body["details"] = [shown_details(found, dated=self.today is not None) for found in result.details]
            for found in result.details if self.today else ():
                if found.date_added:
                    self._day(found.date_added)
            body["recorded_by"] = "submitter"
        returned = {found.handle for found in result.details}
        missing = [h for h in requested if h not in returned]
        if missing:
            body["not_found"] = missing
        if not result.details:
            return Outcome(json.dumps(body), control_only=True)
        return Outcome(self._dump(body), progress=new, metadata_only=True)

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
        # Dates a count was filtered by may be stated; they are not totals.
        self._ranged(fact.filters)
        self.terms.update(v.casefold() for name, v in fact.filters if name in metadata.TAXONOMIES)

    def _ranged(self, filters) -> None:
        """Let an answer state the date range it used, whose open end is today (IR-1316)."""
        used = [(name, v) for name, v in filters if name in (*metadata.YEARS, *metadata.DAYS)]
        for name, v in used:
            if name in metadata.YEARS:
                # "Before 2018" is a range ending in 2017, "after 2021" one starting in 2022.
                near = v - 1 if name.endswith("_from") else v + 1
                self.figures.update({str(v), str(near)} if self.today else {str(v)})
            else:
                self._day(date.fromisoformat(v))
        if used and self.today:
            self._recent()

    def _recent(self) -> None:
        """Let an answer state the recent ranges it was told, once a date is used (IR-1316)."""
        window = recency.window(self.today)
        self.figures.update(str(y) for y in window["recent_years"].values())
        for day in window["recent_added"].values():
            self._day(date.fromisoformat(day))

    def _day(self, day: date) -> None:
        self.dates.add(day)
        self.figures.add(str(day.year))

    def _dated(self, record) -> dict:
        """A paper's three dates, which an answer may then state; nothing on earlier pins (IR-1316)."""
        if self.today is None or record.added is None:
            return {}
        self.figures.update(str(y) for y in (record.year, record.publication_year) if y is not None)
        self._day(record.added)
        return {"completion_year": record.year, "publication_year": record.publication_year,
                "date_added": record.added.isoformat()}

    def _left_out(self, fact: Count) -> dict:
        if self.today is None or fact.undated is None:
            return {}
        self.figures.add(str(fact.undated))
        return {"undated": fact.undated}

    def _counted(self, result: Evidence) -> Outcome:
        """An exact count, typed for the model; the counted Records never leave the run (IR-750)."""
        body, fact = self._status(result)
        if fact is None:
            return Outcome(json.dumps(body), control_only=True)
        self._fact(fact)
        if fact.group_by in ("year", "publication_year"):
            self.figures.update(str(v) for v, _ in fact.groups)
        else:
            self.terms.update(str(v).casefold() for v, _ in fact.groups)
        body["count"] = {**counted(fact), **self._left_out(fact)}
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


#: Fields that carry text from a paper, or derived from one, wherever they appear (IR-1196).
#: A paper's abstract and Adviser came from its submitter, like its title (IR-1278).
_PAPER_TEXT = frozenset({"text", "title", "heading", "question", "answer", "abstract", "adviser"})
#: Lists whose every string a submitter typed: each item is quoted (IR-1278).
_PAPER_TEXT_LISTS = frozenset({"authors", "keywords"})


def _framed(value, key=None, within=None):
    """`value` with every paper-text field quoted; handles, ids and numbers untouched."""
    if isinstance(value, dict):
        return {k: _framed(v, k, key or within) for k, v in value.items()}
    if isinstance(value, list):
        return [_framed(v, None, key) for v in value]
    if isinstance(value, str) and (key in _PAPER_TEXT or (key == "section" and within == "passages")
                                   or (key is None and within in _PAPER_TEXT_LISTS)):
        return quoted(value)
    return value
