"""Follow-ups, exact counts and listings get past the send guard (IR-994, ADR-049).

The executor with a recording provider that applies the guard's own provenance
check to every request, as the admitted transport does before a paid send.
"""

import dataclasses
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.admission.guard import _sources  # noqa: E402
from ai.agent.executor import WITHHELD_ANSWER, WITHHELD_SUMMARY, AgentExecutor  # noqa: E402
from ai.agent.protocol import ToolResult as Entry  # noqa: E402
from ai.infrastructure.recording_adapter import RecordingAgentProvider  # noqa: E402
from ai.research.tools import OK, Count, Coverage, Source, ToolResult  # noqa: E402
from ai.runs.executor import PriorTurn  # noqa: E402
from .test_ai_runtime_agent_loop_contract import (  # noqa: E402
    MILLION, PIN, PROFILES, Corpus, call, context, reply, run, tools,
)
from .test_ai_runtime_context_contract import RESERVES  # noqa: E402

PIN_2 = dataclasses.replace(PIN, prompt_version="agent-research-2", tool_version="research-2")
HYDROLOGY = Count(total=3, filters=(("classification", "Hydrology"),), population=frozenset({1, 2, 5}))


class Guarded(RecordingAgentProvider):
    """Refuses a request the guard's provenance check would refuse."""

    async def converse(self, request):
        _sources([e for e in request.history if isinstance(e, Entry)
                  or getattr(e, "dependencies", frozenset())
                  or getattr(e, "unverified_provenance", False)])
        return await super().converse(request)


def guarded(*responses):
    return Guarded(responses=list(responses), capabilities=("continuation",),
                   capacities={"scripted-model": MILLION})


class Catalogue(Corpus):
    async def count(self, filters, group_by=None):
        self.calls.append(("count", dict(filters), group_by))
        return ToolResult(OK, count=HYDROLOGY)


def test_an_exact_count_reaches_the_model_and_is_answered():
    provider = guarded(
        tools(call("c", "count_records", classification="Hydrology")),
        reply("There are 3 papers in «Hydrology» of the records you can see."),
    )
    agent = AgentExecutor(provider, PIN_2, RESERVES, profiles=PROFILES)
    result = run(agent.answer("How many Hydrology papers are there?", Catalogue(), context()))
    assert len(provider.requests) == 2
    assert result.answer == "There are 3 papers in «Hydrology» of the records you can see."


PIN_6 = dataclasses.replace(PIN, prompt_version="agent-research-6", tool_version="research-6")


class Listing(Catalogue):
    async def list_records(self, filters, limit=None):
        self.calls.append(("list", dict(filters)))
        records = (dataclasses.replace(self.record(1), year=2024), dataclasses.replace(self.record(2), year=None))
        fact = Count(total=2, filters=(("classification", "Hydrology"),), population=frozenset({1, 2}))
        return ToolResult(OK, records=records, count=fact, coverage=Coverage(2, 2))

    async def count(self, filters, group_by=None):
        self.calls.append(("count", dict(filters), group_by))
        return ToolResult(OK, count=Count(total=2, filters=(("classification", "Hydrology"),),
                                          population=frozenset({1, 2})))


def offered(request):
    return {t["function"]["name"] for t in request["tools"]}


def test_only_the_research_6_pin_offers_list_records():
    provider = guarded(reply("General background."))
    run(AgentExecutor(provider, PIN_6, RESERVES, profiles=PROFILES).answer("Hello", Listing(), context()))
    assert "list_records" in offered(provider.requests[0])
    older = guarded(reply("General background."))
    run(AgentExecutor(older, PIN_2, RESERVES, profiles=PROFILES).answer("Hello", Listing(), context()))
    assert "list_records" not in offered(older.requests[0])


