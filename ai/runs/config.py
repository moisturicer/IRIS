"""Run limits, read fail-closed (IR-722, IR-723, ADR-049 §12).

Every limit is required; an unset one refuses admission. Nothing here is a
production value.
"""

from __future__ import annotations

from dataclasses import dataclass

EXECUTORS = ("deterministic", "agent")
DEPTHS = ("ordinary", "deep")
PROTOCOL = "runs-1"
SCHEMA = "0004_agent.sql"

LIMIT_NAMES = (
    "RUNS_DEADLINE_SECONDS", "RUNS_DEEP_DEADLINE_SECONDS", "RUNS_LEASE_SECONDS",
    "RUNS_MAX_ATTEMPTS", "RUNS_MAX_INPUT_TOKENS", "RUNS_MAX_OUTPUT_TOKENS", "RUNS_MAX_COST_USD",
    "RUNS_MAX_QUEUED", "RUNS_MAX_ACTIVE_PER_READER", "RUNS_MAX_RUNNING_PER_READER",
    "RUNS_DEEP_CONCURRENCY", "RUNS_WORKER_CONCURRENCY", "RUNS_POLL_SECONDS",
)


class RunsUnavailable(Exception):
    """Runs are unconfigured; the routes answer `unavailable`."""


@dataclass(frozen=True)
class RunLimits:
    deadline_seconds: int
    deep_deadline_seconds: int
    lease_seconds: int
    max_attempts: int
    max_input_tokens: int
    max_output_tokens: int
    max_cost_usd: float

    def allowance(self) -> dict:
        """What the run may spend, persisted unchanged at admission."""
        return {
            "max_attempts": self.max_attempts,
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "max_cost_usd": self.max_cost_usd,
        }

    def deadline_for(self, depth: str) -> int:
        if depth not in DEPTHS:
            raise ValueError(depth)
        return self.deep_deadline_seconds if depth == "deep" else self.deadline_seconds


@dataclass(frozen=True)
class Dispatch:
    """Queue populations and worker slots (IR-723)."""

    #: Active runs across every reader.
    max_queued: int
    max_active_per_reader: int
    #: Running at once per reader, so one account cannot hold every slot.
    max_running_per_reader: int
    #: Deep runs running at once; every other slot is kept for ordinary ones.
    deep_concurrency: int
    #: Slots per worker process.
    worker_concurrency: int
    #: How long a worker waits for a wakeup before scanning anyway.
    poll_seconds: float


@dataclass(frozen=True)
class RunsConfig:
    database_url: str
    executor: str
    limits: RunLimits
    dispatch: Dispatch
    #: Wakeups only; empty means workers poll.
    redis_url: str = ""


def problems(values) -> list[str]:
    found = []
    if not getattr(values, "RUNS_DATABASE_URL", ""):
        found.append("RUNS_DATABASE_URL is required")
    if getattr(values, "RUNS_MIGRATION_DATABASE_URL", ""):
        found.append("RUNS_MIGRATION_DATABASE_URL must not be set on a running service")
    if getattr(values, "RUNS_EXECUTOR", None) not in EXECUTORS:
        found.append(f"RUNS_EXECUTOR must be one of {', '.join(EXECUTORS)}")
    for name in LIMIT_NAMES:
        value = getattr(values, name, None)
        if value is None or value <= 0:
            found.append(f"{name} must be set and positive")
    deep = getattr(values, "RUNS_DEEP_CONCURRENCY", None)
    slots = getattr(values, "RUNS_WORKER_CONCURRENCY", None)
    if deep and slots and deep >= slots:
        found.append("RUNS_DEEP_CONCURRENCY must be below RUNS_WORKER_CONCURRENCY")
    return found


def read(values) -> RunsConfig:
    """From the gateway's settings; raises RunsUnavailable when incomplete."""
    found = problems(values)
    if found:
        raise RunsUnavailable("; ".join(found))
    return RunsConfig(
        database_url=values.RUNS_DATABASE_URL,
        executor=values.RUNS_EXECUTOR,
        limits=RunLimits(
            deadline_seconds=values.RUNS_DEADLINE_SECONDS,
            deep_deadline_seconds=values.RUNS_DEEP_DEADLINE_SECONDS,
            lease_seconds=values.RUNS_LEASE_SECONDS,
            max_attempts=values.RUNS_MAX_ATTEMPTS,
            max_input_tokens=values.RUNS_MAX_INPUT_TOKENS,
            max_output_tokens=values.RUNS_MAX_OUTPUT_TOKENS,
            max_cost_usd=values.RUNS_MAX_COST_USD,
        ),
        dispatch=Dispatch(
            max_queued=values.RUNS_MAX_QUEUED,
            max_active_per_reader=values.RUNS_MAX_ACTIVE_PER_READER,
            max_running_per_reader=values.RUNS_MAX_RUNNING_PER_READER,
            deep_concurrency=values.RUNS_DEEP_CONCURRENCY,
            worker_concurrency=values.RUNS_WORKER_CONCURRENCY,
            poll_seconds=values.RUNS_POLL_SECONDS,
        ),
        redis_url=getattr(values, "RUNS_REDIS_URL", ""),
    )
