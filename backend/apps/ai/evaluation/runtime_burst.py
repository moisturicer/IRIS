"""A simultaneous burst of questions through the dedicated runtime (IR-1007).

IR-550's burst drives Django's retired `/ask/stream/`. This one submits every
question to the runtime's run route at once, spread over several readers, each
in a new Conversation, and follows each run to its end with the same collector
the answer-quality run uses (`collect_case_runtime`).

Every submission stays in the denominator: a `503 busy` is `refused`, and a
failed, timed-out or cancelled run is not an answer. Latency runs from
submission, so queue wait counts. No latency objective is approved for the
runtime, so the summary reports what was observed and claims no goal.
"""

from __future__ import annotations

import threading
import time
from collections import Counter
from typing import Callable, Mapping, Optional, Sequence

from .capacity import MIN_BURST, percentile
from .runtime_replay import collect_case_runtime

ANSWERED = "answered"
#: The collector's name for a `503 busy` submission.
_BUSY = "cap_stop"
DEPTHS = ("ordinary", "deep")


def plan_items(questions: Sequence[str], *, readers: Sequence, deep_share: float) -> list[dict]:
    """Readers in turn; `deep_share` of the questions deep, spread evenly. Deterministic."""
    if not readers:
        raise ValueError("a burst needs at least one reader")
    if not 0 <= deep_share <= 1:
        raise ValueError("deep_share must be between 0 and 1")
    return [{"question": q, "reader": readers[i % len(readers)],
             "depth": "deep" if int((i + 1) * deep_share) > int(i * deep_share) else "ordinary"}
            for i, q in enumerate(questions)]


def run_burst(items: Sequence[Mapping], seam_for: Callable, *, deadline_seconds: float,
              poll_seconds: float, clock=time.monotonic, sleep=time.sleep,
              after: Optional[Callable[[], None]] = None) -> list[dict]:
    """One row per item, in item order; no item is sent until every one is ready."""
    barrier = threading.Barrier(len(items))
    rows: list = [None] * len(items)

    def one(index: int, item: Mapping) -> None:
        seam, error = None, None
        try:
            seam = seam_for(item["reader"])
        except Exception as exc:  # a broken edge is a failed submission, never a lost one
            error = type(exc).__name__
        try:
            barrier.wait(timeout=max(30.0, deadline_seconds))
        except threading.BrokenBarrierError:
            pass
        started = clock()
        row = {"question": item["question"], "depth": item["depth"], "reader": str(item["reader"]),
               "outcome": "failure", "latency_ms": None, "run_id": None, "kind": None}
        try:
            if seam is None:
                raise RuntimeError(error)
            case = {"id": f"B{index + 1:03d}", "family": "burst", "turns": [{"user": item["question"]}]}
            collected = collect_case_runtime(seam, case, depth=item["depth"], clock=clock, sleep=sleep,
                                             deadline_seconds=deadline_seconds, poll_seconds=poll_seconds)
            turn = (collected["turns"] or [{}])[0]
            outcome = turn.get("outcome", "failure")
            row.update(outcome="refused" if outcome == _BUSY else outcome,
                       latency_ms=turn.get("latency_ms"), run_id=turn.get("runtime_run_id"),
                       kind=(turn.get("public_answer") or {}).get("kind"))
        except Exception as exc:
            row.update(outcome="failure", error=error or type(exc).__name__,
                       latency_ms=round((clock() - started) * 1000))
        finally:
            rows[index] = row
            if after is not None:
                after()

    threads = [threading.Thread(target=one, args=(i, item), daemon=True) for i, item in enumerate(items)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return rows


def _latency(values: Sequence[int]) -> dict:
    return {"n": len(values), "p50": percentile(values, 0.5), "p95": percentile(values, 0.95),
            "max": max(values, default=None)}


def summarize(rows: Sequence[Mapping], *, provider: str, cache: str, wall_ms: int) -> dict:
    submitted = len(rows)
    distinct = len({row["question"] for row in rows})
    answered = [row for row in rows if row["outcome"] == ANSWERED]
    latency = {}
    for depth in DEPTHS:
        mine = [row for row in rows if row["depth"] == depth]
        latency[depth] = {
            "submissions": len(mine),
            "answered": _latency([r["latency_ms"] for r in mine
                                  if r["outcome"] == ANSWERED and r["latency_ms"] is not None]),
            "ended": _latency([r["latency_ms"] for r in mine
                               if r["outcome"] != "refused" and r["latency_ms"] is not None]),
        }
    if provider != "real" or cache != "cold":
        claim = "control_only"
    elif distinct < MIN_BURST or distinct != submitted:
        claim = "unverified"
    else:
        claim = "measured"
    return {
        "provider": provider, "cache": cache, "simultaneous": True,
        "submissions": submitted, "distinct": distinct,
        "outcomes": dict(Counter(row["outcome"] for row in rows)),
        "answered_share": len(answered) / submitted if submitted else None,
        "wall_ms": wall_ms,
        "answered_per_minute": round(len(answered) / (wall_ms / 60_000), 2) if wall_ms else None,
        "latency_ms": latency,
        "goal": None,
        "claim": claim,
    }
