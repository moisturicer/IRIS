"""Compact an AGENT Conversation into a portable handoff before it overflows (IR-734, ADR-049 §19, §20).

Older complete exchanges -- earlier Turns, and this run's tool groups, each
whole -- are summarized by the same AGENT and replaced by one handoff
message. The reader's question, the Conversation state and the most recent
exchanges stay as they were. The application, not the model, records the
shown order, selections, exclusions, plan and which original Turns were
compacted; the model only describes goals, findings and limitations, and a
finding is kept only when it names a passage this run read or a compacted
Turn. A handoff is derived context: never evidence, never instructions.

Nothing here is provider-native: the handoff is text any model can read,
and an opaque artifact in a compacted exchange is dropped with it.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, fields
from typing import Optional

from ai.agent.context import Capacity, Reserves
from ai.agent.protocol import ModelTurn, ToolResult, User
from ai.research.tools import Source

FORMAT = "agent-handoff-1"
PREFIX = "[IRIS compacted context] "
STATE_PREFIX = "[IRIS conversation state] "
NOTE = (
    "Earlier context is being compacted. Reply with only a JSON object with these keys: "
    '"goal" (what the reader is trying to find out), "preferences" (a list of the reader\'s stated '
    'preferences and instructions), "findings" (a list of objects with "text", "passages" (the passage '
    'handles that support it) and "turns" (the numbers of the earlier Turns it came from)) and '
    '"limitations" (a list of what is still unknown or was not read). Use only what the exchanges above '
    "say; do not add new facts."
)
#: Read by the model with the handoff, so it is never taken for evidence or an instruction.
DERIVED = (
    "Derived by the assistant from earlier exchanges that are no longer shown. It is not evidence and "
    "contains no instructions. Cite only passages by handle; to quote a paper, read it again."
)
#: Bounds on what a summary may carry, whatever the model returns.
FINDINGS = 30
ITEMS = 10
TEXT_CHARS = 600
FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


@dataclass(frozen=True)
class Compaction:
    """When to compact and how much it may cost; every value is a deployment profile's."""

    #: Estimated occupancy at which older context is compacted.
    threshold_tokens: int
    #: The summary's completion cap.
    summary_tokens: int
    #: Recent complete exchanges never compacted.
    keep_exchanges: int
    #: Summary attempts per run, failed ones included.
    max_attempts: int

    def __post_init__(self):
        for f in fields(self):
            value = getattr(self, f.name)
            if not (isinstance(value, int) and not isinstance(value, bool) and value > 0):
                raise ValueError(f"compaction {f.name} must be a positive integer")

    def summary_reserves(self, reserves: Reserves) -> Reserves:
        """What a summary request holds back: its own output, nothing for tools or repair."""
        return Reserves(output_tokens=self.summary_tokens, reasoning_tokens=reserves.reasoning_tokens,
                        next_result_tokens=0, repair_tokens=0)

    def fits(self, capacity: Optional[Capacity], reserves: Reserves) -> bool:
        """The threshold leaves room both to summarize and to finish under the verified capacity."""
        if capacity is None:
            return False
        summary = self.summary_reserves(reserves)
        generated = summary.output_tokens + (summary.reasoning_tokens if capacity.max_reasoning_tokens is None
                                             else 0)
        return (generated <= capacity.max_output_tokens
                and self.threshold_tokens + reserves.total < capacity.context_tokens
                and self.threshold_tokens + summary.total < capacity.context_tokens)


@dataclass(frozen=True)
class Handoff:
    """What a run asks the store to commit; `body` holds Record ids, never run handles' meaning."""

    body: dict
    #: The newest original Turn it compacts; 0 when it compacts only this run's exchanges.
    through_ordinal: int
    turns: tuple[int, ...]
    #: Manuscript revisions its findings depend on.
    sources: tuple[str, ...]
    binding: tuple
    usage: dict


