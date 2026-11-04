"""An AGENT investigation's completed steps, saved and restored (IR-724, ADR-049 §12, §14, §20).

After each completed step -- a model turn and every result of its tool
group -- a run saves the whole ordered Conversation with its stable call ids,
the source pointers its Investigation holds, the task and context it is
answering, its pin and bounds, and what it has spent. A replacement worker
restores it only while all of that still matches; `ResearchTools.reauthorize`
then rechecks every recovered source under the run's own grant. Restored
state confers nothing: an answer is still checked and its sources rechecked
before delivery.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Optional

from ai.agent.protocol import (
    AgentRequest, BrokenExchange, IncompatibleContinuation, ModelTurn, Opaque, Pin, StopReason, Text,
    ToolCall, ToolGroup, ToolResult, User, check_history,
)
from ai.agent.tools import Investigation, ManuscriptRead
from ai.research.tools import Count, PassageRef, Reading, Source, Span

#: -2 adds the compact handoff the history opens with (IR-734); a -1 body is rebuilt, never misread.
FORMAT = "agent-checkpoint-2"


def task_key(question: str, prior, state: dict, *, handoff: Optional[int] = None) -> str:
    """What the run is answering: the reader's words and the Conversation they follow.

    `handoff` is the compact handoff revision the Conversation opens with (IR-734).
    """
    body = json.dumps({
        "question": question,
        "prior": [[t.question, t.answer, t.kind] for t in prior],
        "state": state or {},
        **({"handoff": handoff} if handoff is not None else {}),
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode()).hexdigest()


# --- The Conversation --------------------------------------------------------------

def _item(item) -> dict:
    if isinstance(item, Text):
        return {"t": "text", "text": item.text}
    if isinstance(item, ToolGroup):
        return {"t": "tools", "calls": [{"id": c.id, "name": c.name, "arguments": c.arguments}
                                        for c in item.calls]}
    # Kept unread, to travel back only under the binding that produced it.
    return {"t": "opaque", "binding": list(item.binding), "field": item.field, "payload": item.payload}


def _entry(entry) -> dict:
    if isinstance(entry, User):
        return {"t": "user", "text": entry.text}
    if isinstance(entry, ToolResult):
        return {"t": "result", "call_id": entry.call_id, "content": entry.content}
    return {"t": "model", "stop": entry.stop.value, "reasoned": entry.reasoned,
            "input_tokens": entry.input_tokens, "output_tokens": entry.output_tokens,
            "items": [_item(i) for i in entry.items]}


def _load_item(raw: dict):
    kind = raw["t"]
    if kind == "text":
        return Text(raw["text"])
    if kind == "tools":
        return ToolGroup(tuple(ToolCall(c["id"], c["name"], c["arguments"]) for c in raw["calls"]))
    if kind == "opaque":
        return Opaque(binding=tuple(raw["binding"]), field=raw["field"], payload=raw["payload"])
    raise ValueError(kind)


def _load_entry(raw: dict):
    kind = raw["t"]
    if kind == "user":
        return User(raw["text"])
    if kind == "result":
        return ToolResult(raw["call_id"], raw["content"])
    if kind == "model":
        return ModelTurn(items=tuple(_load_item(i) for i in raw["items"]), stop=StopReason(raw["stop"]),
                         reasoned=bool(raw["reasoned"]), input_tokens=raw["input_tokens"],
                         output_tokens=raw["output_tokens"])
    raise ValueError(kind)


def _complete(pin: Pin, history: list) -> bool:
    """Every tool group answered, in order, and every artifact under this pin's binding."""
    try:
        check_history(AgentRequest(pin=pin, instructions="", history=tuple(history)))
    except (BrokenExchange, IncompatibleContinuation):
        return False
    pending: list[str] = []
    for entry in history:
        if isinstance(entry, ModelTurn):
            pending = [c.id for i in entry.items if isinstance(i, ToolGroup) for c in i.calls]
        elif isinstance(entry, ToolResult) and pending:
            pending.pop(0)
    return not pending


# --- The Investigation -------------------------------------------------------------

def _tuples(value):
    return tuple(_tuples(v) for v in value) if isinstance(value, list) else value


def _count(fact: Count) -> dict:
    return {"total": fact.total, "filters": [list(f) for f in fact.filters], "group_by": fact.group_by,
            "groups": [list(g) for g in fact.groups], "ungrouped": fact.ungrouped,
            "scope_record_id": fact.scope_record_id, "population": sorted(fact.population),
            "relative_to": fact.relative_to}


def _load_count(raw: dict) -> Count:
    return Count(total=raw["total"], filters=_tuples(raw["filters"]), group_by=raw["group_by"],
                 groups=_tuples(raw["groups"]), ungrouped=raw["ungrouped"],
                 scope_record_id=raw["scope_record_id"], population=frozenset(raw["population"]),
                 relative_to=raw["relative_to"])


def _investigation(found: Investigation) -> dict:
    return {
        "passages": [{"handle": p.handle, "record_id": p.record_id, "page": p.page, "section": p.section,
                      "text": p.text, "source": asdict(p.source), "overlap": p.overlap}
                     for p in found.passages.values()],
        "papers": [[rid, handle, title] for rid, (handle, title) in found.papers.items()],
        "figures": sorted(found.figures), "exact": sorted(found.exact), "terms": sorted(found.terms),
        "reads": found.reads, "plan": list(found.plan), "plan_revision": found.plan_revision,
        "selected": list(found.selected) if found.selected is not None else None,
        "excluded": list(found.excluded) if found.excluded is not None else None,
        "seen": sorted((list(k) for k in found.seen), key=json.dumps),
        "tool_calls": found.tool_calls, "counts": [_count(c) for c in found.counts],
        "searched": found.searched, "outages": list(found.outages),
        "readings": {revision: _reading(read) for revision, read in found.readings.items()},
    }


