"""IR-593: the bounded conversational controller behind the chat boundary.

Driven through `/ask/` and `/ask/stream/` with fake providers only; the
controller is the engine a root pins for new runs (ADR-042).
"""
import json

import pytest
from django.urls import reverse

from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.controller.budget import FAKE_TEST_PROFILE
from apps.ai.controller.versions import CONTROLLER_ENGINE, LEGACY_ENGINE, pin
from apps.ai.inference import InferenceTask
from apps.ai.models import AskRun, Conversation, Turn
from apps.ai.providers.fakes import ScriptedLLM, ScriptedReranker, ScriptedToolCallingLLM
from apps.ai.providers.tool_calling import ToolCompletion

from apps.ai.conversation_state import snapshot
from apps.ai.research.tests.conftest import fresh_vector_indexes
from apps.ai.tasks import answer_queued_question

from .corpus import FLOOD_TEXT, POND_TEXT, make_record, make_user
from .test_routed_chat_http import answer

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

GENERAL = {"resolve_papers", "search_research", "read_papers", "aggregate_records",
           "extract_evidence"}
CEREMONY = {"plan_research", "continue_plan", "subtask_done", "finish"}


@pytest.fixture
def budget(settings):
    for name, value in FAKE_TEST_PROFILE.items():
        setattr(settings, name, value)
    return FAKE_TEST_PROFILE


def controller_root(monkeypatch, *, embedder=None, planner, reply="Composed answer.", writer=None):
    root = CompositionRoot(
        embedder=embedder, reranker=ScriptedReranker(), llm=writer or ScriptedLLM(reply=reply),
        permits=lambda record: True, engine=CONTROLLER_ENGINE,
    )
    real = root.llm_for
    monkeypatch.setattr(root, "llm_for", lambda task, **kw: (
        planner if task == InferenceTask.PLAN else real(task, **kw)))
    return root


def compose(**fields):
    return ScriptedToolCallingLLM.answering(json.dumps({"next": "compose", **fields}))


@pytest.mark.parametrize("endpoint", ["ai-ask", "ai-ask-stream"])
def test_a_request_needing_no_tool_is_composed_by_the_answer_model_not_the_planner(
    endpoint, budget, monkeypatch, client_for,
):
    reader = make_user("direct@cit.edu")
    conversation = Conversation.objects.create(user=reader)
    planner = ScriptedToolCallingLLM([ScriptedToolCallingLLM.answering(
        json.dumps({"next": "compose", "basis": "general"}) + " PLANNER NOTE")])
    root = controller_root(monkeypatch, planner=planner, reply="A table of right and wrong guesses.")
    question = "Explain a confusion matrix in simple words."
    with use_composition_root(root):
        body = answer(client_for(reader), endpoint, question, conversation_id=conversation.pk)

    assert body["answer"] == "A table of right and wrong guesses."
    assert "PLANNER" not in json.dumps(body)
    assert "routing" not in body and "research" not in body
    offered = {tool.name for tool in planner.conversation_requests[0].tools}
    assert offered == GENERAL and not offered & CEREMONY
    sent = " ".join(m.content for m in planner.conversation_requests[0].messages
                    if hasattr(m, "content") and isinstance(m.content, str))
    assert question in sent
    turn = Turn.objects.get(conversation=conversation)
    assert turn.answer == "A table of right and wrong guesses." and not turn.routing and not turn.research


def call(name, arguments, call_id):
    return ScriptedToolCallingLLM.calling(name, json.dumps(arguments), call_id)


