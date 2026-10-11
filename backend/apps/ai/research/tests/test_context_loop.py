import json
from dataclasses import replace

import pytest

from apps.ai.models import Conversation, Turn, TurnCitation
from apps.ai.providers.fakes import ScriptedLLM, ScriptedToolCallingLLM
from apps.ai.research.context import Budget, RunContext
from apps.ai.research.planner import ResearchPlanner

from .helpers import TOPIC, root
from .test_planner import planning

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def test_planner_reads_recent_answers_but_no_recalled_or_restricted_exchange(corpus, embedder, settings):
    settings.AI_HISTORY_TOKEN_BUDGET = 300
    conversation = Conversation.objects.create(user=corpus["student"])
    Turn.objects.create(conversation=conversation, question="Old memory question",
                        answer="RECALLED_ONLY " * 500, state="generated")
    restricted = Turn.objects.create(conversation=conversation, question="PRIVATE_QUESTION",
                                     answer="PRIVATE_ANSWER", state="generated")
    TurnCitation.objects.create(turn=restricted, marker=1, record=corpus["draft"])
    Turn.objects.create(conversation=conversation, question="Recent rainfall question",
                        answer="RECENT_VISIBLE_ANSWER", state="generated")
    stack = root(embedder)
    ctx = RunContext.for_request(user=corpus["student"], root=stack,
                                 lane="research", conversation=conversation)
    model = planning(("search_passages", {"query": TOPIC}), ("finish", {}))
    ResearchPlanner(stack, planner=model, answer_llm=ScriptedLLM()).answer(TOPIC, ctx)
    sent = str(model.conversation_requests)
    assert "RECENT_VISIBLE_ANSWER" in sent
    assert "Recent rainfall question" in sent
    assert "PRIVATE_QUESTION" not in sent
    assert "PRIVATE_ANSWER" not in sent
    assert "RECALLED_ONLY" not in sent


def script(*calls):
    return ScriptedToolCallingLLM([
        ScriptedToolCallingLLM.calling(name, json.dumps(args), f"step-{i}", text=note)
        for i, (name, args, note) in enumerate(calls)
    ])


def execute(corpus, embedder, model, *, stack=None, conversation=None, answerer=None, **limits):
    stack = stack or root(embedder)
    ctx = RunContext.for_request(
        user=corpus["student"], root=stack, lane="research", conversation=conversation,
        budget=replace(Budget.from_settings(), **limits),
    )
    answerer = answerer or ScriptedLLM()
    result = ResearchPlanner(stack, planner=model, answer_llm=answerer).answer(TOPIC, ctx)
    return result, answerer


def test_first_subtask_can_finish_without_executing_the_rest_of_the_plan(corpus, embedder):
    model = script(
        ("plan_research", {"subtasks": ["Find findings", "Compare methods"]}, "Plan notes"),
        ("search_passages", {"query": TOPIC}, "Need the reported findings"),
        ("subtask_done", {}, "Evidence is sufficient"),
        ("finish", {}, ""),
    )
    result, answerer = execute(corpus, embedder, model)
    assert result.stop_reason == "finish"
    assert result.answer.citations
    assert len(answerer.calls) == 1
    assert [step.tool for step in result.steps if step.kind == "tool"] == [
        "plan_research", "search_passages", "subtask_done", "finish",
    ]
    sent = str(model.conversation_requests[-1].messages)
    assert "Can the question be answered from the aggregate context?" in sent
    assert "Evidence is sufficient" in sent


def test_replanning_stops_at_the_outer_limit_and_answers_once(corpus, embedder):
    model = script(
        ("plan_research", {"subtasks": ["Find findings"]}, ""),
        ("search_passages", {"query": TOPIC}, ""),
        ("subtask_done", {}, ""),
        ("plan_research", {"subtasks": ["Compare methods"]}, ""),
        ("search_passages", {"query": "tilapia ponds"}, ""),
        ("subtask_done", {}, ""),
        ("plan_research", {"subtasks": ["Keep searching"]}, ""),
    )
    result, answerer = execute(corpus, embedder, model, max_outer_rounds=2, max_tool_calls=20)
    assert result.stop_reason == "max_outer_rounds"
    assert len(answerer.calls) == 1
    assert "stopped" in result.answer.text
    assert len(model.conversation_requests) == 7