def _restore_investigation(found: Investigation, raw: dict) -> None:
    found.passages = {p["handle"]: PassageRef(p["handle"], p["record_id"], p["page"], p["section"], p["text"],
                                              Source(**p["source"]), int(p.get("overlap", 0)))
                      for p in raw["passages"]}
    found.papers = {int(rid): (handle, title) for rid, handle, title in raw["papers"]}
    found.figures, found.exact, found.terms = set(raw["figures"]), set(raw["exact"]), set(raw["terms"])
    found.reads = int(raw["reads"])
    found.plan = tuple(dict(s) for s in raw["plan"])
    found.plan_revision = int(raw["plan_revision"])
    found.selected = tuple(raw["selected"]) if raw["selected"] is not None else None
    found.excluded = tuple(raw["excluded"]) if raw["excluded"] is not None else None
    found.seen = {_tuples(k) for k in raw["seen"]}
    found.tool_calls = int(raw["tool_calls"])
    found.counts = [_load_count(c) for c in raw["counts"]]
    found.searched = bool(raw["searched"])
    # A tool that failed before the takeover still qualifies the answer (IR-731).
    found.outages = [str(name) for name in raw["outages"]]
    # What the run read of each Manuscript, so a resumed answer reports the same coverage (IR-733).
    found.readings = {str(revision): _load_reading(read) for revision, read in raw.get("readings", {}).items()}


def _span(span: Optional[Span]) -> Optional[list]:
    return None if span is None else [span.first, span.last, span.first_page, span.last_page]


def _load_span(raw) -> Optional[Span]:
    return None if raw is None else Span(*raw)


def _reading(read: ManuscriptRead) -> dict:
    r = read.reading
    return {
        "record_id": read.record_id, "title": read.title,
        "handles": [[n, h] for n, h in sorted(read.handles.items())], "visible": sorted(read.visible),
        "reading": {"passages": r.passages, "covered": _span(r.covered),
                    "missing": [_span(s) for s in r.missing], "pages": r.pages,
                    "pages_no_passage_starts_on": list(r.pages_no_passage_starts_on),
                    "formulas": r.formulas, "captions": r.captions, "overlap_chars": r.overlap_chars,
                    "continue_after": r.continue_after, "title": r.title},
    }


def _load_reading(raw: dict) -> ManuscriptRead:
    r = raw["reading"]
    reading = Reading(passages=int(r["passages"]), covered=_load_span(r["covered"]),
                      missing=tuple(_load_span(s) for s in r["missing"]), pages=r["pages"],
                      pages_no_passage_starts_on=tuple(r["pages_no_passage_starts_on"]),
                      formulas=int(r["formulas"]), captions=int(r["captions"]),
                      overlap_chars=int(r["overlap_chars"]), continue_after=r["continue_after"],
                      title=r["title"])
    return ManuscriptRead(int(raw["record_id"]), raw["title"], reading,
                          handles={int(n): h for n, h in raw["handles"]}, visible={int(n) for n in raw["visible"]})


# --- Saving and restoring ----------------------------------------------------------

@dataclass(frozen=True)
class Restored:
    history: list
    steps: int
    stale: int
    budget: dict
    investigation: dict
    #: The handoff the history opens with: `revision`, `through`, `carried` and `body`, or None (IR-734).
    compaction: Optional[dict] = None

    def handles(self) -> list[str]:
        """Every handle the restored Investigation may cite or read again."""
        return [*(p["handle"] for p in self.investigation["passages"]),
                *(handle for _, handle, _ in self.investigation["papers"])]

    def counted(self) -> list[int]:
        return [i for c in self.investigation["counts"] for i in c["population"]]

    def apply(self, found: Investigation) -> None:
        _restore_investigation(found, self.investigation)


def dump(*, pin: Pin, bounds, task: str, history, investigation: Investigation, budget,
         steps: int, stale: int, compaction: Optional[dict] = None) -> dict:
    return {
        "compaction": compaction,
        "format": FORMAT,
        "pin": pin.as_dict(), "bounds": asdict(bounds) if bounds is not None else None,
        "task": task, "steps": steps, "stale": stale,
        "budget": {"input": budget.input, "output": budget.output, "reported": budget.reported,
                   "attempts": budget.attempts},
        "history": [_entry(e) for e in history],
        "investigation": _investigation(investigation),
    }


def load(body, *, pin: Pin, bounds, task: str) -> Optional[Restored]:
    """The saved step, or None when it is not this run's to continue unchanged."""
    if not isinstance(body, dict) or body.get("format") != FORMAT:
        return None
    if body.get("pin") != pin.as_dict() or body.get("task") != task:
        return None
    if body.get("bounds") != (asdict(bounds) if bounds is not None else None):
        return None
    try:
        history = [_load_entry(e) for e in body["history"]]
        restored = Restored(history=history, steps=int(body["steps"]), stale=int(body["stale"]),
                            budget={k: int(body["budget"][k]) for k in ("input", "output", "reported", "attempts")},
                            investigation=body["investigation"], compaction=body.get("compaction"))
        # Parsed in full now, so a malformed body is refused before anything is applied.
        _restore_investigation(Investigation(None), restored.investigation)
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    if restored.steps < 1 or not _complete(pin, history):
        return None
    return restored
