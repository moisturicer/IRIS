"""The public reader protocol (IR-595, ADR-042, spec §6).

One server-side allowlist for everything a reader surface receives under
`protocol=public-1`: the live SSE stream, a queued run's replay and
reconnect, the final body of `/ask/`, and a reopened transcript. A field not
named here is never sent -- routing, planner steps, raw reasoning, validation
codes and tool payloads cannot leak by being added later.

The legacy protocol stays as it was; a caller opts in per request, by the
`protocol` body or query field or the `X-IRIS-Protocol` header.

`activity` is a neutral lifecycle state derived from the event kind, never
from its content. `reasoning_summary` is the Turn's stored, already validated
display summary (`answers/assurance.safe_summary`), present only on a
generated answer whose citations are all still readable.
"""

from __future__ import annotations

from typing import Optional

from rest_framework.exceptions import ValidationError

PUBLIC_PROTOCOL = "public-1"
PROTOCOLS = (PUBLIC_PROTOCOL,)

WAITING, THINKING, PREPARING = "waiting", "thinking", "preparing"
LABELS = {WAITING: "Waiting…", THINKING: "Thinking…", PREPARING: "Preparing your answer…"}

_ACTIVITY = {
    "run_queued": WAITING,
    "run_started": THINKING, "retrieval_started": THINKING, "retrieval_finished": THINKING,
    "routing_decided": THINKING, "agent_step": THINKING, "reasoning_delta": THINKING,
    "candidates_selected": THINKING, "candidates_updated": THINKING,
    "generation_started": PREPARING, "text_delta": PREPARING,
}

_RUN = ("run_id", "state", "reason", "retry_of", "deadline_at")
#: Event name to the payload fields it may carry.
EVENT_FIELDS = {
    "run_queued": _RUN, "run_started": ("run_id", "state"), "run_failed": _RUN, "run_cancelled": _RUN,
    "text_delta": ("text",),
    "citations_resolved": ("citations",),
    "candidates_selected": ("candidates", "limit", "more_available", "degraded"),
    "candidates_updated": ("candidates",),
}
DONE_FIELDS = (
    "answer", "message", "citations", "sources", "mode", "degraded", "widened",
    "resolved_question", "conversation_id", "turn_id", "partial", "listing", "comparison",
    "reasoning_summary",
)
TURN_FIELDS = DONE_FIELDS + ("id", "question", "created_at")


def requested(request) -> bool:
    """Whether this request opted into the public protocol; 400 on an unknown one."""
    raw = (request.headers.get("X-IRIS-Protocol") or request.query_params.get("protocol")
           or (request.data.get("protocol") if hasattr(request.data, "get") else None))
    if raw in (None, ""):
        return False
    if raw not in PROTOCOLS:
        raise ValidationError({"protocol": f"Supported protocols: {', '.join(PROTOCOLS)}."})
    return True


def activity_state(name: str) -> Optional[str]:
    return _ACTIVITY.get(name)


def activity(state: str) -> dict:
    return {"state": state, "label": LABELS[state]}


def project_done(body: dict) -> dict:
    """A final answer body, allowlisted. The summary rides only on a generated answer."""
    out = {key: body[key] for key in DONE_FIELDS if key in body}
    if out.get("mode") != "generative" or not out.get("reasoning_summary"):
        out.pop("reasoning_summary", None)
    return out


def project_turn(body: dict) -> dict:
    out = {key: body[key] for key in TURN_FIELDS if key in body}
    out["mode"] = body.get("mode", body.get("state"))
    if out["mode"] != "generative" or not out.get("reasoning_summary"):
        out.pop("reasoning_summary", None)
    return out


def summary_for(turn, resolved_citations: int) -> Optional[str]:
    """The Turn's stored summary, unless a cited source is no longer readable."""
    if not turn.reasoning_summary or resolved_citations < len(turn.citations.all()):
        return None
    return turn.reasoning_summary


class StreamProjector:
    """Turns internal events into public frames, with no repeated activity.

    `feed` returns `(name, data)` pairs in send order. `seed` sets the state a
    reconnecting reader already holds.
    """

    def __init__(self, seed: Optional[str] = None) -> None:
        self.state = seed

    def feed(self, name: str, data: dict) -> list[tuple[str, dict]]:
        frames: list[tuple[str, dict]] = []
        state = activity_state(name)
        if state is not None and state != self.state:
            self.state = state
            frames.append(("activity", activity(state)))
        if name == "done":
            frames.append((name, project_done(data)))
        elif name in EVENT_FIELDS:
            frames.append((name, {k: data[k] for k in EVENT_FIELDS[name] if k in data}))
        return frames
