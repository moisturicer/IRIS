"""The research-5 search the AGENT is offered (IR-886, ADR-049 §9).

The executor with the recording provider and an in-memory stand-in for the
research tools: proves the tool contract and the pin, never answer quality.
"""

import dataclasses
import json

# Imported first: it puts the repository root, and so `ai`, on the path.
from .test_ai_runtime_agent_loop_contract import (
    PIN, PROFILES, Corpus, call, context, handle, recording, reply, run, tools,
)
from .test_ai_runtime_context_contract import RESERVES

from ai.admission.guard import _sources  # noqa: E402
from ai.agent.protocol import ToolResult as Sent  # noqa: E402
from ai.agent.executor import AgentExecutor  # noqa: E402
from ai.research.tools import NO_MATCH, ToolResult  # noqa: E402

PIN_4 = dataclasses.replace(PIN, prompt_version="agent-research-4", tool_version="research-4")
PIN_5 = dataclasses.replace(PIN, prompt_version="agent-research-5", tool_version="research-5")


class HybridCorpus(Corpus):
    def __init__(self, signals=(("keyword", "ok"), ("semantic", "ok"), ("rerank", "off"))):
        super().__init__()
        self.signals = signals

    async def hybrid_search(self, query, limit=10, filters=None):
        self.calls.append(("hybrid_search", query, limit, filters))
        found = await Corpus.search(self, query, limit)
        self.calls.pop()
        return dataclasses.replace(found, signals=self.signals)


def ask(provider, corpus, *, pin):
    executor = AgentExecutor(provider, pin, RESERVES, profiles=PROFILES)
    return run(executor.answer("Which paper predicts floods?", corpus, context())), corpus


def offered(provider, name="search"):
    return next(t["function"] for t in provider.requests[0]["tools"] if t["function"]["name"] == name)


def test_research_5_offers_one_search_with_metadata_filters_and_passes_them_through():
    provider = recording(
        tools(call("s", "search", query="floods", year_from=2020, classification="Engineering")),
        reply(f"It predicted 87 floods [{handle('P', 1)}]."))
    corpus = HybridCorpus()
    result, _ = ask(provider, corpus, pin=PIN_5)
    params = offered(provider)["parameters"]["properties"]
    assert {"query", "classification", "psced", "record_type", "year_from", "year_to"} <= set(params)
    assert not any(t["function"]["name"] == "semantic_search" for t in provider.requests[0]["tools"])
    searches = [c for c in corpus.calls if c[0] != "open_passage"]
    assert searches == [("hybrid_search", "floods", 10, {"year_from": 2020, "classification": "Engineering"})]
    shown = json.loads(provider.requests[1]["messages"][-1]["content"])
    assert shown["search"] == {"keyword": "ok", "semantic": "ok", "rerank": "off"}
    assert result.answer


def test_an_earlier_pin_keeps_its_keyword_search_and_cannot_filter():
    provider = recording(
        tools(call("s", "search", query="floods", year_from=2020)),
        tools(call("t", "search", query="floods")),
        reply(f"It predicted 87 floods [{handle('P', 1)}]."))
    corpus = HybridCorpus()
    ask(provider, corpus, pin=PIN_4)
    assert "year_from" not in offered(provider)["parameters"]["properties"]
    assert json.loads(provider.requests[1]["messages"][-1]["content"]) == {"error": "invalid_arguments"}
    assert [c for c in corpus.calls if c[0] != "open_passage"] == [("search", "floods")]


def test_a_keyword_only_no_match_says_meaning_search_was_unavailable_and_may_be_sent():
    provider = recording(tools(call("s", "search", query="inundation")), reply("Nothing was found."))
    corpus = HybridCorpus(signals=(("keyword", "ok"), ("semantic", "provider_gated"), ("rerank", "off")))
    ask(provider, corpus, pin=PIN_5)
    content = provider.requests[1]["messages"][-1]["content"]
    shown = json.loads(content)
    assert shown["status"] == NO_MATCH and shown["search"]["semantic"] == "provider_gated"
    # A content-free control result passes the send guard; it carries no source.
    assert _sources([Sent("s", content, control_only=True)]) == frozenset()


def test_an_unlisted_failure_reason_is_shown_only_as_unavailable():
    provider = recording(tools(call("s", "search", query="floods")),
                         reply(f"It predicted 87 floods [{handle('P', 1)}]."))
    corpus = HybridCorpus(signals=(("keyword", "ok"), ("semantic", "campaign_exhausted"), ("rerank", "off")))
    ask(provider, corpus, pin=PIN_5)
    assert json.loads(provider.requests[1]["messages"][-1]["content"])["search"]["semantic"] == "unavailable"


def test_invalid_filter_arguments_are_refused_before_any_search():
    provider = recording(
        tools(call("s", "search", query="floods", year_from="2020"),
              call("t", "search", query="floods", record_type="")),
        reply("Refused."))
    corpus = HybridCorpus()
    ask(provider, corpus, pin=PIN_5)
    assert corpus.calls == []


def test_a_refused_filter_value_reaches_the_model_and_may_be_sent():
    refused = ToolResult.unavailable("unknown_filter_value")

    class Unknown(HybridCorpus):
        async def hybrid_search(self, query, limit=10, filters=None):
            return refused

    provider = recording(tools(call("s", "search", query="floods", classification="Nope")), reply("No such Area."))
    ask(provider, Unknown(), pin=PIN_5)
    content = provider.requests[1]["messages"][-1]["content"]
    assert json.loads(content) == {"status": "unavailable", "reason": "unknown_filter_value",
                                   "coverage": {"returned": 0, "total": None, "truncated": False}}
    assert _sources([Sent("s", content, control_only=True)]) == frozenset()