def test_discovery_then_a_simpler_rewording_keeps_the_papers_shown(
    budget, monkeypatch, embedder, space, client_for,
):
    """A01 and A08: search, compose from cited passages; then reword with no tool."""
    fresh_vector_indexes()
    reader = make_user("discover@cit.edu")
    flood = make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    make_record(title="Tilapia ponds", text=POND_TEXT, embedder=embedder, space=space)
    conversation = Conversation.objects.create(user=reader)
    planner = ScriptedToolCallingLLM([
        call("search_research", {"query": "flood prediction", "target": "passages"}, "c1"),
        compose(basis="evidence", topic="flood prediction"),
        compose(basis="general"),
    ])
    writer = ScriptedLLM(reply="Flood Prediction forecasts river levels [1].")
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    client = client_for(reader)
    with use_composition_root(root):
        first = answer(client, "ai-ask-stream", "Suggest papers on flood prediction.",
                       conversation_id=conversation.pk)
        writer._reply = "In short: it predicts floods."
        second = answer(client, "ai-ask-stream", "Say that more simply.",
                        conversation_id=conversation.pk)

    assert first["answer"] == "Flood Prediction forecasts river levels [1]."
    assert [c["record_id"] for c in first["citations"]] == [flood.pk]
    results = planner.conversation_requests[1].messages
    assert any(getattr(m, "tool_call_id", None) == "c1" for m in results)
    assert "Suggest papers on flood prediction." in writer.calls[0][1]
    assert FLOOD_TEXT.split(".")[0] in writer.calls[0][1]

    assert second["answer"] == "In short: it predicts floods."
    assert "Flood Prediction forecasts river levels" in writer.calls[-1][1]
    state = snapshot(conversation, reader).state
    assert state.presented == (flood.pk,) and state.topic == "flood prediction"


def asked_flood(client, conversation, endpoint="ai-ask-stream"):
    return answer(client, endpoint, "What do papers say about flood prediction?",
                  conversation_id=conversation.pk)


@pytest.fixture
def flood_scene(budget, embedder, space, client_for):
    fresh_vector_indexes()
    reader = make_user("scene@cit.edu")
    flood = make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    pond = make_record(title="Tilapia ponds", text=POND_TEXT, embedder=embedder, space=space)
    return {"reader": reader, "flood": flood, "pond": pond, "client": client_for(reader),
            "conversation": Conversation.objects.create(user=reader)}


def test_a_ceremony_tool_and_a_malformed_call_are_rejected_and_stop_the_run(
    flood_scene, monkeypatch, embedder,
):
    planner = ScriptedToolCallingLLM([
        call("plan_research", {"subtasks": ["Find findings"]}, "c1"),
        call("search_research", {"query": "flood", "target": "papers", "user": 1}, "c2"),
    ])
    writer = ScriptedLLM(reply="never written")
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    with use_composition_root(root):
        body = asked_flood(flood_scene["client"], flood_scene["conversation"])

    assert len(planner.conversation_requests) == 2
    replies = [m.content for m in planner.conversation_requests[1].messages
               if getattr(m, "tool_call_id", None) == "c1"]
    assert json.loads(replies[0])["limitations"] == ["unknown_tool"]
    assert body["answer"] is None and body["mode"] == "no_results"
    assert writer.calls == []


def test_a_repeated_call_that_adds_nothing_stops_before_the_round_limit(
    flood_scene, monkeypatch, embedder,
):
    ids = iter(range(100))
    planner = ScriptedToolCallingLLM(lambda request: call(
        "search_research", {"query": "flood prediction", "target": "passages"}, f"c{next(ids)}"))
    writer = ScriptedLLM(reply="Flood findings [1].")
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    with use_composition_root(root):
        body = asked_flood(flood_scene["client"], flood_scene["conversation"])

    assert len(planner.conversation_requests) == 2
    assert body["answer"] == "Flood findings [1]."
    assert "stopped_no_progress" in writer.calls[0][1]


def test_searches_that_find_nothing_new_stop_as_no_progress(flood_scene, monkeypatch, embedder):
    ids = iter(range(100))

    def varied(request):
        n = next(ids)
        return call("search_research", {"query": f"flood topic {n}", "target": "passages"}, f"c{n}")

    planner = ScriptedToolCallingLLM(varied)
    writer = ScriptedLLM(reply="Flood findings [1].")
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    with use_composition_root(root):
        asked_flood(flood_scene["client"], flood_scene["conversation"])

    assert len(planner.conversation_requests) == 3
    assert "stopped_no_progress" in writer.calls[0][1]


def test_the_round_limit_stops_research_and_still_answers(
    flood_scene, settings, monkeypatch, embedder,
):
    settings.AI_CONTROLLER_MAX_ROUNDS = 2
    planner = ScriptedToolCallingLLM([
        call("search_research", {"query": "flood prediction", "target": "papers"}, "c1"),
        call("search_research", {"query": "flood prediction", "target": "passages"}, "c2"),
    ])
    writer = ScriptedLLM(reply="Flood findings [1].")
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    with use_composition_root(root):
        body = asked_flood(flood_scene["client"], flood_scene["conversation"])

    assert len(planner.conversation_requests) == 2
    assert body["answer"] == "Flood findings [1]."
    assert "stopped_max_outer_rounds" in writer.calls[0][1]


