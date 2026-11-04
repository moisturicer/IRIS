"""Named papers and exact counts in the AGENT Conversation (IR-750, ADR-049 §9, §15).

The executor with the recording provider and an in-memory stand-in for the
research tools. A deterministic provider proves the contract, never a
vendor's behaviour or answer quality.
"""

import dataclasses
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.agent import assurance  # noqa: E402
from ai.agent.executor import AgentExecutor  # noqa: E402
from ai.agent.protocol import ToolCall  # noqa: E402
from ai.agent.tools import Investigation  # noqa: E402
from ai.research.tools import (  # noqa: E402
    AMBIGUOUS, NO_MATCH, OK, Count, Match, ToolResult,
)
from ai.runs.executor import Unavailable  # noqa: E402
from .test_ai_runtime_agent_loop_contract import (  # noqa: E402
    PIN, PROFILES, Corpus, call, context, handle, recording, reply, run, tools,
)
from .test_ai_runtime_context_contract import RESERVES  # noqa: E402
from .test_ai_runtime_agent_loop_contract import ask as ask_v1  # noqa: E402

PIN_2 = dataclasses.replace(PIN, prompt_version="agent-research-2", tool_version="research-2")
HYDROLOGY = Count(total=3, filters=(("classification", "Hydrology"),), population=frozenset({1, 2, 5}))


class Catalogue(Corpus):
    """The two-paper corpus, plus a third "Flood" paper and an exact Area count."""

    async def resolve(self, references=(), record_ids=()):
        self.calls.append(("resolve", tuple(references), tuple(record_ids)))
        if references == ["Flood"]:
            candidates = (self.record(1), dataclasses.replace(self.record(1), handle=handle("R", 3),
                                                              record_id=3, title="Flood risk maps"))
            return ToolResult(AMBIGUOUS, records=candidates,
                              matches=(Match(1, "title", "ambiguous", candidates, "title_phrase"),))
        if references == ["Pond sampling"]:
            return ToolResult(OK, records=(self.record(2),),
                              matches=(Match(1, "title", "exact_title", (self.record(2),)),))
        return ToolResult(NO_MATCH, matches=(Match(1, "title", "none"),))

    async def count(self, filters, group_by=None):
        self.calls.append(("count", dict(filters), group_by))
        if group_by == "year":
            return ToolResult(OK, count=dataclasses.replace(HYDROLOGY, group_by="year",
                                                            groups=((2022, 1), (2024, 2))))
        return ToolResult(OK, count=HYDROLOGY)


def ask(provider, question="How many Hydrology papers are there?"):
    corpus = Catalogue()
    agent = AgentExecutor(provider, PIN_2, RESERVES, profiles=PROFILES)
    return run(agent.answer(question, corpus, context())), corpus


def offered(request):
    return {t["function"]["name"] for t in request["tools"]}


def message_for(request, call_id):
    return next(m for m in request["messages"] if m.get("tool_call_id") == call_id)


# --- The pinned tool set -------------------------------------------------------

def test_only_the_research_2_pin_offers_resolve_and_count():
    provider = recording(reply("General background."))
    ask(provider)
    assert {"resolve_papers", "count_records"} <= offered(provider.requests[0])

    older = recording(reply("General background."))
    ask_v1(older)
    assert not {"resolve_papers", "count_records"} & offered(older.requests[0])


# --- Exact counts ----------------------------------------------------------------

def test_the_model_receives_a_typed_exact_count_and_may_state_it_as_a_total():
    provider = recording(
        tools(call("c", "count_records", classification="Hydrology")),
        reply("There are 3 papers in «Hydrology» of the records you can see."),
    )
    result, corpus = ask(provider)

    # The model's count, then the same count recomputed just before delivery.
    assert corpus.calls == [("count", {"classification": "Hydrology"}, None)] * 2
    sent = json.loads(message_for(provider.requests[1], "c")["content"])
    assert sent == {"status": "ok", "count": {
        "kind": "exact_count", "total": 3, "filters": {"classification": "Hydrology"},
        "group_by": None, "groups": [], "ungrouped": 0, "scope": "readable_records",
        "relative_to": "of the records you can see"}}
    # Only the two model turns: no screening or brief writer runs behind the tool.
    assert len(provider.requests) == 2
    assert result.answer == "There are 3 papers in «Hydrology» of the records you can see."
    assert result.facts == ({
        "kind": "exact_count", "total": 3, "filters": {"classification": "Hydrology"},
        "group_by": None, "groups": [], "ungrouped": 0, "scope_record_id": None,
        "relative_to": "of the records you can see", "population": [1, 2, 5]},)


def test_grouped_counts_reach_the_model_as_value_count_pairs():
    provider = recording(
        tools(call("c", "count_records", classification="Hydrology", group_by="year")),
        reply("Of the records you can see, 1 Hydrology paper is from 2022 and 2 are from 2024."),
    )
    result, _ = ask(provider)
    sent = json.loads(message_for(provider.requests[1], "c")["content"])
    assert sent["count"]["groups"] == [{"value": 2022, "count": 1}, {"value": 2024, "count": 2}]
    assert result.answer.startswith("Of the records you can see, 1 Hydrology paper")


def test_a_count_cannot_be_widened_by_scope_reader_or_topic_arguments():
    provider = recording(
        tools(call("a", "count_records", classification="Hydrology", record_id=9),
              call("b", "count_records", topic="floods"),
              call("c", "count_records", reader=4)),
        reply("I could not count those."),
    )
    _, corpus = ask(provider)
    assert [c for c in corpus.calls if c[0] == "count"] == []
    for call_id in "abc":
        assert json.loads(message_for(provider.requests[1], call_id)["content"]) == {
            "error": "invalid_arguments"}