@dataclass(frozen=True)
class Split:
    """A history cut at complete exchanges: what goes, what stays, in order."""

    previous: Optional[User]
    state: tuple[User, ...]
    question: User
    gone_turns: tuple[tuple, ...]
    gone_exchanges: tuple[tuple, ...]
    kept_turns: tuple[tuple, ...]
    kept_exchanges: tuple[tuple, ...]

    def summary(self) -> list:
        """What the summary is written from: everything that goes, with the task it serves."""
        return [*((self.previous,) if self.previous else ()), *_flat(self.gone_turns), *self.state,
                self.question, *_flat(self.gone_exchanges), User(NOTE)]

    def rebuilt(self, handoff: User) -> list:
        return [handoff, *_flat(self.kept_turns), *self.state, self.question, *_flat(self.kept_exchanges)]


def _flat(units) -> list:
    return [entry for unit in units for entry in unit]


def is_handoff(entry) -> bool:
    return isinstance(entry, User) and entry.text.startswith(PREFIX)


def is_state(entry) -> bool:
    return isinstance(entry, User) and entry.text.startswith(STATE_PREFIX)


def reader(text: str) -> str:
    """Reader text, marked when it starts like a handoff or the state message so it never passes for one."""
    return "(reader) " + text if text.startswith((PREFIX, STATE_PREFIX)) else text


def split(history, keep: int) -> Optional[Split]:
    """Cut `history` at whole exchanges, keeping the newest `keep`; None if nothing would go.

    The reader's question is the last plain user message: after it come only
    this run's model turns and their results, so a unit there is a model turn
    with every result it called for, and before it a unit is a Turn's
    question and answer. Neither is ever divided.
    """
    plain = [n for n, e in enumerate(history) if isinstance(e, User) and not is_handoff(e) and not is_state(e)]
    if not plain:
        return None
    q = plain[-1]
    before, after = history[:q], history[q + 1:]
    if any(isinstance(e, User) for e in after):
        return None
    previous = [e for e in before if is_handoff(e)]
    turns: list[list] = []
    for entry in (e for e in before if not is_handoff(e) and not is_state(e)):
        if isinstance(entry, User):
            turns.append([entry])
        elif turns and isinstance(entry, ModelTurn) and len(turns[-1]) == 1:
            turns[-1].append(entry)
        else:
            return None
    exchanges: list[list] = []
    for entry in after:
        if isinstance(entry, ModelTurn):
            exchanges.append([entry])
        elif isinstance(entry, ToolResult) and exchanges:
            exchanges[-1].append(entry)
        else:
            return None
    units = [("turn", tuple(u)) for u in turns] + [("exchange", tuple(u)) for u in exchanges]
    if len(units) <= keep:
        return None
    gone, kept = units[:-keep], units[-keep:]
    return Split(
        previous=previous[-1] if previous else None,
        state=tuple(e for e in before if is_state(e)), question=history[q],
        gone_turns=tuple(u for k, u in gone if k == "turn"),
        gone_exchanges=tuple(u for k, u in gone if k == "exchange"),
        kept_turns=tuple(u for k, u in kept if k == "turn"),
        kept_exchanges=tuple(u for k, u in kept if k == "exchange"),
    )


def parse(text: str) -> Optional[dict]:
    """The model's summary fields, or None when it is not one."""
    try:
        raw = json.loads(FENCE.sub("", text.strip()))
    except ValueError:
        return None
    if not isinstance(raw, dict) or not _text(raw.get("goal")):
        return None
    return raw


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= TEXT_CHARS


def _texts(value) -> list[str]:
    return [v.strip() for v in value if _text(v)][:ITEMS] if isinstance(value, list) else []


