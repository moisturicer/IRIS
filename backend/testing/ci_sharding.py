"""Opt-in, module-preserving CI partitioning (IR-810).

Each runner collects the same suite. Largest modules are assigned first to
the shard with the fewest tests; ties are stable. Items retain collection
order and a module never spans runners, including its migration/role fixtures.
"""

from collections import Counter

import pytest


def module_shards(nodeids, count):
    if count < 1:
        raise ValueError("shard count must be positive")
    sizes = Counter(nodeid.split("::", 1)[0] for nodeid in nodeids)
    loads = [0] * count
    assignments = {}
    for module in sorted(sizes, key=lambda name: (-sizes[name], name)):
        shard = min(range(count), key=lambda index: (loads[index], index))
        assignments[module] = shard + 1
        loads[shard] += sizes[module]
    return assignments


def pytest_addoption(parser):
    group = parser.getgroup("IRIS CI")
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
    assignments = module_shards([item.nodeid for item in items], count)
    selected, deselected = [], []
    for item in items:
        target = selected if assignments[item.nodeid.split("::", 1)[0]] == shard else deselected
        target.append(item)
    config.hook.pytest_deselected(items=deselected)
    items[:] = selected
