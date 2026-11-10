"""A research tool fails part-way and the supported findings survive (IR-731, ADR-049 §15-16).

The executor with the recording provider and an in-memory stand-in whose
tools can fail. A deterministic provider proves the contract, never a
vendor's behaviour or answer quality.
"""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.agent import assurance  # noqa: E402
from ai.agent.executor import AgentExecutor  # noqa: E402
from ai.research.tools import NO_MANUSCRIPT, NO_MATCH, OK, Count, Coverage, ToolResult  # noqa: E402
from .test_ai_runtime_agent_loop_contract import (  # noqa: E402
    FLOOD, PROFILES, call, context, handle, recording, reply, run, tools,
)
from ai.runs.executor import Unavailable  # noqa: E402
from .test_ai_runtime_context_contract import RESERVES  # noqa: E402
from .test_ai_runtime_metadata_contract import PIN_2, Catalogue  # noqa: E402


class Outage(ConnectionError):
    """What a dropped database connection looks like to the agent."""


class Failing(Catalogue):
    """The catalogue, with named operations failing as an outage would."""

    def __init__(self, *failing):
        super().__init__()
        self.failing = set(failing)

    async def read_page(self, paper, page):
        if ("read_page", paper) in self.failing:
            self.calls.append(("read_page", paper, page))
            raise Outage("connection reset")
        return await super().read_page(paper, page)

    async def search(self, query, limit=10):
        if ("search", query) in self.failing:
            self.calls.append(("search", query))
            raise Outage("connection reset")
        return await super().search(query, limit)

    async def count(self, filters, group_by=None):
        if "count" in self.failing:
            self.calls.append(("count", dict(filters), group_by))
            raise Outage("connection reset")
        return await super().count(filters, group_by)


def ask(provider, corpus, question="Compare the flood and pond papers."):
    """research-2 offers every research tool, counts included."""
    executor = AgentExecutor(provider, PIN_2, RESERVES, profiles=PROFILES)
    return run(executor.answer(question, corpus, context()))


def result_for(request, call_id):
    return json.loads(next(m for m in request["messages"] if m.get("tool_call_id") == call_id)["content"])


P1, P2 = handle("P", 1), handle("P", 2)
R2 = handle("R", 2)


# --- An outage after useful evidence ------------------------------------------------

def test_a_failed_read_after_evidence_keeps_the_supported_finding_and_says_what_failed():
    corpus = Failing(("read_page", R2))
    provider = recording(
        tools(call("s", "search", query="flood tilapia")),
        tools(call("r", "read_page", paper=R2, page=2)),
        reply(f"«Flood forecasting» predicted 87 floods from rainfall gauges [{P1}]. "
              "The pond paper's results page could not be read, so the two cannot be compared yet."),
    )
    result = ask(provider, corpus)

    assert result.kind == "answer"
    assert result.answer.startswith("«Flood forecasting» predicted 87 floods from rainfall gauges [1].")
    assert result.answer.endswith(assurance.outage_limitation(["read_page"]))
    [citation] = result.citations
    assert (citation.record_id, citation.quote) == (1, FLOOD)
    # The model was told the read failed, not that the page was empty.
    assert result_for(provider.requests[2], "r") == {"status": "unavailable", "reason": "tool_unavailable"}


# --- An outage is never an absence -----------------------------------------------

@pytest.mark.parametrize("draft", [
    "There are 0 Hydrology papers.",
    "No Hydrology papers exist in the repository.",
    "None of the papers are in Hydrology.",
    "I found zero records in Hydrology.",
])
def test_a_failed_count_is_never_stated_as_zero_or_none(draft):
    corpus = Failing("count")
    provider = recording(
        tools(call("c", "count_records", classification="Hydrology")),
        reply(draft),
        reply("The number of Hydrology papers could not be counted just now."),
    )
    result = ask(provider, corpus, question="How many Hydrology papers are there?")

    assert result.answer == ("The number of Hydrology papers could not be counted just now.\n\n"
                             + assurance.outage_limitation(["count_records"]))
    assert result.facts == ()
    # The repair was asked for: the zero or absence went back to the model.
    assert len(provider.requests) == 3
    assert result_for(provider.requests[1], "c") == {"status": "unavailable", "reason": "tool_unavailable"}


