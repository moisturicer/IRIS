"""Run limits fail closed (IR-722, ADR-049 §12)."""

import pytest

from ai.infrastructure.settings import Settings
from ai.runs import config

COMPLETE = dict(
    RUNS_DATABASE_URL="postgresql://runtime@db/iris", RUNS_DEADLINE_SECONDS=120,
    RUNS_LEASE_SECONDS=30, RUNS_MAX_ATTEMPTS=2, RUNS_MAX_INPUT_TOKENS=1000,
    RUNS_MAX_OUTPUT_TOKENS=500, RUNS_MAX_COST_USD=0.5,
    RUNS_DEEP_DEADLINE_SECONDS=600, RUNS_MAX_QUEUED=20, RUNS_MAX_ACTIVE_PER_READER=3,
    RUNS_MAX_RUNNING_PER_READER=1, RUNS_DEEP_CONCURRENCY=1, RUNS_WORKER_CONCURRENCY=2,
    RUNS_POLL_SECONDS=2,
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


def test_each_depth_keeps_its_own_deadline():
    limits = config.read(settings()).limits
    assert limits.deadline_for("ordinary") == 120
    assert limits.deadline_for("deep") == 600
    with pytest.raises(ValueError):
        limits.deadline_for("thorough")


def test_dispatch_bounds_are_read_unchanged():
    cfg = config.read(settings())
    assert cfg.dispatch == config.Dispatch(
        max_queued=20, max_active_per_reader=3, max_running_per_reader=1,
        deep_concurrency=1, worker_concurrency=2, poll_seconds=2,
    )
    assert cfg.redis_url == ""


def test_deep_work_cannot_take_every_worker_slot():
    # Equal values would leave ordinary questions no protected slot.
    assert "RUNS_DEEP_CONCURRENCY must be below RUNS_WORKER_CONCURRENCY" in config.problems(
        settings(RUNS_DEEP_CONCURRENCY=2, RUNS_WORKER_CONCURRENCY=2)
    )
