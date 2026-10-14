"""How a burst of Ask IRIS submissions is counted (IR-550).

The pilot's soft goal is 95 successful final answers under 10 s per 100
submissions, measured at 100 simultaneous distinct uncached questions, with
the ordinary 30 s deadline as a hard limit (fixed-workflow pilot README §1).

**Every submission stays in the denominator.** A rejection, failure, timeout,
cancellation or a stream that never finished is a submission that did not
succeed, never one that is left out. Latency runs from the original
submission, so queueing counts. A preview, an unavailable or partial answer,
no results and an inconclusive listing are not generated completions.

**Only one shape of burst is a capacity measurement**: real providers, a cold
cache, simultaneous, and at least `MIN_BURST` distinct questions. A fake
provider or a warm cache is a control, and anything smaller or sequential is
unverified. A burst declared cold that reports any screening-cache hit is
treated as warm. A throttled submission (429) is a rejection like `503 busy`. `plan_burst` refuses a burst whose worst case does not fit the
campaign's spendable share, so the protected reserve is never planned into.

Pure: no database and no network. A driver hands it what it observed.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

SOFT_GOAL_MS = 10_000
DEADLINE_MS = 30_000
MIN_BURST = 100
GOAL_RATE = 0.95

GENERATED = "generated"

#: Every outcome a submission can end in. Only `generated` can succeed.
OUTCOMES = (
    GENERATED, "preview_only", "unavailable", "partial", "no_results", "inconclusive",
    "refused", "failed", "timeout", "cancelled", "unfinished",
)

#: The campaign limits a burst is planned against (`admission.limits.Ceiling`).
LIMITS = ("attempts", "input_tokens", "output_tokens", "cost_micros", "active_ms")

_MODE_OUTCOME = {"generative": GENERATED, "unavailable": "unavailable",
                 "partial": "partial", "no_results": "no_results"}
_PREVIEW_EVENTS = {"candidates_selected", "candidates_updated"}


@dataclass(frozen=True)
class Submission:
    question: str
    result: str
    #: Milliseconds on one monotonic clock shared by the whole burst.
    submitted_ms: int
    #: When the final response arrived, or `None` if none did.
    final_ms: Optional[int]
    #: Verdicts the run reused from the screening cache (`listing.observed`).
    cache_hits: int = 0

    def __post_init__(self):
        if self.result not in OUTCOMES:
            raise ValueError(f"unknown outcome {self.result!r}")

    @property
    def elapsed_ms(self) -> Optional[int]:
        return None if self.final_ms is None else self.final_ms - self.submitted_ms


@dataclass(frozen=True)
class Burst:
    submissions: tuple[Submission, ...]
    #: `real` or `fake`: which providers answered.
    provider: str
    #: `cold` or `warm`: whether any verdict or answer could come from a cache.
    cache: str
    #: All submissions were sent together rather than one after another.
    simultaneous: bool
    #: `queued` (durable runs, so queue wait is measured) or `inline`.
    path: str = "inline"


def classify_stream(status: int, events: Sequence[tuple[str, Mapping]]) -> str:
    """The outcome a reader got from one submission's HTTP status and SSE events."""
    if status in (429, 503):  # throttled, or refused as busy
        return "refused"
    if status != 200:
        return "failed"
    names = [name for name, _ in events]
    for name, data in reversed(events):
        if name == "done":
            if "capacity_limited" in names:
                return "unavailable"
            listing = data.get("listing") or {}
            if listing.get("completeness") == "inconclusive":
                return "inconclusive"
            return _MODE_OUTCOME.get(data.get("mode"), "unavailable")
        if name == "run_failed":
            expired = data.get("state") == "expired" or data.get("reason") == "deadline_exceeded"
            return "timeout" if expired else "failed"
        if name == "run_cancelled":
            return "cancelled"
    return "preview_only" if _PREVIEW_EVENTS & set(names) else "unfinished"


def percentile(values: Sequence[int], fraction: float) -> Optional[int]:
    """Nearest rank, so every reported figure is one a submission observed."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def _claim(burst: Burst, distinct: int, goal_met: bool, warm: bool) -> str:
    if burst.provider != "real" or burst.cache != "cold" or warm:
        return "control_only"
    if not burst.simultaneous or distinct < MIN_BURST or distinct != len(burst.submissions):
        return "unverified"
    return "measured_goal_met" if goal_met else "measured_goal_missed"


def summarize(burst: Burst) -> dict:
    rows = burst.submissions
    submitted = len(rows)
    distinct = len({row.question for row in rows})
    late = [row.question for row in rows
            if row.elapsed_ms is not None and row.elapsed_ms > DEADLINE_MS]
    successes = sum(row.result == GENERATED and row.elapsed_ms is not None
                    and row.elapsed_ms <= SOFT_GOAL_MS for row in rows)
    rate = successes / submitted if submitted else None
    goal_met = rate is not None and rate >= GOAL_RATE
    arrived = [row.elapsed_ms for row in rows if row.elapsed_ms is not None]
    # A declared cold burst that reused verdicts was warm, whatever was declared.
    warm = burst.cache == "cold" and any(row.cache_hits for row in rows)
    return {
        "provider": burst.provider,
        "cache": burst.cache,
        "simultaneous": burst.simultaneous,
        "path": burst.path,
        "cache_contradicted": warm,
        "submissions": submitted,
        "distinct": distinct,
        "outcomes": dict(Counter(row.result for row in rows)),
        "successes_under_goal": successes,
        "goal_rate": rate,
        "goal": f"{GOAL_RATE:.0%} of submissions generated under {SOFT_GOAL_MS // 1000} s",
        "goal_met": goal_met,
        "deadline_violations": late,
        "latency_ms": {"n": len(arrived), "p50": percentile(arrived, 0.5),
                       "p95": percentile(arrived, 0.95), "max": max(arrived, default=None)},
        "claim": _claim(burst, distinct, goal_met, warm) if submitted else "unverified",
    }


def plan_burst(n: int, *, per_run: Mapping[str, Optional[int]],
               spendable: Mapping[str, int], charged: Mapping[str, int]) -> dict:
    """May ``n`` submissions start, at each run's worst case, before the reserve?

    ``per_run`` is the per-run cap (a run cannot spend beyond it), ``spendable``
    the campaign's share before its protected reserve, and ``charged`` what the
    ledger already holds, open reservations included. A limit with no per-run
    cap or no campaign ceiling cannot be bounded, so it blocks.
    """
    blocking, needed, remaining = [], {}, {}
    for limit in LIMITS:
        cap, spend = per_run.get(limit), spendable.get(limit)
        remaining[limit] = None if spend is None else spend - charged.get(limit, 0)
        needed[limit] = None if cap is None else n * cap
        if None in (needed[limit], remaining[limit]) or needed[limit] > remaining[limit]:
            blocking.append(limit)
    fits = not blocking
    return {
        "submissions": n,
        "needed": needed,
        "remaining_before_reserve": remaining,
        "blocking": blocking,
        "fits": fits,
        "claim": "may_start" if fits else "unverified",
    }
