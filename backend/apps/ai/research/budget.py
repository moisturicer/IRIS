"""A run's spend against its Budget; every limit stops the run (ADR-038 §5)."""

from __future__ import annotations

import time
from typing import Callable

from .context import Budget


class BudgetExhausted(Exception):
    """A limit was reached. The message is the limit's name."""


class Spend:
    def __init__(self, budget: Budget, clock: Callable[[], float] = time.monotonic) -> None:
        self._budget = budget
        self._clock = clock
        self._started = clock()
        self.rounds = 0
        self.subtask_calls = 0
        self.tool_calls = 0
        self.prompt_tokens = 0

    def time_left(self) -> float:
        """What a vendor call may take: `min(per-call timeout, time_left())`."""
        return max(0.0, self._budget.wall_clock_seconds - (self._clock() - self._started))

    def begin_round(self) -> None:
        self._check_clock()
        if self.rounds >= self._budget.max_outer_rounds:
            raise BudgetExhausted("max_outer_rounds")
        self.rounds += 1
        self.subtask_calls = 0

    def begin_subtask(self) -> None:
        self._check_clock()
        self.subtask_calls = 0

    def charge_call(self) -> None:
        self._check_clock()
        if self.tool_calls >= self._budget.max_tool_calls:
            raise BudgetExhausted("max_tool_calls")
        if self.subtask_calls >= self._budget.max_calls_per_subtask:
            raise BudgetExhausted("max_calls_per_subtask")
        self.tool_calls += 1
        self.subtask_calls += 1

    def charge_prompt_tokens(self, tokens: int) -> None:
        self.prompt_tokens += tokens
        if self.prompt_tokens > self._budget.max_prompt_tokens:
            raise BudgetExhausted("max_prompt_tokens")

    def _check_clock(self) -> None:
        if self.time_left() <= 0:
            raise BudgetExhausted("wall_clock_seconds")
