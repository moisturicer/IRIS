"""Allowlisted reader state shared by live, reopened and exported runs (IR-730)."""

from ai.agent.tools import PLAN_STEPS, STEP_ID, STEP_STATUS
from ai.runs.config import KIND_COMPACT

PROTOCOL = "runs-reader-1"


#: Lifecycle moments a reconnecting reader is told of, by name alone. Anything
#: else in the journal (tool calls, model attempts, recovery) is the operator's.
LIFECYCLE = ("admitted", "started", "completed", "cancelled", "failed", "expired", "conflict", "deleted")


class _Progress:
    """Folds journal events into the reader's progress, and says what each shows (IR-726).

    `accept` returns the allowlisted form of an event the reader may see, or
    None when it shows nothing (unknown, invalid, or repeated).
    """

    def __init__(self):
        self.plan = None
        self.context = None
        self.compaction = None
        self.counted = set()

    def accept(self, event):
        data = event["data"]
        name = event["name"]
        if name == "plan":
            return self._plan(data)
        if name == "compaction":
            return self._compaction(data)
        if name == "context":
            return self._context(data)
        if name in LIFECYCLE:
            return {"name": name}
        return None

    def _plan(self, data):
        revision, steps = data.get("revision"), data.get("steps")
        if (type(revision) is not int or revision < 1 or
                (self.plan and revision <= self.plan["revision"]) or
                not isinstance(steps, list) or len(steps) > PLAN_STEPS):
            return None
        clean = []
        for step in steps:
            if (not isinstance(step, dict) or not isinstance(step.get("id"), str) or
                    not STEP_ID.fullmatch(step["id"]) or step.get("status") not in STEP_STATUS or
                    not isinstance(step.get("title"), str) or not step["title"].strip() or
                    len(step["title"]) > 160):
                return None
            clean.append({key: step[key] for key in ("id", "title", "status")})
        ids = [s["id"] for s in clean]
        previous = {s["id"] for s in self.plan["steps"]} if self.plan else set()
        if len(set(ids)) != len(ids) or not previous <= set(ids):
            return None
        self.plan = {"revision": revision, "steps": clean}
        return {"name": "plan", **self.plan}

    def _compaction(self, data):
        # Outcome and counts only: never a reason code, summary text, revision or source.
        turns = data.get("turns")
        if data.get("outcome") not in ("compacted", "kept") or (
                data["outcome"] == "compacted" and (type(turns) is not int or turns < 0)):
            return None
        revision = data.get("revision")
        if data["outcome"] == "compacted" and revision in self.counted:
            # A worker that took the run over saw the commit and said so again (IR-754).
            return None
        self.compaction = self.compaction or {"compactions": 0, "turns_compacted": 0, "last": None}
        self.compaction["last"] = data["outcome"]
        if data["outcome"] == "compacted":
            self.counted.add(revision)
            self.compaction["compactions"] += 1
            self.compaction["turns_compacted"] += turns
            return {"name": "compaction", "outcome": "compacted", "turns": turns}
        return {"name": "compaction", "outcome": "kept"}

    def _context(self, data):
        used, capacity = data.get("used_tokens"), data.get("capacity_tokens")
        valid = type(used) is int and type(capacity) is int and 0 <= used <= capacity and capacity > 0
        self.context = {"estimated": True, "used_tokens": used, "capacity_tokens": capacity} if valid else None
        return {"name": "context", **self.context} if valid else None


def progress(events):
    folded = _Progress()
    for event in events:
        folded.accept(event)
    return {"plan": folded.plan, "context": folded.context, "compaction": folded.compaction}


def journal(events, after):
    """The reader's journal past position `after`, and its length (IR-726).

    Only what the reader may see is counted, so a position says nothing of how
    many tool calls, model attempts or recoveries the operator's journal holds.
    The whole journal is folded, so a slice never contradicts the run's plan,
    context or compaction; entries are returned only past the cursor.
    """
    folded = _Progress()
    entries, position = [], 0
    for event in events:
        shown = folded.accept(event)
        if shown is None:
            continue
        position += 1
        if position > after:
            entries.append({"position": position, **shown})
    return entries, position


#: What the reader sees the model doing: a coarse phase, never a prompt or tool argument.
MODEL_PHASES = {"gather": "Thinking", "final": "Writing the answer", "repair": "Checking the answer"}
TOOL_STEPS = {
    "search": ("search", "Searched papers"), "hybrid_search": ("search", "Searched papers"),
    "resolve": ("search", "Looked up papers"), "list_records": ("catalogue", "Looked through the catalogue"),
    "count": ("catalogue", "Counted papers"), "recall": ("recall", "Recalled the conversation"),
    "recover_turn": ("recall", "Reread an earlier answer"),
}
READING = ("read_manuscript", "read_page", "open_passage", "outline")


