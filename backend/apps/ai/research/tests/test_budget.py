"""Each ADR-038 §5 limit stops the run when exceeded (IR-509)."""

import pytest

from apps.ai.research.budget import BudgetExhausted, Spend
from apps.ai.research.context import Budget


def _budget(**overrides):
    values = dict(
        max_outer_rounds=3, max_calls_per_subtask=4, max_tool_calls=10,
        wall_clock_seconds=90.0, max_prompt_tokens=120_000,
        max_ledger_passages=30, read_token_cap=3000,
    )
    values.update(overrides)
    return Budget(**values)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_outer_rounds_stop_at_the_limit():
    spend = Spend(_budget(max_outer_rounds=2))
    spend.begin_round()
    spend.begin_round()
    with pytest.raises(BudgetExhausted, match="max_outer_rounds"):
        spend.begin_round()


def test_calls_per_subtask_stop_and_reset_with_the_next_subtask():
    spend = Spend(_budget(max_calls_per_subtask=2))
    spend.begin_subtask()
    spend.charge_call()
    spend.charge_call()
    with pytest.raises(BudgetExhausted, match="max_calls_per_subtask"):
        spend.charge_call()
    spend.begin_subtask()
    spend.charge_call()


def test_total_calls_stop_across_subtasks():
    spend = Spend(_budget(max_calls_per_subtask=4, max_tool_calls=5))
    for _ in range(5):
        if spend.subtask_calls == 4:
            spend.begin_subtask()
        spend.charge_call()
    spend.begin_subtask()
    with pytest.raises(BudgetExhausted, match="max_tool_calls"):
        spend.charge_call()
    assert spend.tool_calls == 5


def test_wall_clock_stops_the_run():
    clock = Clock()
    spend = Spend(_budget(wall_clock_seconds=90), clock=clock)
    clock.now = 60
    assert spend.time_left() == 30
    spend.charge_call()
    clock.now = 90
    assert spend.time_left() == 0
    with pytest.raises(BudgetExhausted, match="wall_clock_seconds"):
        spend.charge_call()
    with pytest.raises(BudgetExhausted, match="wall_clock_seconds"):
        spend.begin_round()


def test_prompt_tokens_stop_the_run():
    spend = Spend(_budget(max_prompt_tokens=1000))
    spend.charge_prompt_tokens(600)
    with pytest.raises(BudgetExhausted, match="max_prompt_tokens"):
        spend.charge_prompt_tokens(401)
    assert spend.prompt_tokens == 1001
