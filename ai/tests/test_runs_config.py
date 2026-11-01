"""Run limits fail closed (IR-722, ADR-049 §12)."""

import pytest

from ai.infrastructure.settings import Settings
from ai.runs import config

COMPLETE = dict(
    RUNS_DATABASE_URL="postgresql://runtime@db/iris", RUNS_DEADLINE_SECONDS=120,
    RUNS_LEASE_SECONDS=30, RUNS_MAX_ATTEMPTS=2, RUNS_MAX_INPUT_TOKENS=1000,
    RUNS_MAX_OUTPUT_TOKENS=500, RUNS_MAX_COST_USD=0.5,
)


def settings(**overrides):
    return Settings(_env_file=None, **{**COMPLETE, **overrides})


def test_complete_limits_become_the_persisted_allowance():
    cfg = config.read(settings())
    assert cfg.limits.allowance() == {
        "max_attempts": 2, "max_input_tokens": 1000, "max_output_tokens": 500, "max_cost_usd": 0.5,
    }


@pytest.mark.parametrize("name", config.LIMIT_NAMES)
def test_any_unset_limit_refuses_runs(name):
    with pytest.raises(config.RunsUnavailable):
        config.read(settings(**{name: None}))
    assert f"{name} must be set and positive" in config.problems(settings(**{name: None}))


def test_no_paid_executor_can_be_selected():
    assert config.problems(settings(RUNS_EXECUTOR="openai")) == [
        "RUNS_EXECUTOR must be one of deterministic"
    ]


def test_runs_need_a_database():
    with pytest.raises(config.RunsUnavailable):
        config.read(settings(RUNS_DATABASE_URL=""))
