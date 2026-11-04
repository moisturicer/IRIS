"""One bounded AGENT Conversation over local research tools (IR-728, ADR-049 §13-16).

The executor with the recording provider and an in-memory stand-in for the
research tools. A deterministic provider proves the contract, never a
vendor's behaviour or answer quality.
"""

import asyncio
import dataclasses
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.admission.limits import Price  # noqa: E402
from ai.agent.budget import Bounds  # noqa: E402
from ai.agent.dialect import ChatCompletions  # noqa: E402
from ai.agent.assurance import LIMITATION  # noqa: E402
from ai.agent.executor import FINAL_NOTE, AgentExecutor  # noqa: E402
from ai.agent.protocol import Pin  # noqa: E402
from ai.infrastructure.recording_adapter import RecordingAgentProvider  # noqa: E402
from ai.research.tools import (  # noqa: E402
    NO_MATCH, OK, Coverage, PassageRef, RecordRef, Source, ToolResult,
)
from ai.runs import config as runs_config  # noqa: E402
from ai.runs.executor import PriorTurn, RunContext, Unavailable  # noqa: E402
from .test_ai_runtime_context_contract import MILLION, RESERVES  # noqa: E402

PIN = Pin(
    model="scripted-model", endpoint="scripted", adapter="recording", dialect=ChatCompletions.name,
    prompt_version="agent-research-1", tool_version="research-1", public_version=runs_config.PROTOCOL,
    state_version=runs_config.SCHEMA, data_policy="no-training", requires=("continuation",),
)
# Test bounds only; no production value is implied.
ORDINARY = Bounds(max_steps=4, max_tool_calls=6, max_no_progress=2, final_seconds=5, history_turns=4)
DEEP = Bounds(max_steps=8, max_tool_calls=12, max_no_progress=2, final_seconds=5, history_turns=4)
PROFILES = {"ordinary": ORDINARY, "deep": DEEP}
ALLOWANCE = {"max_attempts": 2, "max_input_tokens": 10_000_000, "max_output_tokens": 100_000,
             "max_cost_usd": 1.0}

FLOOD = "Rainfall gauges fed a neural network that predicted 87 floods."
POND = "Tilapia ponds were sampled weekly in brackish water."


def run(coro):
    return asyncio.run(coro)


def handle(prefix, n):
    return f"{prefix}{n:020x}"


class Corpus:
    """Two papers, a passage each; handles are fixed so scripts can cite them."""

    def __init__(self):
        self.papers = {
            1: ("Flood forecasting", Source(1, 11, "e1"), PassageRef(handle("P", 1), 1, 4, "Methods", FLOOD,
                                                                        Source(1, 11, "e1"))),
            2: ("Pond sampling", Source(2, 22, "e2"), PassageRef(handle("P", 2), 2, 2, "Methods", POND,
                                                                    Source(2, 22, "e2"))),
        }
        self.calls = []
        self.events = []
        self.ended = False
        self.replaced = set()

    def record(self, rid):
        title, source, _ = self.papers[rid]
        return RecordRef(handle("R", rid), rid, title, source)

    async def search(self, query, limit=10):
        self.calls.append(("search", query))
        hits = [rid for rid, (_, _, p) in self.papers.items()
                if any(w in p.text.lower() for w in query.lower().split())]
        if not hits:
            return ToolResult(NO_MATCH, coverage=Coverage(total=0))
        return ToolResult(OK, records=tuple(self.record(r) for r in hits),
                          passages=tuple(self.papers[r][2] for r in hits),
                          coverage=Coverage(len(hits), len(hits), False, 2))

    async def open_passage(self, passage):
        self.calls.append(("open_passage", passage))
        for rid, (_, source, p) in self.papers.items():
            if p.handle == passage:
                if rid in self.replaced:
                    return ToolResult.unavailable("source_replaced")
                return ToolResult(OK, passages=(p,), coverage=Coverage(1, 1))
        return ToolResult.unavailable("unknown_handle")

    async def read_page(self, paper, page):
        self.calls.append(("read_page", paper, page))
        return ToolResult(NO_MATCH, coverage=Coverage(total=0))

    async def outline(self, paper):
        self.calls.append(("outline", paper))
        return ToolResult(NO_MATCH)

    async def recall(self, record_ids):
        self.calls.append(("recall", tuple(record_ids)))
        return ToolResult(OK, records=tuple(self.record(r) for r in record_ids if r in self.papers))

    async def journal(self, name, data):
        if self.ended:
            return False
        self.events.append((name, data))
        return True