def test_replanning_does_not_reset_run_calls_or_duplicate_cache(corpus, embedder):
    model = script(
        ("plan_research", {"subtasks": ["First"]}, ""),
        ("search_passages", {"query": TOPIC}, ""),
        ("subtask_done", {}, ""),
        ("plan_research", {"subtasks": ["Second"]}, ""),
        ("search_passages", {"query": TOPIC}, ""),
        ("subtask_done", {}, ""),
    )
    result, answerer = execute(corpus, embedder, model, max_tool_calls=5)
    assert result.stop_reason == "max_tool_calls"
    assert len(model.conversation_requests) == 5
    assert [step for step in result.steps if step.tool == "search_passages"][-1].duplicate
    assert len(answerer.calls) == 1


def test_subtask_limit_returns_to_outer_check_without_resetting_run_budget(corpus, embedder):
    model = script(
        ("plan_research", {"subtasks": ["First", "Second"]}, ""),
        ("search_passages", {"query": TOPIC}, ""),
        ("continue_plan", {}, ""),
        ("search_passages", {"query": "tilapia ponds"}, ""),
        ("finish", {}, ""),
    )
    result, answerer = execute(corpus, embedder, model, max_calls_per_subtask=1)
    assert result.stop_reason == "finish"
    assert len(answerer.calls) == 1
    stages = [json.loads(request.messages[-1].content)["stage"]
              for request in model.conversation_requests]
    assert stages == ["outer", "inner", "outer", "inner", "outer"]


@pytest.mark.parametrize("args", [{"subtasks": []}, {"subtasks": [""]}, {"subtasks": ["Read"], "user": 3}])
def test_two_invalid_plans_stop_without_running_any_corpus_tool(corpus, embedder, args):
    result, _ = execute(corpus, embedder, script(
        ("plan_research", args, ""), ("plan_research", args, ""),
    ))
    assert result.stop_reason == "malformed_call"
    assert all(step.tool in ("", "plan_research") for step in result.steps)


def test_oversized_weak_evidence_leaves_all_later_prompts_and_reports_coverage(corpus, embedder, settings):
    from apps.ai.models import DocumentChunk
    settings.AI_RESEARCH_CONTEXT_TOKEN_BUDGET = 4000
    DocumentChunk.objects.filter(record=corpus["pond"]).update(content="WEAK_PASSAGE " * 6000)
    model = script(
        ("plan_research", {"subtasks": ["Read evidence"]}, ""),
        ("search_passages", {"query": TOPIC}, ""),
        ("subtask_done", {}, ""),
        ("finish", {}, ""),
    )
    result, answerer = execute(corpus, embedder, model)
    assert result.stop_reason == "finish"
    assert result.answer.citations
    assert "WEAK_PASSAGE" not in str(model.conversation_requests[2:])
    assert "WEAK_PASSAGE" not in str(answerer.calls)
    assert {source.record_id for source in result.answer.sources} == {corpus["public"].pk}
    assert "lowest-scoring passages" in result.answer.text


def test_synthesis_also_drops_whole_weak_passages_before_its_single_call(corpus, embedder, settings):
    from apps.ai.research.registry import ToolRun
    from apps.ai.research.synthesis import synthesize
    settings.AI_RESEARCH_CONTEXT_TOKEN_BUDGET = 2000
    stack = root(embedder)
    ctx = RunContext.for_request(user=corpus["student"], root=stack, lane="research")
    tool_run = ToolRun.start(ctx, stack)
    for chunk, text, score in [(100, "STRONG_TEXT", 0.9), (101, "WEAK_TEXT " * 3000, 0.1)]:
        tool_run.ledger.add_passage(record_id=corpus["public"].pk, chunk_id=chunk,
            chunk_set_hash="fixture", record_title="Flood forecasting", text=text,
            page=1, context_path=(), score=score)
    answerer = ScriptedLLM(reply="Supported finding [1].")
    answer, handles, codes = synthesize(TOPIC, tool_run, answerer, [])
    assert codes == ()
    assert handles == {1: "E1"}
    assert "WEAK_TEXT" not in str(answerer.calls)
    assert answer.citations
    assert len(answerer.calls) == 1