def activity(snapshot):
    """The live phase of an active run, and its latest step; None once it ends."""
    state = snapshot["state"]
    if state == "queued":
        return {"phase": "waiting", "label": "Waiting to start", "since": snapshot["created_at"], "step": None}
    if state != "running":
        return None
    events = [e for e in snapshot.get("events", []) if e["name"] in ("started", "model", "tool")]
    label, since, step = "Thinking", snapshot.get("started_at") or snapshot["created_at"], None
    titles = snapshot.get("read_titles") or []
    for event in events:
        data = event.get("data") or {}
        if event["name"] == "model":
            next_label = MODEL_PHASES.get(data.get("phase"), "Thinking")
            if next_label != label:
                label, since = next_label, event.get("created_at") or since
        elif event["name"] == "tool":
            tool = data.get("tool")
            if tool in READING:
                count = len(titles)
                step = {"kind": "read", "label": f"Read {count} paper{'s' if count != 1 else ''}" if count
                        else "Reading a paper", "detail": titles[-3:]}
            elif tool in TOOL_STEPS:
                kind_, text = TOOL_STEPS[tool]
                step = {"kind": kind_, "label": text, "detail": []}
    return {"phase": "working", "label": label, "since": since, "step": step}


def usage(snapshot, reserved_tokens=None):
    """Tokens the provider reported for this run's model calls; the context is the latest call's prompt."""
    used = snapshot.get("usage")
    if not used:
        return None
    capacity = None
    for event in snapshot.get("events", []):
        if event["name"] == "context" and type((event.get("data") or {}).get("capacity_tokens")) is int:
            capacity = event["data"]["capacity_tokens"]
    return {**{key: used[key] for key in ("calls", "input_tokens", "output_tokens", "cost_usd")},
            "context_tokens": used["last_input_tokens"], "capacity_tokens": capacity,
            "reserved_tokens": reserved_tokens}


def kind(snapshot):
    """What the run was for: "compact" for a manual compaction, else an Ask. Nothing else is published."""
    return "compact" if (snapshot.get("pinned") or {}).get("kind") == KIND_COMPACT else "ask"


def run(snapshot, *, manual_compaction=False, after=None, reserved_tokens=None):
    """The reader's view of a run. A cursor (`after`) adds the journal replay past it (IR-726)."""
    # A compaction asks nothing; it shows an empty question rather than none.
    snapshot = {**snapshot, "question": snapshot["question"] or ""}
    visible = snapshot["events"] if snapshot.get("sources_available", True) else []
    replay, cursor = journal(visible, after or 0)
    return {
        "protocol": PROTOCOL,
        **{key: snapshot[key] for key in (
            "id", "conversation_id", "state", "question", "base_revision", "version",
            "turn_id", "depth", "awaiting_reader", "created_at", "finished_at",
        )},
        "kind": kind(snapshot),
        **progress(visible),
        "activity": activity(snapshot),
        "usage": usage(snapshot, reserved_tokens),
        # The end of what the reader may see: where a reconnecting reader asks to continue from.
        "cursor": cursor,
        **({"journal": replay} if after is not None else {}),
        "retry_of": snapshot.get("retry_of"),
        "retried_by": snapshot.get("retried_by"),
        "sources_available": snapshot.get("sources_available", True),
        "capabilities": {"manual_compaction": manual_compaction},
    }


def conversation(snapshot, *, manual_compaction=False, reserved_tokens=None):
    available = {item["id"]: item.get("sources_available", True) for item in snapshot["runs"]}
    return {
        "protocol": PROTOCOL, "id": snapshot["id"], "revision": snapshot["revision"],
        "runs": [run(item, manual_compaction=manual_compaction, reserved_tokens=reserved_tokens)
                 for item in snapshot["runs"]],
        "turns": [{**{key: turn[key] for key in (
            "id", "run_id", "ordinal", "question", "answer", "kind", "created_at", "citations",
        )}, "facts": turn.get("facts", []),
            **({} if available[turn["run_id"]] else {
                "answer": "This answer is unavailable because its sources changed or are no longer readable.",
                "citations": [], "facts": [],
            })} for turn in snapshot["turns"]],
    }
