"""Run limits, read fail-closed (IR-722, ADR-049 §12).

Every limit is required; an unset one refuses admission. Nothing here is a
production value.
"""

from __future__ import annotations

from dataclasses import dataclass

EXECUTORS = ("deterministic",)
PROTOCOL = "runs-1"
SCHEMA = "0001_runs.sql"

LIMIT_NAMES = (
    "RUNS_DEADLINE_SECONDS", "RUNS_LEASE_SECONDS", "RUNS_MAX_ATTEMPTS",
    "RUNS_MAX_INPUT_TOKENS", "RUNS_MAX_OUTPUT_TOKENS", "RUNS_MAX_COST_USD",
)


class RunsUnavailable(Exception):
    """Runs are unconfigured; the routes answer `unavailable`."""


@dataclass(frozen=True)
class RunLimits:
    deadline_seconds: int
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


@dataclass(frozen=True)
class RunsConfig:
    database_url: str
    executor: str
    limits: RunLimits


def problems(values) -> list[str]:
    found = []
    if not getattr(values, "RUNS_DATABASE_URL", ""):
        found.append("RUNS_DATABASE_URL is required")
    if getattr(values, "RUNS_EXECUTOR", None) not in EXECUTORS:
        found.append(f"RUNS_EXECUTOR must be one of {', '.join(EXECUTORS)}")
    for name in LIMIT_NAMES:
        value = getattr(values, name, None)
        if value is None or value <= 0:
            found.append(f"{name} must be set and positive")
    return found


def read(values) -> RunsConfig:
    """From the gateway's settings; raises RunsUnavailable when incomplete."""
    if problems(values):
        raise RunsUnavailable
    return RunsConfig(
        database_url=values.RUNS_DATABASE_URL,
        executor=values.RUNS_EXECUTOR,
        limits=RunLimits(
            deadline_seconds=values.RUNS_DEADLINE_SECONDS,
            lease_seconds=values.RUNS_LEASE_SECONDS,
            max_attempts=values.RUNS_MAX_ATTEMPTS,
            max_input_tokens=values.RUNS_MAX_INPUT_TOKENS,
            max_output_tokens=values.RUNS_MAX_OUTPUT_TOKENS,
            max_cost_usd=values.RUNS_MAX_COST_USD,
        ),
    )
