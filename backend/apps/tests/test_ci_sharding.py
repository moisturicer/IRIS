"""IR-810: all collected tests run exactly once across isolated CI jobs."""

from collections import Counter
import os
from pathlib import Path
import subprocess
import sys

import pytest

from testing.ci_sharding import module_shards


def test_partition_is_complete_disjoint_deterministic_and_keeps_modules_together():
    nodeids = [f"test_{module}.py::test_{item}" for module in range(13) for item in range(module + 1)]
    assignments = module_shards(nodeids, 4)
    assert assignments == module_shards(reversed(nodeids), 4)
    partitions = [[node for node in nodeids if assignments[node.split("::")[0]] == shard]
                  for shard in range(1, 5)]
    assert Counter(node for partition in partitions for node in partition) == Counter(nodeids)
    assert all(partitions)
    loads = [len(partition) for partition in partitions]
    assert max(loads) - min(loads) <= 13
    for module in assignments:
        assert sum(any(node.startswith(module + "::") for node in partition) for partition in partitions) == 1


def test_invalid_count_is_refused():
    with pytest.raises(ValueError):
        module_shards(["test_a.py::test_one"], 0)


@pytest.fixture
def run_pytest(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    for module in range(4):
        (tmp_path / f"test_{module}.py").write_text(
            "def test_first(): pass\ndef test_second(): pass\n", encoding="utf-8"
        )
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    env.pop("PYTEST_ADDOPTS", None)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])

    def run(*args):
        return subprocess.run(
            [sys.executable, "-m", "pytest", "-p", "testing.ci_sharding", "-q", *args],
            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30,
        )

    return run


def test_real_pytest_collection_runs_every_test_once_and_preserves_order(run_pytest):
    whole = run_pytest("--collect-only")
    assert whole.returncode == 0, whole.stdout + whole.stderr
    expected = [line for line in whole.stdout.splitlines() if "::" in line]
    actual = []
    for shard in range(1, 5):
        result = run_pytest("--collect-only", "--ci-shard", str(shard), "--ci-shards", "4")
        assert result.returncode == 0, result.stdout + result.stderr
        selected = [line for line in result.stdout.splitlines() if "::" in line]
        assert selected == [node for node in expected if node in selected]
        actual.extend(selected)
        executed = run_pytest("--ci-shard", str(shard), "--ci-shards", "4")
        assert executed.returncode == 0, executed.stdout + executed.stderr
        assert "2 passed, 6 deselected" in executed.stdout
    assert len(expected) == 8
    assert Counter(actual) == Counter(expected)


def test_a_failing_test_fails_its_shard(run_pytest, tmp_path):
    (tmp_path / "test_0.py").write_text(
        "def test_first(): assert False\ndef test_second(): pass\n", encoding="utf-8"
    )
    failed = run_pytest("--ci-shard", "1", "--ci-shards", "4")
    assert failed.returncode == 1
    assert "1 failed, 1 passed, 6 deselected" in failed.stdout


def test_an_empty_shard_is_not_successful(run_pytest):
    empty = run_pytest("--ci-shard", "5", "--ci-shards", "5")
    assert empty.returncode == 5


@pytest.mark.parametrize("args", [
    ["--ci-shard", "1"], ["--ci-shards", "4"],
    ["--ci-shard", "0", "--ci-shards", "4"],
    ["--ci-shard", "5", "--ci-shards", "4"],
    ["--ci-shard", "1", "--ci-shards", "0"],
])
def test_bad_configuration_cannot_silently_run_a_partial_suite(run_pytest, args):
    result = run_pytest(*args)
    assert result.returncode == 4
    assert "supply both --ci-shard and --ci-shards" in result.stderr


def test_duration_weights_balance_slow_small_modules():
    ids = [f"apps/test_{i}.py::test_{j}" for i in range(4) for j in range(10 if i > 1 else 1)]
    durations = {f"apps/test_{i}.py": seconds for i, seconds in enumerate([90, 80, 10, 20])}
    assigned = module_shards(ids, 2, durations)
    loads = [sum(durations[m] for m, shard in assigned.items() if shard == target) for target in (1, 2)]
    assert loads == [100, 100]
    assert assigned == module_shards(reversed(ids), 2, durations)


def test_unseen_modules_use_seconds_per_test():
    ids = ["apps/test_old.py::one", "apps/test_new.py::one", "apps/test_new.py::two"]
    assigned = module_shards(ids, 2, {"apps/test_old.py": 0.3})
    assert assigned["apps/test_new.py"] == 1
    assert assigned["apps/test_old.py"] == 2


def test_invalid_timing_file_refuses_to_select_a_shard(run_pytest, tmp_path):
    timings = tmp_path / "broken.json"
    timings.write_text('{"apps/test_a.py": -10}')
    result = run_pytest("--ci-shard", "1", "--ci-shards", "4", "--ci-timings", str(timings))
    assert result.returncode == 4
    assert "invalid CI timings" in result.stderr