def test_the_tool_call_limit_stops_a_round_and_still_answers(flood_scene, monkeypatch, embedder):
    many = tuple(
        call("search_research", {"query": f"flood {n}", "target": "passages"}, f"m{n}").tool_calls[0]
        for n in range(FAKE_TEST_PROFILE["AI_CONTROLLER_MAX_TOOL_CALLS"] + 1)
    )
    planner = ScriptedToolCallingLLM([ToolCompletion(tool_calls=many)])
    writer = ScriptedLLM(reply="Flood findings [1].")
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    with use_composition_root(root):
        body = asked_flood(flood_scene["client"], flood_scene["conversation"])

    assert len(planner.conversation_requests) == 1
    assert body["answer"] == "Flood findings [1]."
    assert "stopped_max_tool_calls" in writer.calls[0][1]


def test_no_research_starts_when_the_answer_reserve_cannot_be_met(
    flood_scene, settings, monkeypatch, embedder,
):
    settings.AI_CONTROLLER_ANSWER_RESERVE_TOKENS = settings.AI_RESEARCH_MAX_PROMPT_TOKENS
    planner = ScriptedToolCallingLLM([])
    root = controller_root(monkeypatch, embedder=embedder, planner=planner)
    with use_composition_root(root):
        body = asked_flood(flood_scene["client"], flood_scene["conversation"])
    assert planner.conversation_requests == []
    assert body["answer"] is None and body["mode"] == "no_results"


def test_an_unset_limit_refuses_without_calling_any_model(flood_scene, settings, monkeypatch, embedder):
    settings.AI_CONTROLLER_MAX_TOOL_CALLS = None
    planner = ScriptedToolCallingLLM([])
    writer = ScriptedLLM(reply="never written")
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    with use_composition_root(root):
        body = asked_flood(flood_scene["client"], flood_scene["conversation"])
    assert planner.conversation_requests == [] and writer.calls == []
    assert body["mode"] == "unavailable"


def test_paper_chat_searches_only_its_paper(flood_scene, monkeypatch, embedder):
    reader, flood = flood_scene["reader"], flood_scene["flood"]
    conversation = Conversation.objects.create(user=reader, record=flood)
    planner = ScriptedToolCallingLLM([
        call("search_research", {"query": "tilapia ponds brackish water", "target": "passages"}, "c1"),
        compose(basis="evidence"),
    ])
    writer = ScriptedLLM(reply="This paper is about floods [1].")
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    with use_composition_root(root):
        body = answer(flood_scene["client"], "ai-ask-stream", "Does it discuss tilapia ponds?",
                      conversation_id=conversation.pk)
    sent = " ".join(repr(m) for r in planner.conversation_requests for m in r.messages)
    assert POND_TEXT not in sent and POND_TEXT not in writer.calls[0][1]
    assert {c["record_id"] for c in body["citations"]} <= {flood.pk}


def test_a_failed_tool_and_a_planner_outage_keep_the_supported_parts(
    flood_scene, monkeypatch, embedder,
):
    """A09: a tool fails, another permitted tool is tried, then PLAN goes down."""
    from dataclasses import replace

    from apps.ai.providers.openai_compatible import LLMUnavailable
    from apps.ai.research import tools

    def broken(run, args):
        raise RuntimeError("retrieval down")

    monkeypatch.setattr(tools, "GENERAL_TOOLS", tuple(
        replace(tool, execute=broken) if tool.name == "search_research" else tool
        for tool in tools.GENERAL_TOOLS))
    planner = ScriptedToolCallingLLM([
        call("search_research", {"query": "flood", "target": "passages"}, "c1"),
        call("aggregate_records", {"operation": "count"}, "c2"),
        LLMUnavailable("planner down"),
    ])
    writer = ScriptedLLM(reply="Two papers are visible to you.")
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    with use_composition_root(root):
        body = asked_flood(flood_scene["client"], flood_scene["conversation"])

    assert body["answer"] == "Two papers are visible to you."
    prompt = writer.calls[0][1]
    assert "tool_unavailable" in prompt and "stopped_planner_unavailable" in prompt
    assert "metadata" in prompt


