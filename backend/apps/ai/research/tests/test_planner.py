import json
from dataclasses import replace

import pytest

from apps.ai.providers.fakes import ScriptedLLM, ScriptedToolCallingLLM
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.providers.tool_calling import ToolResultMessage
from apps.ai.research.planner import ResearchPlanner
from apps.ai.research.context import Budget, RunContext

from .helpers import TOPIC, root

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def planning(*calls):
    return ScriptedToolCallingLLM([
        ScriptedToolCallingLLM.calling(name, json.dumps(args), f"call-{i}")
        for i, (name, args) in enumerate(calls)
    ])


def run(corpus, embedder, planner, **limits):
    stack = root(embedder)
    ctx = RunContext.for_request(
        user=corpus["student"], root=stack, lane="research",
        budget=replace(Budget.from_settings(), **limits),
    )
    return ResearchPlanner(stack, planner=planner, answer_llm=ScriptedLLM()).answer(TOPIC, ctx)


def test_a_search_then_finish_returns_a_cited_answer(corpus, embedder):
    model = planning(("search_passages", {"query": TOPIC}), ("finish", {}))
    result = run(corpus, embedder, model)
    assert result.answer.state == "generated"
    assert result.answer.citations
    assert result.stop_reason == "finish"
    assert result.source_handles[1].startswith("E")
    assert "Secret flood draft" not in str(model.conversation_requests)


def test_duplicate_is_fed_back_and_spends_the_inner_budget(corpus, embedder):
    model = planning(*[("search_passages", {"query": TOPIC})] * 3)
    result = run(corpus, embedder, model, max_calls_per_subtask=2)
    assert result.stop_reason == "max_calls_per_subtask"
    assert "stopped" in result.answer.text
    assert [step for step in result.steps if step.kind == "tool"][-1].duplicate is True


def test_two_malformed_calls_end_planning_and_use_the_pipeline(corpus, embedder):
    model = planning(("read_record_sections", {"record": "R999"}), ("unknown", {}))
    result = run(corpus, embedder, model)
    assert result.stop_reason == "malformed_call"
    assert result.fallback is True
    assert result.answer.state in ("generated", "no_sources", "unavailable")
    messages = model.conversation_requests[1].messages
    assert any(isinstance(m, ToolResultMessage) and "correct" in m.content for m in messages)


@pytest.mark.parametrize("limit, value, reason", [
    ("max_tool_calls", 1, "max_tool_calls"),
    ("max_calls_per_subtask", 1, "max_calls_per_subtask"),
    ("max_outer_rounds", 0, "max_outer_rounds"),
    ("max_prompt_tokens", 0, "max_prompt_tokens"),
    ("wall_clock_seconds", 0, "wall_clock_seconds"),
])
def test_each_planning_budget_stops_the_run(corpus, embedder, limit, value, reason):
    model = planning(*[("search_passages", {"query": TOPIC})] * 5)
    result = run(corpus, embedder, model, **{limit: value})
    assert result.stop_reason == reason
    assert len(model.conversation_requests) <= 1


def test_provider_failure_with_evidence_synthesizes_without_another_search(corpus, embedder):
    model = ScriptedToolCallingLLM([
        ScriptedToolCallingLLM.calling("search_passages", json.dumps({"query": TOPIC}), "a"),
        LLMUnavailable("a timeout whose body must not reach telemetry"),
    ])
    result = run(corpus, embedder, model)
    assert result.fallback is False
    assert result.answer.citations
    assert result.stop_reason == "planner_unavailable"
    assert "stopped" in result.answer.text


@pytest.mark.parametrize("reply, code", [
    ("An invented citation [99].", "unknown_citation"),
    ("The result measured 987654 percent [1].", "unsupported_number"),
    ("«An invented paper» agrees [1].", "unknown_title"),
    ("Every paper agrees [1].", "completeness_overclaim"),
])
def test_validation_withholds_the_answer_and_keeps_sources(corpus, embedder, reply, code):
    stack = root(embedder)
    ctx = RunContext.for_request(user=corpus["student"], root=stack, lane="research")
    model = planning(("search_passages", {"query": TOPIC}), ("finish", {}))
    result = ResearchPlanner(stack, planner=model, answer_llm=ScriptedLLM(reply=reply)).answer(TOPIC, ctx)
    assert code in result.validation_codes
    assert result.answer.state == "unavailable"
    assert result.answer.sources
    assert reply not in result.answer.text
    assert "withheld" in result.answer.text


def test_empty_ledger_needs_no_answering_model(corpus, embedder, settings):
    settings.LLM_ANSWER_MODEL = ""
    settings.LLM_MODEL = ""
    stack = root(embedder, permits=lambda record: False)
    ctx = RunContext.for_request(user=corpus["student"], root=stack, lane="research")
    result = ResearchPlanner(stack, planner=planning(("finish", {}))).answer(TOPIC, ctx)
    assert result.answer.state == "no_sources"


def test_both_models_down_still_return_the_pipeline_sources(corpus, embedder):
    class UnavailableLLM(ScriptedLLM):
        def generate(self, system, user):
            raise LLMUnavailable("down")
    stack = root(embedder)
    ctx = RunContext.for_request(user=corpus["student"], root=stack, lane="research")
    result = ResearchPlanner(stack, planner=ScriptedToolCallingLLM([LLMUnavailable("down")]), answer_llm=UnavailableLLM()).answer(TOPIC, ctx)
    assert result.fallback is True
    assert result.answer.state == "unavailable"
    assert result.answer.sources


def test_planner_cannot_widen_scope_with_arguments(corpus, embedder):
    model = planning(("search_passages", {"query": TOPIC, "scope_record_id": None}), ("finish", {}))
    result = run(corpus, embedder, model)
    assert result.answer.state == "no_sources"
    assert any(step.status == "rejected" for step in result.steps)


def test_a_late_planner_response_cannot_start_an_answer_call(corpus, embedder):
    from .test_budget import Clock
    clock = Clock()
    stack = root(embedder)
    ctx = RunContext.for_request(user=corpus["student"], root=stack, lane="research")
    def late(request):
        if len(model.conversation_requests) == 1:
            return ScriptedToolCallingLLM.calling("search_passages", json.dumps({"query": TOPIC}), "search")
        clock.now = 100
        return ScriptedToolCallingLLM.calling("finish", "{}", "stop")
    model = ScriptedToolCallingLLM(late)
    answerer = ScriptedLLM()
    result = ResearchPlanner(stack, planner=model, answer_llm=answerer, clock=clock).answer(TOPIC, ctx)
    assert result.stop_reason == "wall_clock_seconds"
    assert result.answer.sources
    assert answerer.calls == []
