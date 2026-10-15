"""The controller's bounds, read from settings with no defaults (spec §7)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

from django.conf import settings

from apps.ai.providers.deadline import time_left
from apps.ai.research.context import Budget

#: Spec §7's initial fake-test profile. A fixture, not a production limit.
FAKE_TEST_PROFILE = {
    "AI_CONTROLLER_MAX_ROUNDS": 4,
    "AI_CONTROLLER_MAX_TOOL_CALLS": 6,
    "AI_CONTROLLER_MAX_CONCURRENT_READS": 2,
    "AI_CONTROLLER_REPAIR_ATTEMPTS": 1,
    "AI_CONTROLLER_ANSWER_RESERVE_TOKENS": 4000,
    "AI_CONTROLLER_ANSWER_RESERVE_SECONDS": 5.0,
}


class NotConfigured(Exception):
    """A limit is unset; the controller refuses rather than guess one."""


@dataclass(frozen=True)
class ControllerBudget:
    max_rounds: int
    max_tool_calls: int
    max_concurrent_reads: int
    repair_attempts: int
    answer_reserve_tokens: int
    answer_reserve_seconds: float

    @classmethod
    def from_settings(cls) -> "ControllerBudget":
        values = {name: getattr(settings, name, None) for name in FAKE_TEST_PROFILE}
        unset = sorted(name for name, value in values.items() if value is None)
        if unset:
            raise NotConfigured(", ".join(unset))
        budget = cls(*values.values())
        if min(budget.max_rounds, budget.max_tool_calls, budget.max_concurrent_reads) < 1:
            raise NotConfigured("controller limits must be positive")
        return budget

    @property
    def answer_attempts(self) -> int:
        """The answer plus its repair slots, reserved before any research."""
        return 1 + self.repair_attempts

    @property
    def reserved_tokens(self) -> int:
        return self.answer_reserve_tokens * self.answer_attempts

    @property
    def reserved_seconds(self) -> float:
        return self.answer_reserve_seconds * self.answer_attempts

    def run_budget(self) -> Budget:
        """The registry's Budget, inside the run's original deadline."""
        base = Budget.from_settings()
        seconds = base.wall_clock_seconds
        left: Optional[float] = time_left()
        if left is not None:
            seconds = min(seconds, max(0.0, left))
        return replace(
            base, max_outer_rounds=self.max_rounds, max_calls_per_subtask=self.max_tool_calls,
            max_tool_calls=self.max_tool_calls, wall_clock_seconds=seconds,
        )