def test_a_clarification_is_composed_and_kept_pending(flood_scene, monkeypatch, embedder):
    planner = ScriptedToolCallingLLM([ScriptedToolCallingLLM.answering(
        json.dumps({"next": "clarify", "about": "which of two similar titles"}))])
    writer = ScriptedLLM(reply="Do you mean the 2021 or the 2023 study?")
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    reader, conversation = flood_scene["reader"], flood_scene["conversation"]
    with use_composition_root(root):
        body = asked_flood(flood_scene["client"], conversation)
    assert body["answer"] == "Do you mean the 2021 or the 2023 study?"
    assert "which of two similar titles" in writer.calls[0][1]
    pending = snapshot(conversation, reader).state.pending_clarification
    assert pending["question"] == "Do you mean the 2021 or the 2023 study?"


@pytest.fixture
def queued(settings, monkeypatch):
    settings.AI_DURABLE_ASK = True
    settings.AI_DURABLE_ASK_POLL_SECONDS = 0
    sent = []
    monkeypatch.setattr(answer_queued_question, "apply_async",
                        lambda args, **limits: sent.append(args[0]))
    return sent


def submit(client, conversation, capture):
    with capture(execute=True):
        response = client.post(reverse("ai-ask-stream"), {
            "question": "What do papers say about flood prediction?",
            "conversation_id": conversation.pk}, format="json")
    assert response.status_code == 200
    next(iter(response.streaming_content))
    response._iterator.close()
    return AskRun.objects.get(conversation=conversation)


def test_a_queued_run_keeps_the_controller_it_was_pinned_to_after_a_rollback(
    flood_scene, queued, monkeypatch, embedder, django_capture_on_commit_callbacks,
):
    planner = ScriptedToolCallingLLM([
        call("search_research", {"query": "flood prediction", "target": "passages"}, "c1"),
        compose(basis="evidence"),
    ])
    writer = ScriptedLLM(reply="Flood findings [1].")
    controller = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    with use_composition_root(controller):
        run = submit(flood_scene["client"], flood_scene["conversation"],
                     django_capture_on_commit_callbacks)
    assert run.request["pin"] == pin(CONTROLLER_ENGINE)

    # Rolled back: new runs are legacy, this one still runs its pinned engine.
    legacy = CompositionRoot(embedder=embedder, reranker=ScriptedReranker(),
                             llm=writer, permits=lambda record: True)
    monkeypatch.setattr(legacy, "llm_for", lambda task, **kw: (
        planner if task == InferenceTask.PLAN else writer))
    assert legacy.engine == LEGACY_ENGINE
    with use_composition_root(legacy):
        answer_queued_question(str(run.pk))

    run.refresh_from_db()
    assert run.state == "succeeded" and run.turn.answer == "Flood findings [1]."
    assert len(planner.conversation_requests) == 2


def test_a_run_pinned_to_the_legacy_engine_never_reaches_the_controller(
    flood_scene, queued, monkeypatch, embedder, django_capture_on_commit_callbacks,
):
    writer = ScriptedLLM(reply="Legacy answer [1].")
    legacy = CompositionRoot(embedder=embedder, reranker=ScriptedReranker(), llm=writer,
                             permits=lambda record: True)
    with use_composition_root(legacy):
        run = submit(flood_scene["client"], flood_scene["conversation"],
                     django_capture_on_commit_callbacks)
    assert run.request["pin"] == {"engine": LEGACY_ENGINE}

    planner = ScriptedToolCallingLLM([])
    controller = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    with use_composition_root(controller):
        answer_queued_question(str(run.pk))
    run.refresh_from_db()
    assert run.state == "succeeded" and run.turn.answer == "Legacy answer [1]."
    assert planner.conversation_requests == []


def test_a_run_pinned_to_an_engine_this_code_lacks_ends_without_a_turn(
    flood_scene, queued, monkeypatch, embedder, django_capture_on_commit_callbacks,
):
    writer = ScriptedLLM(reply="never written")
    root = controller_root(monkeypatch, embedder=embedder, planner=ScriptedToolCallingLLM([]),
                           writer=writer)
    with use_composition_root(root):
        run = submit(flood_scene["client"], flood_scene["conversation"],
                     django_capture_on_commit_callbacks)
        AskRun.objects.filter(pk=run.pk).update(request={**run.request, "pin": {"engine": "controller-v9"}})
        answer_queued_question(str(run.pk))
    run.refresh_from_db()
    assert run.state == "failed" and run.turn is None and writer.calls == []


