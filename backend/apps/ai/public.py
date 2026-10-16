"""The public reader protocol (IR-595, ADR-042 §6): `protocol=public-1`.

One allowlist for live SSE, queued replay, `/ask/` and transcripts. A field
not named here is never sent, at any depth.
"""

from __future__ import annotations

from typing import Optional

from rest_framework.exceptions import ValidationError

from apps.ai.presentation import GENERATIVE_MODE

PUBLIC_PROTOCOL = "public-1"
PROTOCOLS = (PUBLIC_PROTOCOL,)

WAITING, THINKING, PREPARING = "waiting", "thinking", "preparing"
LABELS = {WAITING: "Waiting…", THINKING: "Thinking…", PREPARING: "Preparing your answer…"}

_ACTIVITY = {
    "run_queued": WAITING, "capacity_limited": WAITING,
    "run_started": THINKING, "retrieval_started": THINKING, "retrieval_finished": THINKING,
    "routing_decided": THINKING, "agent_step": THINKING, "reasoning_delta": THINKING,
    "candidates_selected": THINKING, "candidates_updated": THINKING,
    "generation_started": PREPARING, "text_delta": PREPARING,
}

#: The only end reasons a reader receives; anything else is dropped.
REASONS = frozenset({
    "cancelled", "deadline_exceeded", "no_answer", "not_answerable", "engine_unavailable",
    "error", "unavailable",
})
_RUN = ("run_id", "state", "reason", "retry_of", "deadline_at")
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

_CITATION = ("marker", "chunk_id", "record_id", "record_title", "page", "text", "context_path",
             "regions")
_SOURCE_CARD = ("id", "title", "abstract", "authors", "year", "classification", "score")
_RECORD = ("record_id", "title")
_CANDIDATE = ("record_id", "title", "state", "quote", "restricted")
_CANDIDATE_SOURCE = ("field", "page", "chunk_id")
_COVERAGE = ("limit", "selected", "included", "excluded", "uncertain", "unassessed",
             "more_available", "search_degraded", "changed")
_TOPIC_COUNT = ("criterion", "basis", "matches", "assessed", "excluded", "uncertain",
                "unassessed", "selected", "limit", "more_available")
_LISTING = ("completeness", "wording")
_COMPARISON_COVERAGE = ("record_id", "title", "state")
_COMPARISON_CITATION = ("page", "quote", "chunk_id", "marker")
_LATEST_RUN = ("id", "state", "end_reason", "question", "retry_of", "last_sequence")


def requested(request) -> bool:
    """Whether the request opted in; 400 on an unknown protocol."""
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


def _pick(source, keys) -> dict:
    return {key: source[key] for key in keys if isinstance(source, dict) and key in source}


def _each(rows, project) -> list:
    return [project(row) for row in rows or [] if isinstance(row, dict)]


def _candidate(row: dict) -> dict:
    out = _pick(row, _CANDIDATE)
    if isinstance(row.get("source"), dict):
        out["source"] = _pick(row["source"], _CANDIDATE_SOURCE)
    return out


def _listing(listing: dict) -> dict:
    out = _pick(listing, _LISTING)
    out["records"] = _each(listing.get("records"), lambda r: _pick(r, _RECORD))
    out["candidates"] = _each(listing.get("candidates"), _candidate)
    out["coverage"] = _pick(listing.get("coverage"), _COVERAGE)
    if "topic_count" in listing:
        out["topic_count"] = _pick(listing["topic_count"], _TOPIC_COUNT)
    return out


def _comparison(comparison: dict) -> dict:
    def cell(c):
        return {**_pick(c, ("record_id", "state")), "values": _each(c.get("values"), lambda v: {
            **_pick(v, ("value",)),
            "citations": _each(v.get("citations"), lambda x: _pick(x, _COMPARISON_CITATION))})}

    def row(r):
        return {**_pick(r, ("dimension", "label")), "cells": _each(r.get("cells"), cell)}

    return {
        "records": _each(comparison.get("records"), lambda r: _pick(r, _RECORD)),
        "rows": _each(comparison.get("rows"), row),
        "coverage": _each(comparison.get("coverage"), lambda c: _pick(c, _COMPARISON_COVERAGE)),
        **_pick(comparison, ("removed_claims",)),
    }


def _shape(body: dict, fields) -> dict:
    out = _pick(body, fields)
    nested = (("citations", _CITATION), ("sources", _SOURCE_CARD))
    for key, keys in nested:
        if key in out:
            out[key] = _each(out[key], lambda row, keys=keys: _pick(row, keys))
    if isinstance(out.get("listing"), dict):
        out["listing"] = _listing(out["listing"])
    if isinstance(out.get("comparison"), dict):
        out["comparison"] = _comparison(out["comparison"])
    return out


def _generated_only(out: dict) -> dict:
    if out.get("mode") != GENERATIVE_MODE or not out.get("reasoning_summary"):
        out.pop("reasoning_summary", None)
    return out


def project_done(body: dict) -> dict:
    return _generated_only(_shape(body, DONE_FIELDS))


def project_turn(body: dict) -> dict:
    out = _shape(body, TURN_FIELDS)
    out["mode"] = body.get("mode", body.get("state"))
    return _generated_only(out)


def project_latest_run(run: Optional[dict]) -> Optional[dict]:
    if run is None:
        return None
    out = _pick(run, _LATEST_RUN)
    if out.get("end_reason") not in REASONS:
        out.pop("end_reason", None)
    return out


def summary_for(turn, resolved_citations: int) -> Optional[str]:
    """The stored summary, unless a cited source is no longer readable."""
    if not turn.reasoning_summary or resolved_citations < len(turn.citations.all()):
        return None
    return turn.reasoning_summary


class StreamProjector:
    """Internal events to public frames; `seed` is the activity a reconnecting reader holds."""

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
            out = _pick(data, EVENT_FIELDS[name])
            if out.get("reason") not in REASONS:
                out.pop("reason", None)
            if "candidates" in out:
                out["candidates"] = _each(out["candidates"], _candidate)
            if name == "citations_resolved":
                out["citations"] = _each(out.get("citations"), lambda c: _pick(c, _CITATION))
            frames.append((name, out))
        return frames
