"""Opt-in, module-preserving CI partitioning (IR-810).

Each runner collects the same suite. Modules with the greatest measured duration go first to
the shard with the lowest estimated time; ties are stable. Items retain collection
order and a module never spans runners, including its migration/role fixtures.
"""

from collections import Counter
from pathlib import Path

from testing.timings import load_timings

import pytest


def module_shards(nodeids, count, durations=None):
    if count < 1:
        raise ValueError("shard count must be positive")
    sizes = Counter(nodeid.split("::", 1)[0] for nodeid in nodeids)
    durations = durations or {}
    weights = {module: durations.get(module, size * 0.2) for module, size in sizes.items()}
    loads = [0.0] * count
    assignments = {}
    for module in sorted(sizes, key=lambda name: (-weights[name], name)):
        shard = min(range(count), key=lambda index: (loads[index], index))
        assignments[module] = shard + 1
        loads[shard] += weights[module]
    return assignments


def pytest_addoption(parser):
    group = parser.getgroup("IRIS CI")
    group.addoption("--ci-timings", default=str(Path(__file__).with_name("module_durations.json")))
    group.addoption("--ci-shard", type=int, default=None)
    group.addoption("--ci-shards", type=int, default=None)


def pytest_configure(config):
    shard = config.getoption("ci_shard")
    count = config.getoption("ci_shards")
    if shard is None and count is None:
        return
    if shard is None or count is None or not 1 <= shard <= count:
        raise pytest.UsageError("supply both --ci-shard and --ci-shards, with 1 <= shard <= shards")


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    shard = config.getoption("ci_shard")
    if shard is None:
        return
    count = config.getoption("ci_shards")
    try:
        durations = load_timings(config.getoption("ci_timings"))
    except (ValueError, OSError) as exc:
        raise pytest.UsageError(f"invalid CI timings: {exc}") from exc
    assignments = module_shards([item.nodeid for item in items], count, durations)
    selected, deselected = [], []
    for item in items:
        target = selected if assignments[item.nodeid.split("::", 1)[0]] == shard else deselected
        target.append(item)
    config.hook.pytest_deselected(items=deselected)
    items[:] = selected