# --- Samples are never promoted to totals -------------------------------------------

def investigation(*calls):
    """An investigation after running `(tool, arguments)` calls through its public entry."""
    found = Investigation(Catalogue(), metadata=True)
    for n, (name, arguments) in enumerate(calls):
        run(found.execute(ToolCall(f"c{n}", name, json.dumps(arguments))))
    return found


SEARCH = ("search", {"query": "flood"})
COUNT = ("count_records", {"classification": "Hydrology"})


def test_a_search_sample_stated_as_a_total_is_refused_even_beside_an_exact_count():
    counted = investigation(SEARCH, COUNT)
    cite = f"[{handle('P', 1)}]"

    assert assurance.findings(f"There are 3 Hydrology papers {cite}.", counted) == {}
    assert assurance.findings(f"There are 1 papers on flooding {cite}.", counted) == {
        "completeness_overclaim": ["There are"]}
    # Without an exact count, a completeness claim is never supported.
    assert "completeness_overclaim" in assurance.findings(
        f"There are 1 papers on flooding {cite}.", investigation(SEARCH))


def test_only_a_counts_total_lets_a_sentence_speak_of_a_total():
    grouped = investigation(SEARCH, ("count_records", {"classification": "Hydrology", "group_by": "year"}))
    cite = f"[{handle('P', 1)}]"
    # 2 is a group's size and 0 is the ungrouped remainder: neither is a total.
    for claim in (f"There are 2 papers on floods {cite}.", f"There are 0 other studies {cite}."):
        assert "completeness_overclaim" in assurance.findings(claim, grouped), claim
    assert assurance.findings(f"There are 3 Hydrology papers {cite}.", grouped) == {}


def test_a_quoted_area_name_is_not_mistaken_for_an_unknown_paper_title():
    counted = investigation(COUNT)
    assert assurance.findings("Of the records you can see, 3 are in “Hydrology”.", counted) == {}
    assert "unknown_title" in assurance.findings("Of the records you can see, 3 are in “Botany”.", counted)


def test_a_count_only_answer_is_still_checked_for_its_numbers():
    assert assurance.findings("Of the records you can see, 4 are in Hydrology.", investigation(COUNT)) == {
        "unsupported_number": ["4"]}


def test_the_turn_records_a_keyword_sample_as_never_exhaustive_and_no_unstated_count():
    provider = recording(
        tools(call("s", "search", query="flood"), call("c", "count_records", classification="Hydrology")),
        reply(f"One paper trained on rainfall gauges [{handle('P', 1)}]."),
    )
    result, _ = ask(provider, question="What did the flood paper do?")
    assert result.facts == ({"kind": "keyword_sample", "papers": 1, "exhaustive": False},)


class Shrinking(Catalogue):
    """A paper leaves the reader's population between counts."""

    def __init__(self):
        super().__init__()
        self.counted = 0

    async def count(self, filters, group_by=None):
        self.counted += 1
        await super().count(filters, group_by)
        if self.counted == 1:
            return ToolResult(OK, count=HYDROLOGY)
        return ToolResult(OK, count=dataclasses.replace(HYDROLOGY, total=2, population=frozenset({1, 2})))


def ask_with(corpus, provider, question="How many Hydrology papers are there?"):
    agent = AgentExecutor(provider, PIN_2, RESERVES, profiles=PROFILES)
    return run(agent.answer(question, corpus, context()))


def test_a_count_that_changed_before_delivery_is_not_delivered():
    provider = recording(
        tools(call("c", "count_records", classification="Hydrology")),
        reply("Of the records you can see, there are 3 papers in Hydrology."),
    )
    with pytest.raises(Unavailable) as refused:
        ask_with(Shrinking(), provider)
    assert refused.value.code == "source_changed"


def test_a_recount_replaces_the_earlier_count_in_the_turns_facts():
    provider = recording(
        tools(call("a", "count_records", classification="Hydrology")),
        tools(call("b", "count_records", classification="Hydrology")),
        reply("Of the records you can see, there are 2 papers in Hydrology, down from 3 a moment ago."),
    )
    # The recount and the delivery recheck both see the current, smaller population.
    result = ask_with(Shrinking(), provider)
    [fact] = result.facts
    assert (fact["total"], fact["population"]) == (2, [1, 2])


# --- Named papers ------------------------------------------------------------------

def test_an_ambiguous_name_yields_candidates_and_a_focused_clarification():
    provider = recording(
        tools(call("r", "resolve_papers", references=["Flood"])),
        tools(call("q", "ask_clarification",
                   question="Do you mean «Flood forecasting» or «Flood risk maps»?")),
    )
    result, _ = ask(provider, question="Summarise the Flood paper.")
    sent = json.loads(message_for(provider.requests[1], "r")["content"])
    assert sent["status"] == "ambiguous"
    assert sent["matches"] == [{"reference": 1, "kind": "title", "match": "ambiguous",
                                "basis": "title_phrase", "papers": [
                                    {"paper": handle("R", 1), "title": "Flood forecasting"},
                                    {"paper": handle("R", 3), "title": "Flood risk maps"}]}]
    assert result.kind == "clarification"
    assert result.answer == "Do you mean «Flood forecasting» or «Flood risk maps»?"


def test_a_resolved_paper_handle_reads_and_its_title_may_be_named():
    provider = recording(
        tools(call("r", "resolve_papers", references=["Pond sampling"])),
        tools(call("p", "outline", paper=handle("R", 2))),
        reply("«Pond sampling» has no outline I could read."),
    )
    result, corpus = ask(provider, question="Outline Pond sampling.")
    assert ("outline", handle("R", 2)) in corpus.calls
    assert result.answer == "«Pond sampling» has no outline I could read."