# --- Four different kinds of "nothing", told apart ----------------------------------

class Bare(Failing):
    """Paper 2 has no Manuscript read; a year count leaves one paper without a year."""

    async def read_page(self, paper, page):
        if paper == R2:
            self.calls.append(("read_page", paper, page))
            return ToolResult(NO_MATCH, NO_MANUSCRIPT, coverage=Coverage(total=0))
        return await super().read_page(paper, page)

    async def count(self, filters, group_by=None):
        self.calls.append(("count", dict(filters), group_by))
        return ToolResult(OK, count=Count(total=3, group_by="year", groups=((2022, 2),), ungrouped=1,
                                          population=frozenset({1, 2, 5})))


GROUP = {
    "absent": call("absent", "read_page", paper=R2, page=2),
    "ungrouped": call("ungrouped", "count_records", group_by="year"),
    "nomatch": call("nomatch", "search", query="volcano"),
    "outage": call("outage", "search", query="mangrove"),
    "malformed": {"id": "malformed", "type": "function",
                  "function": {"name": "read_page", "arguments": "{not json"}},
}


@pytest.mark.parametrize("order", [
    ("absent", "ungrouped", "nomatch", "outage", "malformed"),
    ("outage", "malformed", "nomatch", "ungrouped", "absent"),
    ("nomatch", "outage", "absent", "malformed", "ungrouped"),
])
def test_unavailable_absent_unmatched_and_malformed_are_distinct_in_any_order(order):
    corpus = Bare(("search", "mangrove"))
    provider = recording(
        tools(call("s", "search", query="flood")),
        tools(*(GROUP[name] for name in order)),
        reply(f"«Flood forecasting» predicted 87 floods [{P1}]. One of three papers has no recorded year."),
    )
    result = ask(provider, corpus)

    final = provider.requests[2]
    tail = [m for m in final["messages"] if m["role"] == "tool"][-len(order):]
    # Every call in the group is answered, in the order it was made.
    assert [m["tool_call_id"] for m in tail] == list(order)
    seen = {name: result_for(final, name) for name in order}
    assert seen["outage"] == {"status": "unavailable", "reason": "tool_unavailable"}
    assert seen["absent"]["status"] == "no_match" and seen["absent"]["reason"] == NO_MANUSCRIPT
    assert seen["nomatch"]["status"] == "no_match" and "reason" not in seen["nomatch"]
    assert seen["ungrouped"]["count"]["ungrouped"] == 1
    assert seen["malformed"] == {"error": "invalid_arguments"}
    # Only the outage is an outage; the rest are answers.
    assert result.answer.endswith(assurance.outage_limitation(["search"]))
    assert result.answer.startswith("«Flood forecasting» predicted 87 floods [1].")


def test_a_missing_paper_value_is_not_invented():
    corpus = Bare()
    provider = recording(
        tools(call("c", "count_records", group_by="year")),
        reply("The third paper was completed in 2019."),
        reply("Two papers were completed in 2022; one has no recorded year."),
    )
    result = ask(provider, corpus, question="When were the papers completed?")
    assert result.answer == "Two papers were completed in 2022; one has no recorded year."
    assert "2019" in provider.requests[2]["messages"][-1]["content"]


# --- Completeness and final assurance still hold -------------------------------------

@pytest.mark.parametrize("claim, phrase", [
    ("A complete literature search found one flood paper", "complete literature search"),
    ("A comprehensive search found one flood paper", "comprehensive search"),
    ("Searching every paper found one flood paper", "Searching every"),
])
def test_a_complete_literature_search_is_never_claimed(claim, phrase):
    corpus = Failing(("search", "mangrove"))
    provider = recording(
        tools(call("s", "search", query="flood"), call("m", "search", query="mangrove")),
        reply(f"{claim}: «Flood forecasting» [{P1}]."),
        reply(f"«Flood forecasting» predicted 87 floods [{P1}]."),
    )
    result = ask(provider, corpus)
    assert result.answer.startswith("«Flood forecasting» predicted 87 floods [1].")
    # Sent back for the one repair, never delivered.
    assert repr(phrase) in provider.requests[2]["messages"][-1]["content"]