@pytest.mark.parametrize("citation", ["[N1]", "[planner_note]", "[made_up_source]", "[E1]", "[R1]", "[99]"])
def test_notes_are_visible_to_planner_but_never_citable_or_sent_to_synthesis(corpus, embedder, citation):
    model = script(
        ("plan_research", {"subtasks": ["Find findings"]}, "<think>REASONING_LEAK</think>PLAN_NOTE"),
        ("search_passages", {"query": TOPIC}, "SCRATCHPAD_NOTE"),
        ("subtask_done", {}, ""),
        ("finish", {}, ""),
    )
    answerer = ScriptedLLM(reply=f"A note supports this {citation}.")
    result, _ = execute(corpus, embedder, model, answerer=answerer)
    assert "SCRATCHPAD_NOTE" in str(model.conversation_requests[2].messages)
    assert "REASONING_LEAK" not in str(model.conversation_requests)
    assert "SCRATCHPAD_NOTE" not in str(answerer.calls)
    assert "PLAN_NOTE" not in str(answerer.calls)
    assert result.answer.state == "unavailable"
    assert result.validation_codes == ("unknown_citation",)
    assert result.answer.citations == ()
    assert len(answerer.calls) == 1


def test_newly_gated_evidence_history_notes_and_plan_disappear_before_next_call(corpus, embedder):
    allowed = {corpus["public"].pk, corpus["pond"].pk}
    conversation = Conversation.objects.create(user=corpus["student"])
    turn = Turn.objects.create(conversation=conversation, question="CITED_QUESTION",
                               answer="CITED_ANSWER", state="generated")
    TurnCitation.objects.create(turn=turn, marker=1, record=corpus["public"])
    calls = [
        ("plan_research", {"subtasks": ["Read Flood forecasting"]}, "PLAN_DERIVED_FROM_PAPER"),
        ("search_passages", {"query": TOPIC}, "SEARCH_NOTE"),
        ("subtask_done", {}, "NEWLY_PRIVATE_NOTE"),
        ("finish", {}, ""),
    ]
    def reply(request):
        i = len(model.conversation_requests) - 1
        if i == 2:
            allowed.remove(corpus["public"].pk)
        name, args, note = calls[i]
        return ScriptedToolCallingLLM.calling(name, json.dumps(args), f"call-{i}", text=note)
    model = ScriptedToolCallingLLM(reply)
    result, answerer = execute(corpus, embedder, model, conversation=conversation,
                              stack=root(embedder, permits=lambda r: r.pk in allowed))
    before = str(model.conversation_requests[2].messages)
    after = str(model.conversation_requests[3].messages)
    assert "Flood forecasting" in before
    assert "CITED_ANSWER" in before
    for forbidden in ("Flood forecasting", "CITED_QUESTION", "CITED_ANSWER",
                      "PLAN_DERIVED_FROM_PAPER", "SEARCH_NOTE", "NEWLY_PRIVATE_NOTE"):
        assert forbidden not in after
        assert forbidden not in str(answerer.calls)
    assert {source.record_id for source in result.answer.sources} == {corpus["pond"].pk}


def test_paper_scope_and_history_never_send_another_paper_to_planner(corpus, embedder):
    conversation = Conversation.objects.create(user=corpus["student"], record=corpus["public"])
    widened = Turn.objects.create(conversation=conversation, question="WIDENED_QUESTION",
                                  answer="WIDENED_ANSWER", widened=True, state="generated")
    TurnCitation.objects.create(turn=widened, marker=1, record=corpus["pond"])
    model = script(
        ("plan_research", {"subtasks": ["Read findings"]}, ""),
        ("search_passages", {"query": TOPIC}, ""),
        ("subtask_done", {}, ""), ("finish", {}, ""),
    )
    result, _ = execute(corpus, embedder, model, conversation=conversation)
    sent = str(model.conversation_requests)
    assert "WIDENED_ANSWER" not in sent
    assert "Tilapia ponds" not in sent
    assert "Secret flood draft" not in sent
    assert {source.record_id for source in result.answer.sources} == {corpus["public"].pk}
    body = json.loads(model.conversation_requests[2].messages[1].content)
    assert body["aggregate_context"]["records"][0]["abstract"] == corpus["public"].abstract
    assert body["aggregate_context"]["passages"][0]["text"] == result.answer.sources[0].content