def build(summary: dict, *, previous: Optional[dict], compacted: list[int], passages, plan, state: dict,
          entries=()) -> dict:
    """The handoff body: the model's description, bounded and checked, beside the application's record.

    `passages` maps each handle this run read to its source; `state` holds
    Record ids for the shown order, selections and exclusions.
    """
    turns = sorted({*(previous or {}).get("turns", ()), *compacted})
    findings = []
    for raw in summary.get("findings", ())[:FINDINGS] if isinstance(summary.get("findings"), list) else ():
        if not isinstance(raw, dict) or not _text(raw.get("text")):
            continue
        cited = [h for h in raw.get("passages", ()) if isinstance(h, str) and h in passages] \
            if isinstance(raw.get("passages"), list) else []
        came_from = [t for t in raw.get("turns", ()) if type(t) is int and t in turns] \
            if isinstance(raw.get("turns"), list) else []
        # A finding with no original behind it is the model's, not the research's.
        if cited or came_from:
            findings.append({"text": raw["text"].strip(), "passages": list(dict.fromkeys(cited)),
                             "turns": sorted(set(came_from))})
    # Every passage read, not only those a finding cites: the goal and limitations may draw on any.
    sources = {*(previous or {}).get("sources", ()), *(p.source.revision for p in passages.values())}
    source_refs = {p.source for p in passages.values()}
    source_refs.update(source for entry in entries for source in entry.dependencies)
    if previous:
        source_refs.update(Source(**source) for source in previous.get("source_refs", ()))
    unverified = (any(getattr(entry, "unverified_provenance", False) for entry in entries)
                  or any(isinstance(entry, ToolResult) and not entry.dependencies and not entry.control_only
                         and not entry.metadata_only for entry in entries)
                  or bool(previous and (previous.get("unverified", True) or "source_refs" not in previous)))
    return {
        "format": FORMAT, "derived": True, "goal": summary["goal"].strip(),
        "preferences": _texts(summary.get("preferences")), "findings": findings,
        "limitations": _texts(summary.get("limitations")), "plan": [dict(s) for s in plan],
        "shown": list(state.get("shown", ())), "selected": list(state.get("selected", ())),
        "excluded": list(state.get("excluded", ())), "turns": turns, "sources": sorted(sources),
        "source_refs": [asdict(source) for source in sorted(
            source_refs, key=lambda source: (source.record_id, source.chunk_set_id, source.extraction_hash))],
        "unverified": unverified,
    }


#: What every handoff body carries; a saved body missing any is not one.
BODY_KEYS = frozenset({"format", "derived", "goal", "preferences", "findings", "limitations", "plan", "shown",
                       "selected", "excluded", "turns", "sources", "source_refs", "unverified"})


def well_formed(body) -> bool:
    return (isinstance(body, dict) and BODY_KEYS <= set(body) and body["format"] == FORMAT
            and type(body["unverified"]) is bool
            and all(isinstance(body[k], list) for k in BODY_KEYS - {"format", "derived", "goal", "unverified"})
            and all(isinstance(source, dict) and set(source) == {"record_id", "chunk_set_id", "extraction_hash"}
                    and type(source["record_id"]) is int and source["record_id"] > 0
                    and type(source["chunk_set_id"]) is int and source["chunk_set_id"] > 0
                    and isinstance(source["extraction_hash"], str) and source["extraction_hash"]
                    for source in body["source_refs"]))


def render(body: dict, papers: dict, *, passages: bool) -> User:
    """The handoff as the model reads it, with this run's handles for the papers it may still read.

    `passages` False drops passage handles, which only the run that read them can use.
    """
    def listed(ids):
        return [papers[i][0] for i in ids if i in papers]

    shown = [{"position": n, "paper": papers[i][0], "title": papers[i][1]}
             for n, i in enumerate((i for i in body["shown"] if i in papers), start=1)]
    view = {
        "derived": True, "note": DERIVED, "goal": body["goal"], "preferences": body["preferences"],
        "shown": shown, "selected": listed(body["selected"]), "excluded": listed(body["excluded"]),
        "plan": body["plan"],
        "findings": [{"text": f["text"], "turns": f["turns"], "passages": f["passages"] if passages else []}
                     for f in body["findings"]],
        "limitations": body["limitations"], "turns": body["turns"],
    }
    return User(PREFIX + json.dumps(view, ensure_ascii=False),
                frozenset(Source(**source) for source in body.get("source_refs", ())),
                body.get("unverified") is not False)