def test_an_exact_count_that_succeeded_still_states_its_total_beside_an_outage():
    corpus = Failing(("search", "mangrove"))
    provider = recording(
        tools(call("c", "count_records", classification="Hydrology"), call("m", "search", query="mangrove")),
        reply("There are 3 Hydrology papers of the records you can see."),
    )
    result = ask(provider, corpus, question="How many Hydrology papers are there, and do any study mangroves?")
    assert result.answer.startswith("There are 3 Hydrology papers of the records you can see.")
    assert [f["kind"] for f in result.facts] == ["exact_count"]
    assert result.answer.endswith(assurance.outage_limitation(["search"]))


def test_when_both_repairs_fail_too_the_answer_is_kept_its_absence_claim_marked_and_the_outage_said():
    corpus = Failing(("read_page", R2))
    bad = reply(f"«Flood forecasting» predicted 87 floods [{P1}]. No pond papers report results.")
    provider = recording(
        tools(call("s", "search", query="flood")),
        tools(call("r", "read_page", paper=R2, page=2)),
        bad, bad, bad,
    )
    result = ask(provider, corpus)
    assert result.answer == "\n\n".join([
        f"«Flood forecasting» predicted 87 floods [1]. No pond papers report results. {assurance.QUALIFIER}",
        assurance.outage_limitation(["read_page"]),
    ])


def test_a_recheck_that_cannot_reach_its_source_is_unavailable_not_a_crash():
    class RecheckOutage(Failing):
        async def open_passage(self, passage):
            raise Outage("connection reset")

    provider = recording(tools(call("s", "search", query="flood")),
                         reply(f"«Flood forecasting» predicted 87 floods [{P1}]."))
    with pytest.raises(Unavailable) as ended:
        ask(provider, RecheckOutage())
    assert ended.value.code == "tool_unavailable"


def test_a_revoked_reader_still_ends_the_run_however_many_tools_failed():
    class Revoked(Failing):
        async def read_page(self, paper, page):
            return ToolResult.unavailable("unauthorized")

    provider = recording(tools(call("m", "search", query="mangrove")),
                         tools(call("r", "read_page", paper=R2, page=2)), reply("unused"))
    with pytest.raises(Unavailable) as ended:
        ask(provider, Revoked(("search", "mangrove")))
    assert ended.value.code == "unauthorized"


def test_a_necessary_clarification_after_an_outage_is_still_asked():
    question = "Did you mean the flood paper, or none of these?"
    provider = recording(
        tools(call("m", "search", query="mangrove")),
        tools(call("q", "ask_clarification", question=question)),
    )
    result = ask(provider, Failing(("search", "mangrove")), question="Tell me about that paper.")
    assert (result.kind, result.answer) == ("clarification", question)


def test_the_honest_hedge_the_limitation_uses_is_not_a_completeness_claim():
    provider = recording(
        tools(call("s", "search", query="flood"), call("m", "search", query="mangrove")),
        reply(f"«Flood forecasting» predicted 87 floods [{P1}]. This is not a complete search."),
    )
    result = ask(provider, Failing(("search", "mangrove")))
    assert result.answer.startswith("«Flood forecasting» predicted 87 floods [1]. This is not a complete search.")
    assert len(provider.requests) == 2


def test_a_permission_refusal_is_not_an_outage_and_ends_the_run():
    import asyncpg

    class Refused(Failing):
        async def read_page(self, paper, page):
            raise asyncpg.InsufficientPrivilegeError("permission denied for table research_chunks")

    provider = recording(tools(call("s", "search", query="flood")),
                         tools(call("r", "read_page", paper=R2, page=2)), reply("unused"))
    with pytest.raises(Unavailable) as ended:
        ask(provider, Refused())
    assert ended.value.code == "unauthorized"


def test_a_bug_in_the_runtime_is_not_disguised_as_an_outage():
    class Broken(Failing):
        async def read_page(self, paper, page):
            raise KeyError("chunk_set_id")

    provider = recording(tools(call("r", "read_page", paper=R2, page=2)), reply("unused"))
    with pytest.raises(KeyError):
        ask(provider, Broken())