def test_a_visible_but_undisclosable_prior_exchange_is_omitted(corpus, embedder):
    conversation = Conversation.objects.create(user=corpus["student"])
    turn = Turn.objects.create(conversation=conversation, question="GATED_QUESTION",
                               answer="GATED_ANSWER", state="generated")
    TurnCitation.objects.create(turn=turn, marker=1, record=corpus["public"])
    Turn.objects.create(conversation=conversation, question="FAILED_QUESTION",
                        answer="FAILED_ANSWER", state="unavailable")
    model = script(("finish", {}, ""))
    execute(corpus, embedder, model, conversation=conversation,
            stack=root(embedder, permits=lambda r: r.pk != corpus["public"].pk))
    sent = str(model.conversation_requests)
    assert "GATED_QUESTION" not in sent
    assert "GATED_ANSWER" not in sent
    assert "FAILED_QUESTION" not in sent


def test_replan_cannot_reset_reported_prompt_token_spend(corpus, embedder):
    calls = [
        ("plan_research", {"subtasks": ["First"]}),
        ("search_passages", {"query": TOPIC}),
        ("subtask_done", {}),
        ("plan_research", {"subtasks": ["Second"]}),
    ]
    model = ScriptedToolCallingLLM([
        ScriptedToolCallingLLM.calling(name, json.dumps(args), f"call-{i}", input_tokens=3000)
        for i, (name, args) in enumerate(calls)
    ])
    result, answerer = execute(corpus, embedder, model, max_prompt_tokens=11000)
    assert result.stop_reason == "max_prompt_tokens"
    assert len(model.conversation_requests) == 4
    assert result.answer.sources
    assert answerer.calls == []


def test_a_passage_count_cap_also_reports_reduced_coverage(corpus, embedder):
    model = script(
        ("plan_research", {"subtasks": ["Read findings"]}, ""),
        ("search_passages", {"query": TOPIC}, ""),
        ("subtask_done", {}, ""), ("finish", {}, ""),
    )
    result, _ = execute(corpus, embedder, model, max_ledger_passages=1)
    assert len(result.answer.sources) == 1
    assert "lowest-scoring passages" in result.answer.text


def test_visibility_loss_removes_old_counts_notes_and_plan_from_later_requests(corpus, embedder):
    from apps.records.models import Record
    from core.enums import PipelineStatus

    calls = [
        ("plan_research", {"subtasks": ["Read papers", "Compare the counted papers"]}, ""),
        ("search_passages", {"query": TOPIC}, ""),
        ("count_records", {}, "COUNT_NOTE"),
        ("subtask_done", {}, ""),
        ("finish", {}, ""),
    ]

    def reply(request):
        i = len(model.conversation_requests) - 1
        if i == 3:
            Record.objects.filter(pk=corpus["pond"].pk).update(pipeline_status=PipelineStatus.DRAFT)
        name, args, note = calls[i]
        return ScriptedToolCallingLLM.calling(name, json.dumps(args), f"call-{i}", text=note)

    model = ScriptedToolCallingLLM(reply)
    result, answerer = execute(corpus, embedder, model)
    before = json.loads(model.conversation_requests[3].messages[1].content)
    assert any(row.get("detail", {}).get("total") == 2 for row in before["computed_results"])
    after = str(model.conversation_requests[4].messages)
    assert '"total": 2' not in after
    assert "COUNT_NOTE" not in after
    assert "Compare the counted papers" not in after
    assert '"total": 2' not in str(answerer.calls)
    assert {source.record_id for source in result.answer.sources} == {corpus["public"].pk}


@pytest.mark.parametrize("name,args", [
    ("count_records", {}), ("corpus_facets", {"dimension": "classification"}),
])
def test_aggregate_cache_recomputes_after_visible_membership_changes(corpus, embedder, name, args):
    from apps.ai.research.registry import ToolRun, research_tools
    from apps.records.models import Record
    from core.enums import PipelineStatus

    stack = root(embedder)
    run = ToolRun.start(RunContext.for_request(user=corpus["student"], root=stack, lane="research"), stack)
    registry = research_tools()
    first = registry.call(run, name, args)
    assert registry.call(run, name, args).duplicate
    Record.objects.filter(pk=corpus["pond"].pk).update(pipeline_status=PipelineStatus.DRAFT)
    second = registry.call(run, name, args)
    assert not second.duplicate
    field = "total" if name == "count_records" else "sample_size"
    assert first.detail[field] == 2
    assert second.detail[field] == 1
    assert "visible_record_ids" not in second.planner_message()
