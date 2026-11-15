"""Run limits, read fail-closed (IR-722, IR-723, ADR-049 §12).

Every limit is required; an unset one refuses admission. Nothing here is a
production value.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai.infrastructure.db import PoolSize
from ai.research.selection import Policy

EXECUTORS = ("deterministic", "agent")
DEPTHS = ("ordinary", "deep")
#: Owner decision, ADR-049's 2026-11-04 amendment (IR-885).
DEFAULT_DEPTH = "deep"
#: What a run is for, in its pin: absent means an Ask; a compaction asks nothing and writes no Turn (IR-754).
KIND_COMPACT = "compact"
PROTOCOL = "runs-1"
SCHEMA = "0004_agent.sql"

LIMIT_NAMES = (
    "RUNS_DEADLINE_SECONDS", "RUNS_DEEP_DEADLINE_SECONDS", "RUNS_LEASE_SECONDS",
    "RUNS_MAX_ATTEMPTS", "RUNS_MAX_INPUT_TOKENS", "RUNS_MAX_OUTPUT_TOKENS", "RUNS_MAX_COST_USD",
    "RUNS_MAX_QUEUED", "RUNS_MAX_ACTIVE_PER_READER", "RUNS_MAX_RUNNING_PER_READER",
    "RUNS_DEEP_CONCURRENCY", "RUNS_WORKER_CONCURRENCY", "RUNS_POLL_SECONDS",
    "RUNS_DB_POOL_SIZE", "RUNS_DB_ACQUIRE_SECONDS",
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
    #: Deep is the default depth, so this caps most runs.
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
    #: Reuse a query's embedding within one run (IR-953); on unless RUNS_QUERY_VECTOR_CACHE=off.
    query_vector_cache: bool = False
    #: Pooled connections per process; None opens one per use, as tests and scripts do (IR-1012).
    db_pool: "PoolSize | None" = None
    #: What a search hands the agent (IR-397, IR-1055); on unless switched off.
    selection: Policy = Policy()


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
    if str(getattr(values, "RUNS_QUERY_VECTOR_CACHE", "") or "").strip() not in ("", "off", "on"):
        found.append("RUNS_QUERY_VECTOR_CACHE must be on or off")
    for name in ("RUNS_JOIN_PASSAGES", "RUNS_SECTION_MATES"):
        if _text(values, name) not in ("", "off", "on"):
            found.append(f"{name} must be on or off")
    if _text(values, "RUNS_PASSAGE_TOKENS") and not _text(values, "RUNS_PASSAGE_TOKENS").isdigit():
        found.append("RUNS_PASSAGE_TOKENS must be a whole number; 0 turns it off")
    share = _text(values, "RUNS_PAPER_SHARE")
    if share and not (share.isdigit() and int(share) <= 100):
        found.append("RUNS_PAPER_SHARE must be a percent from 0 to 100; 0 turns it off")
    return found


def _text(values, name) -> str:
    return str(getattr(values, name, "") or "").strip()


def selection(values) -> Policy:
    """Passage selection, on by default (owner decision 2026-11-15, ADR-033 amendment)."""
    default = Policy()
    return Policy(
        paper_share=int(_text(values, "RUNS_PAPER_SHARE") or default.paper_share),
        join=_text(values, "RUNS_JOIN_PASSAGES") != "off",
        tokens_per_passage=int(_text(values, "RUNS_PASSAGE_TOKENS") or default.tokens_per_passage),
        section_mates=_text(values, "RUNS_SECTION_MATES") != "off",
    )


def query_vector_cache(values) -> bool:
    """On unless RUNS_QUERY_VECTOR_CACHE=off (IR-953, approved 2026-11-09)."""
    return str(getattr(values, "RUNS_QUERY_VECTOR_CACHE", "") or "").strip() != "off"


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
        query_vector_cache=query_vector_cache(values),
        selection=selection(values),
        db_pool=PoolSize(values.RUNS_DB_POOL_SIZE, values.RUNS_DB_ACQUIRE_SECONDS),
    )