def test_a_listing_reaches_the_model_and_its_titles_may_be_named_as_complete():
    provider = guarded(
        tools(call("l", "list_records", classification="Hydrology")),
        reply("All 2 papers in «Hydrology» of the records you can see: «Flood forecasting» and "
              "«Pond sampling»."),
    )
    corpus = Listing()
    result = run(AgentExecutor(provider, PIN_6, RESERVES, profiles=PROFILES).answer(
        "List the Hydrology papers.", corpus, context()))
    sent = json.loads(next(m for m in provider.requests[1]["messages"]
                           if m.get("tool_call_id") == "l")["content"])
    assert sent["list"]["total"] == 2 and not sent["list"]["truncated"]
    assert [p["title"] for p in sent["list"]["papers"]] == ["Flood forecasting", "Pond sampling"]
    assert result.answer.startswith("All 2 papers")


FLOOD_SOURCE, POND_SOURCE = Source(1, 11, "e1"), Source(2, 22, "e2")
EARLIER = "Rainfall gauges fed a neural network in «Flood forecasting»."


class Screened(Guarded):
    """A transport that can carry every source except `withdrawn`."""

    withdrawn = frozenset()

    async def eligible(self, pin, sources):
        return frozenset(sources) - self.withdrawn


def screened(*responses, withdrawn=()):
    provider = Screened(responses=list(responses), capabilities=("continuation",),
                        capacities={"scripted-model": MILLION})
    provider.withdrawn = frozenset(withdrawn)
    return provider


def follow_up(provider, sources):
    prior = (PriorTurn("Which paper predicts floods?", EARLIER, "answer", 1, sources),)
    agent = AgentExecutor(provider, PIN_2, RESERVES, profiles=PROFILES)
    return run(agent.answer("How many floods did it predict?", Corpus(), context(prior=prior)))


def sent_text(request):
    return json.dumps(request["messages"], ensure_ascii=False)


def test_a_follow_up_sends_the_earlier_answer_with_its_sources():
    provider = screened(reply("General background."))
    follow_up(provider, frozenset({FLOOD_SOURCE}))
    assert EARLIER in sent_text(provider.requests[0])


def test_an_earlier_answer_whose_paper_can_no_longer_be_sent_is_withheld_not_refused():
    provider = screened(reply("General background."), withdrawn=[FLOOD_SOURCE])
    result = follow_up(provider, frozenset({FLOOD_SOURCE}))
    sent = sent_text(provider.requests[0])
    assert EARLIER not in sent and WITHHELD_ANSWER in sent
    assert "Which paper predicts floods?" in sent
    assert result.answer == "General background."


def test_an_answer_records_every_source_it_read_and_those_its_history_carried():
    provider = screened(
        tools(call("s", "search", query="ponds")),
        reply("General background."),
    )
    result = follow_up(provider, frozenset({FLOOD_SOURCE}))
    assert result.sources == {FLOOD_SOURCE, POND_SOURCE}


class Failing(Screened):
    async def eligible(self, pin, sources):
        raise ConnectionError("database unreachable")


def test_a_failed_source_check_withholds_the_earlier_answer_and_the_run_continues():
    provider = Failing(responses=[reply("General background.")], capabilities=("continuation",),
                       capacities={"scripted-model": MILLION})
    result = follow_up(provider, frozenset({FLOOD_SOURCE}))
    assert WITHHELD_ANSWER in sent_text(provider.requests[0])
    assert result.answer == "General background."


def test_an_unverifiable_summary_of_earlier_turns_is_withheld_not_refused():
    saved = {"goal": "Water papers.", "preferences": [], "findings": [], "limitations": [], "plan": [],
             "shown": [], "selected": [], "excluded": [], "turns": [1], "sources": [],
             "format": "agent-handoff-1", "derived": True}
    provider = screened(reply("General background."))
    agent = AgentExecutor(provider, PIN_2, RESERVES, profiles=PROFILES)
    ctx = context(handoff={"revision": 1, "through_ordinal": 1, "body": saved})
    result = run(agent.answer("Which was it?", Corpus(), ctx))
    assert WITHHELD_SUMMARY in sent_text(provider.requests[0])
    assert result.answer == "General background."
