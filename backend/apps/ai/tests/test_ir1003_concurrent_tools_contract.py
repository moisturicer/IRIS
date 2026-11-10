"""A tool group's read-only calls run together and read as a sequential run (IR-1003).

The executor with the recording provider and IR-728's in-memory research
stand-in, slowed down so overlap is measurable. A deterministic contract,
never a vendor's latency.
"""

import asyncio
import dataclasses
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.research.tools import EARLIER_COMMITTED  # noqa: E402
from ai.runs import agent_profile  # noqa: E402

from .test_ai_runtime_agent_loop_contract import (  # noqa: E402
    ORDINARY, PROFILES, Corpus, ask, call, recording, reply, tools,
)

DELAY = 0.4


class SlowCorpus(Corpus):
    """Each search takes `delays[query]` seconds, and journals as `_call` does: after every earlier call."""

    def __init__(self, delays):
        super().__init__()
        self.delays = delays
        self.journalled = []

    async def search(self, query, limit=10):
        await asyncio.sleep(self.delays.get(query, DELAY))
        result = await super().search(query, limit)
        earlier = EARLIER_COMMITTED.get()
        if earlier is not None:
            await earlier.wait()
        self.journalled.append(query)
        return result


def two_searches():
    return recording(
        tools(call("a", "search", query="flood"), call("b", "search", query="tilapia")),
        reply("Both papers were found."),
    )


def timed(corpus, concurrency, provider=None):
    provider = provider or two_searches()
    started = time.perf_counter()
    ask(provider, corpus, tool_concurrency=concurrency)
    return time.perf_counter() - started, provider


def test_two_searches_in_one_group_take_one_searchs_wait():
    elapsed, _ = timed(SlowCorpus({}), 2)
    assert elapsed < DELAY * 1.75


def test_one_at_a_time_is_unchanged_by_default():
    elapsed, _ = timed(SlowCorpus({}), 1)
    assert elapsed >= DELAY * 2


def test_the_model_reads_exactly_what_a_sequential_run_gives_it():
    _, together = timed(SlowCorpus({}), 2)
    _, alone = timed(SlowCorpus({}), 1)
    assert together.requests == alone.requests
    tail = together.requests[1]["messages"][-2:]
    assert [m["tool_call_id"] for m in tail] == ["a", "b"]


def test_a_later_call_that_finishes_first_still_journals_second():
    corpus = SlowCorpus({"flood": DELAY, "tilapia": 0.05})
    timed(corpus, 2)
    assert corpus.journalled == ["flood", "tilapia"]


def test_a_call_past_the_tool_limit_is_answered_and_never_fetched():
    corpus = SlowCorpus({})
    provider = recording(
        tools(call("a", "search", query="flood"), call("b", "search", query="tilapia"),
              call("c", "search", query="ponds")),
        reply("Both papers were found."),
    )
    limited = {**PROFILES, "ordinary": dataclasses.replace(ORDINARY, max_tool_calls=2)}
    ask(provider, corpus, tool_concurrency=4, profiles=limited)
    assert [c for c in corpus.calls if c[0] == "search"] == [("search", "flood"), ("search", "tilapia")]
    [answered] = [m for m in provider.requests[-1]["messages"] if m.get("tool_call_id") == "c"]
    assert '"tool_limit"' in answered["content"]


def test_the_setting_is_optional_and_bounded():
    def read(value):
        return agent_profile._tool_concurrency(type("V", (), {"RUNS_AGENT_TOOL_CONCURRENCY": value}))
    assert read("") == 1 and read("4") == 4
    for bad in ("0", "17", "two", "-1"):
        with pytest.raises(agent_profile.NotConfigured, match="RUNS_AGENT_TOOL_CONCURRENCY"):
            read(bad)


def test_the_executor_refuses_a_cap_below_one():
    with pytest.raises(ValueError, match="tool_concurrency"):
        ask(two_searches(), SlowCorpus({}), tool_concurrency=0)
