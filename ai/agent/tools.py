"""The AGENT's tools for one run (IR-728, ADR-049 §9, §13, §16).

Research calls go to the local research tools (IR-719) and return original
evidence; no tool calls a model. Arguments name handles, never a reader,
scope or limit, and any undeclared key is refused. The plan and focus are
AI-owned run state that confers nothing.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Optional

from ai.agent.protocol import ToolCall, ToolSpec
from ai.research.tools import OK, PARTIAL, PassageRef, ToolResult as Evidence

PLAN_STEPS = 12
FOCUS_PAPERS = 20
CLARIFICATION_CHARS = 500
STEP_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
STEP_STATUS = ("pending", "in_progress", "done", "blocked")
#: A run cannot continue past these; anything else is the model's to handle.
ENDS_RUN = ("unauthorized", "run_ended")


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

RESEARCH = (SEARCH, OPEN_PASSAGE, READ_PAGE, OUTLINE)


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


def _key(passage: PassageRef) -> tuple:
    return (passage.source.revision, passage.page, hashlib.sha256(passage.text.encode()).hexdigest())


@dataclass
class Investigation:
    """Everything one run has read, planned and been told; nothing outlives the run."""

    research: object
    clarify: bool = False
    #: Passage handle -> what was shown for it.
    passages: dict[str, PassageRef] = field(default_factory=dict)
    #: Record id -> (paper handle, title).
    papers: dict[int, tuple[str, str]] = field(default_factory=dict)
    #: Numbers the tools computed (coverage), which an answer may state.
    figures: set[str] = field(default_factory=set)
    results: list[Evidence] = field(default_factory=list)
    plan: tuple[dict, ...] = ()
    plan_revision: int = 0
    selected: Optional[tuple[int, ...]] = None
    excluded: Optional[tuple[int, ...]] = None
    seen: set = field(default_factory=set)
    tool_calls: int = 0

    def specs(self) -> tuple[ToolSpec, ...]:
        extra = (ASK_CLARIFICATION,) if self.clarify else ()
        return (*RESEARCH, UPDATE_PLAN, UPDATE_FOCUS, *extra)

    @property
    def researched(self) -> bool:
        return bool(self.results)

    def titles(self) -> set[str]:
        return {title.casefold().strip() for _, title in self.papers.values()}

    def paper(self, handle) -> Optional[int]:
        return next((rid for rid, (h, _) in self.papers.items() if h == handle), None)

    async def recall(self, state: dict) -> dict:
        """Fresh handles for the papers the Conversation showed, still readable now."""
        ids = [*state.get("shown", ()), *state.get("selected", ()), *state.get("excluded", ())]
        if not ids:
            return {}
        found = await self.research.recall(list(dict.fromkeys(ids)))
        self._ended(found)
        for record in found.records:
            self.papers[record.record_id] = (record.handle, record.title)

        def listed(name):
            return [self.papers[i][0] for i in state.get(name, ()) if i in self.papers]

        shown = [{"position": n, "paper": self.papers[i][0], "title": self.papers[i][1]}
                 for n, i in enumerate((i for i in state.get("shown", ()) if i in self.papers), start=1)]
        return {"shown": shown, "selected": listed("selected"), "excluded": listed("excluded")}

    async def execute(self, call: ToolCall) -> Outcome:
        self.tool_calls += 1
        spec = next((s for s in self.specs() if s.name == call.name), None)
        if spec is None:
            return Outcome(json.dumps({"error": "unknown_tool"}))
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
            return self._evidence(await self._research(spec, args))
        except InvalidArguments:
            return Outcome(json.dumps({"error": "invalid_arguments"}))

    async def _research(self, spec: ToolSpec, args: dict) -> Evidence:
        if spec is SEARCH:
            if not _str(args["query"]) or ("limit" in args and not _int(args["limit"])):
                raise InvalidArguments
            return await self.research.search(args["query"], args.get("limit", 10))
        if spec is OPEN_PASSAGE:
            if not _str(args["passage"]):
                raise InvalidArguments
            return await self.research.open_passage(args["passage"])
        if not _str(args["paper"]) or (spec is READ_PAGE and not _int(args["page"])):
            raise InvalidArguments
        if spec is READ_PAGE:
            return await self.research.read_page(args["paper"], args["page"])
        return await self.research.outline(args["paper"])

    def _ended(self, result: Evidence) -> None:
        if result.reason in ENDS_RUN:
            raise RunEnded(result.reason)

    def _evidence(self, result: Evidence) -> Outcome:
        self._ended(result)
        new = False
        body: dict = {"status": result.status}
        if result.reason:
            body["reason"] = result.reason
        if result.status in (OK, PARTIAL):
            self.results.append(result)
        for record in result.records:
            self.papers.setdefault(record.record_id, (record.handle, record.title))
        if result.records:
            body["papers"] = [{"paper": r.handle, "title": r.title} for r in result.records]
        if result.passages:
            body["passages"] = []
        for passage in result.passages:
            self.passages[passage.handle] = passage
            key = _key(passage)
            new = new or key not in self.seen
            self.seen.add(key)
            paper = self.papers.get(passage.record_id)
            body["passages"].append({
                "passage": passage.handle, "paper": paper[0] if paper else None,
                "page": passage.page, "section": passage.section, "text": passage.text,
            })
        if result.sections:
            outline = ("outline", *sorted(d.revision for d in result.dependencies))
            new = new or outline not in self.seen
            self.seen.add(outline)
            body["sections"] = [{"section": s.section, "heading": s.heading, "level": s.level,
                                 "first_page": s.first_page, "last_page": s.last_page}
                                for s in result.sections]
        coverage = result.coverage
        body["coverage"] = {"returned": coverage.returned, "total": coverage.total,
                            "truncated": coverage.truncated}
        self.figures.update(str(n) for n in (coverage.returned, coverage.total) if n is not None)
        return Outcome(json.dumps(body, ensure_ascii=False), progress=new)

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
            "executed": {"tool_calls": self.tool_calls - 1, "evidence_reads": len(self.results)},
        }):
            raise RunEnded("run_ended")
        return Outcome(json.dumps({"status": "ok", "revision": self.plan_revision}))

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
        return Outcome(json.dumps({"status": "ok"}))