def test_a_follow_up_compares_the_papers_shown_by_their_displayed_order(
    flood_scene, monkeypatch, embedder,
):
    """A01/A02: discovery shows two papers; "compare the first and second"
    resolves them from the committed order, reads both and composes."""
    reader, conversation = flood_scene["reader"], flood_scene["conversation"]
    replies = iter([
        call("search_research", {"query": "flood prediction", "target": "passages"}, "a1"),
        call("search_research", {"query": "tilapia ponds brackish", "target": "passages"}, "a2"),
        compose(basis="evidence"),
        call("resolve_papers", {"ordinals": [1, 2]}, "b1"),
    ])

    def script(request):
        step = next(replies, None)
        if step is not None:
            return step
        results = json.loads(request.user)["results"]
        if len(results) == 1:
            handles = [item["record"] for item in results[0]["items"]]
            return call("read_papers", {"records": handles, "view": "sections"}, "b2")
        return compose(basis="evidence")

    planner = ScriptedToolCallingLLM(script)
    writer = ScriptedLLM(reply="Two studies [1] [2].")
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    with use_composition_root(root):
        asked_flood(flood_scene["client"], conversation)
        shown = snapshot(conversation, reader).state.presented
        assert set(shown) == {flood_scene["flood"].pk, flood_scene["pond"].pk}
        writer._reply = "They differ in method [1] [2]."
        body = answer(flood_scene["client"], "ai-ask-stream", "Compare the first and second.",
                      conversation_id=conversation.pk)

    assert body["answer"] == "They differ in method [1] [2]."
    assert [c["record_id"] for c in body["citations"]] == list(shown)
    prompt = writer.calls[-1][1]
    assert POND_TEXT in prompt and FLOOD_TEXT.split(".")[0] in prompt


def test_a_paper_revoked_mid_run_reaches_neither_the_planner_nor_the_answer(
    flood_scene, monkeypatch, embedder,
):
    from dataclasses import replace

    from apps.ai.research import tools
    from core.enums import PipelineStatus

    flood = flood_scene["flood"]

    def search_then_revoke(run, args):
        result = tools.SEARCH_RESEARCH.execute(run, args)
        flood.pipeline_status = PipelineStatus.DRAFT
        flood.save()
        return result

    monkeypatch.setattr(tools, "GENERAL_TOOLS", tuple(
        replace(tool, execute=search_then_revoke) if tool.name == "search_research" else tool
        for tool in tools.GENERAL_TOOLS))
    planner = ScriptedToolCallingLLM([
        call("search_research", {"query": "flood prediction", "target": "passages"}, "c1"),
        compose(basis="evidence"),
    ])
    writer = ScriptedLLM(reply="Ponds only [1].")
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    with use_composition_root(root):
        body = asked_flood(flood_scene["client"], flood_scene["conversation"])

    hidden = FLOOD_TEXT.split(".")[0]
    assert flood.pk not in {c["record_id"] for c in body["citations"]}
    assert all(hidden not in user for _, user in writer.calls)
    assert hidden not in repr(planner.conversation_requests[-1].messages)


def test_a_count_over_a_population_that_changed_mid_run_is_not_composed(
    flood_scene, monkeypatch, embedder,
):
    from dataclasses import replace

    from apps.ai.research import tools
    from core.enums import PipelineStatus

    flood = flood_scene["flood"]

    def count_then_revoke(run, args):
        result = tools.AGGREGATE_RECORDS.execute(run, args)
        flood.pipeline_status = PipelineStatus.DRAFT
        flood.save()
        return result

    monkeypatch.setattr(tools, "GENERAL_TOOLS", tuple(
        replace(tool, execute=count_then_revoke) if tool.name == "aggregate_records" else tool
        for tool in tools.GENERAL_TOOLS))
    planner = ScriptedToolCallingLLM([
        call("aggregate_records", {"operation": "count"}, "c1"),
        compose(basis="evidence"),
    ])
    writer = ScriptedLLM(reply="never written")
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    with use_composition_root(root):
        body = asked_flood(flood_scene["client"], flood_scene["conversation"])

    assert body["answer"] is None and body["mode"] == "no_results"
    assert all("metadata" not in user for _, user in writer.calls)