def call(id_, name, **arguments):
    return {"id": id_, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def tools(*calls, **message):
    return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": list(calls),
                                     **message}, "finish_reason": "tool_calls"}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 5}}


def reply(content, finish="stop"):
    return {"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 60, "completion_tokens": 20}}


def recording(*responses, paid=False):
    provider = RecordingAgentProvider(responses=list(responses), capabilities=("continuation",),
                                      capacities={"scripted-model": MILLION})
    provider.paid = paid
    return provider


def context(**kw):
    return RunContext(**{"allowance": ALLOWANCE, "remaining_seconds": 60, **kw})


def agent(provider, **kw):
    return AgentExecutor(provider, PIN, RESERVES, **{"profiles": PROFILES, **kw})


def ask(provider, corpus=None, question="Which paper predicts floods?", ctx=None, **kw):
    corpus = corpus or Corpus()
    return run(agent(provider, **kw).answer(question, corpus, ctx or context())), corpus


def models(corpus):
    return [data for name, data in corpus.events if name == "model"]


# --- One Conversation, direct and researched -----------------------------------

def test_a_direct_question_is_one_turn_of_the_same_agent_with_tools_offered():
    provider = recording(reply("A repository keeps papers; that is general background."))
    result, corpus = ask(provider, question="What is a repository?")
    assert result.answer == "A repository keeps papers; that is general background."
    [payload] = provider.requests
    assert payload["messages"][-1] == {"role": "user", "content": "What is a repository?"}
    assert {t["function"]["name"] for t in payload["tools"]} >= {"search", "open_passage", "read_page"}
    assert models(corpus) == [{"purpose": "agent", "phase": "gather", "step": 1}]
    assert corpus.calls == []


def test_a_search_then_answer_keeps_the_whole_exchange_intent_and_artifact():
    question = "Which paper predicts floods, and how?"
    provider = recording(
        tools(call("c-1", "search", query="flood rainfall"), reasoning_details={"sig": "opaque-1"}),
        reply(f"«Flood forecasting» trained on rainfall gauges and predicted 87 floods [{handle('P', 1)}]."),
    )
    result, corpus = ask(provider, question=question)

    assert result.answer == "«Flood forecasting» trained on rainfall gauges and predicted 87 floods [1]."
    [citation] = result.citations
    assert (citation.record_id, citation.page, citation.quote, citation.revision) == (1, 4, FLOOD, "11:e1")
    first, second = provider.requests
    assert first["messages"][0] == second["messages"][0]
    assert [m for m in second["messages"] if m["role"] == "user"] == [{"role": "user", "content": question}]
    assistant, result_message = second["messages"][-2:]
    assert assistant["tool_calls"][0]["id"] == "c-1"
    assert assistant["reasoning_details"] == {"sig": "opaque-1"}
    assert result_message["tool_call_id"] == "c-1" and FLOOD in result_message["content"]
    assert [m["phase"] for m in models(corpus)] == ["gather", "gather"]
    assert result.state == {"shown": [1], "selected": [], "excluded": []}


def test_parallel_calls_are_answered_whole_and_in_order():
    provider = recording(
        tools(call("a", "search", query="flood"), call("b", "search", query="tilapia")),
        reply("Both papers were found."),
    )
    ask(provider)
    tail = provider.requests[1]["messages"][-2:]
    assert [m["tool_call_id"] for m in tail] == ["a", "b"]
    assert "Pond sampling" in tail[1]["content"]


def test_no_tool_calls_a_model_and_every_attempt_records_the_one_agent_purpose():
    provider = recording(
        tools(call("a", "search", query="flood")),
        tools(call("b", "open_passage", passage=handle("P", 1))),
        reply(f"Found [{handle('P', 1)}]."),
    )
    result, corpus = ask(provider)
    assert len(provider.requests) == 3
    assert {m["purpose"] for m in models(corpus)} == {"agent"}
    instructions = {r["messages"][0]["content"] for r in provider.requests}
    assert len(instructions) == 1


# --- Bounds close research and keep the answer --------------------------------

def test_a_no_progress_loop_closes_research_and_finalizes_with_tools_declared_but_off():
    same = tools(call("x", "search", query="nothing-matches"))
    provider = recording(same, tools(call("y", "search", query="nothing-matches")),
                         reply("Nothing in the repository answers this."))
    result, corpus = ask(provider)
    assert result.answer == "Nothing in the repository answers this."
    final = provider.requests[-1]
    assert final["tool_choice"] == "none" and final["tools"]
    assert final["messages"][-1] == {"role": "user", "content": FINAL_NOTE}
    assert [m["phase"] for m in models(corpus)] == ["gather", "gather", "final"]


def test_the_step_bound_closes_research():
    bounded = {**PROFILES, "ordinary": Bounds(1, 6, 9, 5, 4)}
    provider = recording(tools(call("a", "search", query="flood")), reply(f"Yes [{handle('P', 1)}]."))
    result, corpus = ask(provider, profiles=bounded)
    assert [m["phase"] for m in models(corpus)] == ["gather", "final"]
    assert result.answer == "Yes [1]."


def test_calls_past_the_tool_bound_are_answered_not_run():
    bounded = {**PROFILES, "ordinary": Bounds(4, 1, 9, 5, 4)}
    provider = recording(tools(call("a", "search", query="flood"), call("b", "search", query="pond")),
                         reply("Partly read."))
    _, corpus = ask(provider, profiles=bounded)
    assert corpus.calls == [("search", "flood")]
    limited = provider.requests[1]["messages"][-2]
    assert limited["tool_call_id"] == "b" and json.loads(limited["content"]) == {"error": "tool_limit"}
    assert provider.requests[1]["tool_choice"] == "none"


def test_deep_selects_the_larger_configured_profile():
    steps = {**PROFILES, "ordinary": Bounds(1, 12, 9, 5, 4), "deep": Bounds(3, 12, 9, 5, 4)}
    for depth, gathers in (("ordinary", 1), ("deep", 3)):
        loop = [tools(call(f"d{n}", "search", query="flood")) for n in range(gathers)]
        provider = recording(*loop, reply("Done."))
        _, corpus = ask(provider, ctx=context(depth=depth), profiles=steps)
        assert [m["phase"] for m in models(corpus)].count("gather") == gathers


def test_too_little_time_left_skips_research_and_answers_directly():
    provider = recording(reply("Briefly: no time to search."))
    _, corpus = ask(provider, ctx=context(remaining_seconds=3))
    assert [m["phase"] for m in models(corpus)] == ["final"]
    assert provider.requests[0]["tool_choice"] == "none"


def test_the_token_allowance_keeps_a_final_answer_and_one_repair():
    first = recording(reply("x"))
    run(agent(first).answer("q", Corpus(), context()))
    sized = len(json.dumps(first.requests[0]))
    # Room for a final answer and its repair, not for a gathering turn too.
    allowance = {**ALLOWANCE, "max_input_tokens": 2 * sized + 2 * 300 + 100 + 400}
    provider = recording(reply("Answered within the reserve."))
    result, corpus = ask(provider, ctx=context(allowance=allowance), question="q")
    assert result.answer == "Answered within the reserve."
    assert [m["phase"] for m in models(corpus)] == ["final"]


def test_an_allowance_that_cannot_hold_the_final_answer_sends_nothing():
    provider = recording(reply("Never sent."))
    with pytest.raises(Unavailable) as refused:
        ask(provider, ctx=context(allowance={**ALLOWANCE, "max_input_tokens": 50}))
    assert refused.value.code == "allowance_exhausted"
    assert provider.requests == []


def test_the_cost_allowance_closes_research_by_price():
    provider = recording(reply("Answered without searching."), paid=True)
    provider.admitted = True
    # Cheap enough for two requests' worth, too dear for three.
    price = Price(input=1.0, output=1.0)
    first = recording(reply("x"))
    run(agent(first).answer("q", Corpus(), context()))
    sized = len(json.dumps(first.requests[0]))
    allowance = {**ALLOWANCE, "max_cost_usd": (2 * sized + 2 * 300 + 100 + 400 + 3 * 300) / 1e6}
    result, corpus = ask(provider, ctx=context(allowance=allowance), question="q", price=price)
    assert [m["phase"] for m in models(corpus)] == ["final"]


def test_a_paid_provider_without_a_price_is_unavailable():
    provider = recording(reply("Never sent."), paid=True)
    provider.admitted = True
    with pytest.raises(Unavailable) as refused:
        ask(provider)
    assert refused.value.code == "price_unknown"
    assert provider.requests == []


@pytest.mark.parametrize("final, code", [
    (tools(call("z", "search", query="flood")), "tool_only"),
    (reply("Half an ans", finish="length"), "length"),
])
def test_a_tool_only_or_truncated_final_turn_is_never_delivered(final, code):
    bounded = {**PROFILES, "ordinary": Bounds(1, 6, 9, 5, 4)}
    provider = recording(tools(call("a", "search", query="flood")), final)
    with pytest.raises(Unavailable) as refused:
        ask(provider, profiles=bounded)
    assert refused.value.code == code


def test_a_truncated_gathering_turn_is_not_an_answer():
    with pytest.raises(Unavailable) as refused:
        ask(recording(reply("Partial", finish="length")))
    assert refused.value.code == "length"


def test_stop_between_steps_admits_no_further_attempt():
    corpus = Corpus()
    provider = recording(tools(call("a", "search", query="flood")), reply("Never sent."))

    original = corpus.search

    async def search_then_stop(*args):
        corpus.ended = True
        return await original(*args)

    corpus.search = search_then_stop
    with pytest.raises(Unavailable) as refused:
        ask(provider, corpus)
    assert refused.value.code == "run_ended"
    assert len(provider.requests) == 1


# --- Checks on the first draft -------------------------------------------------

@pytest.mark.parametrize("draft", [
    f"Floods [{handle('P', 9)}].",
    "Floods [1].",
    f"It predicted 912 floods [{handle('P', 1)}].",
    f"«A paper nobody read» predicted floods [{handle('P', 1)}].",
    f"All papers agree [{handle('P', 1)}].",
])
def test_a_draft_failing_a_deterministic_check_twice_is_not_delivered(draft):
    # IR-729: the one repair repeats the mistake, and no sentence stands on its own.
    provider = recording(tools(call("a", "search", query="flood")), reply(draft), reply(draft))
    with pytest.raises(Unavailable) as refused:
        ask(provider)
    assert refused.value.code == "invalid_draft"
    assert len(provider.requests) == 3


def test_a_cited_source_replaced_before_commit_fails_safely():
    corpus = Corpus()
    provider = recording(tools(call("a", "search", query="flood")), reply(f"Floods [{handle('P', 1)}]."))
    original = corpus.search

    async def search_then_replace(*args):
        result = await original(*args)
        corpus.replaced.add(1)
        return result

    corpus.search = search_then_replace
    with pytest.raises(Unavailable) as refused:
        ask(provider, corpus)
    assert refused.value.code == "source_changed"


# --- One repair (IR-729) -------------------------------------------------------

def feedback(payload):
    return payload["messages"][-1]["content"]


def test_a_bad_page_and_a_wrong_count_are_corrected_once_in_the_same_conversation():
    bad = f"On page 9 it predicted 912 floods [{handle('P', 1)}]."
    good = f"On page 4 it predicted 87 floods [{handle('P', 1)}]."
    provider = recording(tools(call("a", "search", query="flood")), reply(bad), reply(good))
    result, corpus = ask(provider)

    assert result.answer == "On page 4 it predicted 87 floods [1]."
    assert [m["phase"] for m in models(corpus)] == ["gather", "gather", "repair"]
    draft, repair = provider.requests[1:]
    # The same ordered Conversation: everything sent before, then the draft, then the feedback.
    assert repair["messages"][:len(draft["messages"])] == draft["messages"]
    assert repair["messages"][-2] == {"role": "assistant", "content": bad}
    assert repair["messages"][0] == draft["messages"][0] and repair["tools"] == draft["tools"]
    assert repair["tool_choice"] == "none"
    note = feedback(repair)
    assert "9" in note and "912" in note and "unsupported_number" not in note


def test_a_second_invalid_draft_keeps_only_sentences_supported_on_their_own_and_says_so():
    good = f"It predicted 87 floods [{handle('P', 1)}]."
    # An uncited sentence is not supported by anything, however harmless it reads.
    bad = (f"{good} «A paper nobody read» agrees [{handle('P', 1)}].\n"
           "Gauges are cheap to install. Some 40 more papers agree.")
    provider = recording(tools(call("a", "search", query="flood")), reply(bad), reply(bad))
    result, corpus = ask(provider)
    assert result.answer == f"It predicted 87 floods [1].\n\n{LIMITATION}"
    [citation] = result.citations
    assert citation.page == 4
    # One repair, never a second.
    assert [m["phase"] for m in models(corpus)] == ["gather", "gather", "repair"]


def test_a_truncated_repair_falls_back_to_what_the_first_draft_supports():
    first = f"It predicted 87 floods [{handle('P', 1)}]. It predicted 912 more."
    provider = recording(tools(call("a", "search", query="flood")), reply(first), reply("Half", finish="length"))
    result, _ = ask(provider)
    assert result.answer == f"It predicted 87 floods [1].\n\n{LIMITATION}"


def test_a_source_replaced_before_the_repair_fences_delivery_and_sends_no_repair():
    corpus = Corpus()
    provider = recording(tools(call("a", "search", query="flood")),
                         reply(f"It predicted 912 floods [{handle('P', 1)}]."), reply("Never sent."))
    original = corpus.search

    async def search_then_replace(*args):
        result = await original(*args)
        corpus.replaced.add(1)
        return result

    corpus.search = search_then_replace
    with pytest.raises(Unavailable) as refused:
        ask(provider, corpus)
    assert refused.value.code == "source_changed"
    assert len(provider.requests) == 2


def test_a_source_revoked_during_the_repair_fences_the_repaired_answer():
    corpus = Corpus()

    def revoke_then_answer(payload):
        corpus.replaced.add(1)
        return reply(f"It predicted 87 floods [{handle('P', 1)}].")

    provider = recording(tools(call("a", "search", query="flood")),
                         reply(f"It predicted 912 floods [{handle('P', 1)}]."), revoke_then_answer)
    with pytest.raises(Unavailable) as refused:
        ask(provider, corpus)
    assert refused.value.code == "source_changed"
    assert len(provider.requests) == 3


def test_no_repair_is_sent_without_a_repair_reserve():
    no_repair = dataclasses.replace(RESERVES, repair_tokens=0)
    provider = recording(tools(call("a", "search", query="flood")),
                         reply(f"It predicted 912 floods [{handle('P', 1)}]."), reply("Never sent."))
    with pytest.raises(Unavailable) as refused:
        run(AgentExecutor(provider, PIN, no_repair, profiles=PROFILES).answer("q", Corpus(), context()))
    assert refused.value.code == "invalid_draft"
    assert len(provider.requests) == 2


def test_the_repair_is_charged_to_the_original_allowance():
    # The draft reports nearly the whole input allowance, so the reserved repair no longer fits.
    greedy = reply(f"It predicted 912 floods [{handle('P', 1)}].")
    greedy["usage"]["prompt_tokens"] = ALLOWANCE["max_input_tokens"] - 100
    provider = recording(tools(call("a", "search", query="flood")), greedy, reply("Never sent."))
    with pytest.raises(Unavailable) as refused:
        ask(provider)
    assert refused.value.code == "invalid_draft"
    assert len(provider.requests) == 2

    # Within the allowance, the repair's usage is counted with the rest of the run.
    provider = recording(tools(call("a", "search", query="flood")),
                         reply(f"It predicted 912 floods [{handle('P', 1)}]."),
                         reply(f"It predicted 87 floods [{handle('P', 1)}]."))
    result, _ = ask(provider)
    assert result.reported_units == (50 + 5) + 2 * (60 + 20)


def test_stop_before_the_repair_admits_no_repair():
    corpus = Corpus()
    provider = recording(tools(call("a", "search", query="flood")),
                         lambda payload: (setattr(corpus, "ended", True),
                                          reply(f"It predicted 912 floods [{handle('P', 1)}]."))[1],
                         reply("Never sent."))
    with pytest.raises(Unavailable) as refused:
        ask(provider, corpus)
    assert refused.value.code == "run_ended"
    assert len(provider.requests) == 2


# --- Tools confer nothing ------------------------------------------------------

@pytest.mark.parametrize("bad", [
    call("a", "search", query="flood", scope_record_id=2),
    call("a", "search", query="flood", reader_id=7),
    call("a", "update_plan", steps=[], max_steps=99),
    call("a", "read_page", paper=handle("R", 1), page="4"),
    call("a", "semantic_search", query="flood"),
])
def test_arguments_cannot_widen_scope_forge_identity_or_extend_allowance(bad):
    provider = recording(tools(bad), reply("Answered."))
    _, corpus = ask(provider)
    assert corpus.calls == []
    refused = json.loads(provider.requests[1]["messages"][-1]["content"])
    assert refused["error"] in ("invalid_arguments", "unknown_tool")


def test_the_task_list_keeps_stable_ids_and_records_actual_execution():
    plan = [{"id": "find", "title": "Find flood papers", "status": "in_progress"}]
    done = [{"id": "find", "title": "Find flood papers", "status": "done"},
            {"id": "compare", "title": "Compare methods", "status": "pending"}]
    dropped = [{"id": "compare", "title": "Compare methods", "status": "pending"}]
    provider = recording(
        tools(call("p1", "update_plan", steps=plan), call("s", "search", query="flood")),
        tools(call("p2", "update_plan", steps=done), call("p3", "update_plan", steps=dropped)),
        reply("Planned and read."),
    )
    _, corpus = ask(provider)
    plans = [data for name, data in corpus.events if name == "plan"]
    assert [p["revision"] for p in plans] == [1, 2]
    assert plans[0]["executed"] == {"tool_calls": 0, "evidence_reads": 0}
    assert plans[1]["executed"] == {"tool_calls": 2, "evidence_reads": 1}
    assert json.loads(provider.requests[2]["messages"][-1]["content"]) == {"error": "invalid_arguments"}


def test_plan_updates_alone_are_not_progress():
    plan = [{"id": "a", "title": "Think", "status": "pending"}]
    provider = recording(*[tools(call(f"p{n}", "update_plan", steps=plan)) for n in range(2)],
                         reply("Planned only."))
    _, corpus = ask(provider)
    assert [m["phase"] for m in models(corpus)] == ["gather", "gather", "final"]


# --- Follow-ups and clarification ---------------------------------------------

def test_a_follow_up_sees_the_shown_order_and_records_the_selection():
    prior = (PriorTurn("Which papers study water?", "Two papers [1] [2].", "answer"),)
    provider = recording(
        tools(call("f", "update_focus", selected=[handle("R", 2)], excluded=[handle("R", 1)])),
        tools(call("o", "open_passage", passage=handle("P", 2))),
        reply(f"The second one sampled ponds weekly [{handle('P', 2)}]."),
    )
    ctx = context(prior=prior, state={"shown": [1, 2], "selected": [], "excluded": []})
    result, corpus = ask(provider, ctx=ctx, question="Tell me about the second one.")

    messages = provider.requests[0]["messages"]
    assert messages[1:3] == [{"role": "user", "content": "Which papers study water?"},
                             {"role": "assistant", "content": "Two papers."}]
    shown = json.loads(messages[3]["content"].removeprefix("[IRIS conversation state] "))
    assert [(s["position"], s["title"]) for s in shown["shown"]] == [(1, "Flood forecasting"),
                                                                    (2, "Pond sampling")]
    assert messages[4] == {"role": "user", "content": "Tell me about the second one."}
    assert result.state == {"shown": [2], "selected": [2], "excluded": [1]}


def test_an_answer_without_citations_keeps_the_previous_shown_order_and_focus():
    ctx = context(state={"shown": [1, 2], "selected": [2], "excluded": []})
    result, _ = ask(recording(reply("Happy to help.")), ctx=ctx, question="Thanks!")
    assert result.state == {"shown": [1, 2], "selected": [2], "excluded": []}


def test_one_materially_necessary_clarification_and_never_two_in_a_row():
    provider = recording(tools(call("q", "ask_clarification", question="Which year do you mean?")))
    result, _ = ask(provider, question="What changed that year?")
    assert (result.kind, result.answer) == ("clarification", "Which year do you mean?")
    assert "ask_clarification" in {t["function"]["name"] for t in provider.requests[0]["tools"]}

    asked = (PriorTurn("What changed that year?", "Which year do you mean?", "clarification"),)
    provider = recording(reply("Without a year I can only describe the trend."))
    ask(provider, ctx=context(prior=asked), question="Never mind.")
    assert "ask_clarification" not in {t["function"]["name"] for t in provider.requests[0]["tools"]}


# --- Pins ---------------------------------------------------------------------

def test_research_without_configured_profiles_is_unsupported():
    provider = recording(reply("Never sent."))
    with pytest.raises(Unavailable) as refused:
        ask(provider, profiles=None)
    assert refused.value.code == "unsupported_pin"
    assert provider.requests == []


# --- Review fixes ---------------------------------------------------------------

def test_calls_in_a_truncated_turn_are_never_run():
    truncated = tools(call("a", "search", query="flood"))
    truncated["choices"][0]["finish_reason"] = "length"
    corpus = Corpus()
    with pytest.raises(Unavailable) as refused:
        ask(recording(truncated), corpus)
    assert refused.value.code == "malformed"
    assert corpus.calls == []


def test_no_second_clarification_in_a_row_even_without_carried_history():
    no_history = {**PROFILES, "ordinary": Bounds(4, 6, 2, 5, 0)}
    asked = (PriorTurn("What changed that year?", "Which year do you mean?", "clarification"),)
    provider = recording(reply("Without a year I can only describe the trend."))
    ask(provider, ctx=context(prior=asked), question="Never mind.", profiles=no_history)
    assert "ask_clarification" not in {t["function"]["name"] for t in provider.requests[0]["tools"]}
    assert [m["role"] for m in provider.requests[0]["messages"]] == ["system", "user"]


def test_a_follow_up_answered_without_tools_is_still_checked():
    ctx = context(prior=(PriorTurn("Which papers?", "One predicted 87 floods [1].", "answer"),),
                  state={"shown": [1], "selected": [], "excluded": []})
    # A number from a checked earlier Turn is supported; an invented title is not.
    result, _ = ask(recording(reply("It predicted 87 floods.")), ctx=ctx, question="How many?")
    assert result.answer == "It predicted 87 floods."
    invented = reply("«An invented study» agrees.")
    with pytest.raises(Unavailable) as refused:
        ask(recording(invented, invented), ctx=ctx, question="Who agrees?")
    assert refused.value.code == "invalid_draft"


def test_earlier_turns_reach_the_model_without_their_delivered_markers():
    ctx = context(prior=(PriorTurn("Which papers?", "Two papers [1] [2].", "answer"),))
    provider = recording(reply("Happy to help."))
    ask(provider, ctx=ctx, question="Thanks!")
    assert provider.requests[0]["messages"][2] == {"role": "assistant", "content": "Two papers."}


def test_citing_a_paper_the_reader_excluded_is_refused():
    ctx = context(state={"shown": [1], "selected": [], "excluded": [1]})
    excluded = reply(f"Floods [{handle('P', 1)}].")
    provider = recording(tools(call("a", "search", query="flood")), excluded, excluded)
    with pytest.raises(Unavailable) as refused:
        ask(provider, ctx=ctx)
    assert refused.value.code == "invalid_draft"


def test_a_run_ended_during_the_recheck_reports_that_not_a_changed_source():
    corpus = Corpus()
    provider = recording(tools(call("a", "search", query="flood")), reply(f"Floods [{handle('P', 1)}]."))

    async def ended(passage):
        return ToolResult.unavailable("run_ended")

    original = corpus.search

    async def search_then_end(*args):
        result = await original(*args)
        corpus.open_passage = ended
        return result

    corpus.search = search_then_end
    with pytest.raises(Unavailable) as refused:
        ask(provider, corpus)
    assert refused.value.code == "run_ended"


def test_the_deadline_bounds_a_send_even_without_admission():
    from ai.infrastructure.recording_adapter import HANG

    quick = {**PROFILES, "ordinary": Bounds(4, 6, 2, 0.05, 4)}
    with pytest.raises(Unavailable) as refused:
        ask(recording(HANG), ctx=context(remaining_seconds=0.3), profiles=quick)
    assert refused.value.code == "deadline"
