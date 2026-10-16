"""IR-597: readable Records do not authorize reuse of stale historical findings."""

import json

import pytest
from django.utils import timezone

from apps.ai.answers.citations import Citation, GroundedAnswer
from apps.ai.composition import use_composition_root
from apps.ai.conversations import record_turn, turn_for_reader
from apps.ai.history import readable_turns
from apps.ai.memory import ConversationMemory
from apps.ai.models import ChunkSet, TurnCitation, TurnEmbedding
from apps.ai.providers.fakes import ScriptedLLM, ScriptedToolCallingLLM

from .test_controller_http import compose, controller_root
from .test_routed_chat_http import answer

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

STALE_FINDING = "Historical obsolete finding about flood prediction."
STALE_SUMMARY = "The historical finding depends on the paper."


@pytest.fixture
def historical(flood_scene, settings):
    # The injected writer is reserved for ANSWER. The default root would
    # also inject it into RESOLVE and trigger a mid-answer mutation early.
    settings.AI_QUESTION_RESOLUTION_ENABLED = False
    scene = flood_scene
    chunk = scene["flood"].document_chunks.get()
    citation = Citation(
        marker=1, chunk_id=chunk.pk, record_id=scene["flood"].pk,
        record_title=scene["flood"].title, source_page=chunk.source_page,
        text=chunk.content, context_path=tuple(chunk.context_path),
    )
    turn = record_turn(
        scene["conversation"], "What did the earlier paper find?",
        GroundedAnswer(
            text=STALE_FINDING, citations=(citation,),
            reasoning_summary=STALE_SUMMARY, reasoning_summary_source="controller-test",
        ),
    )
    return {**scene, "chunk": chunk, "turn": turn}


def _replace_source(scene):
    old = scene["chunk"].chunk_set
    ChunkSet.objects.filter(pk=old.pk).update(is_active=False)
    return ChunkSet.objects.create(
        record=scene["flood"], extraction_hash="replacement", strategy_id="test",
        options={}, content_hash="replacement", is_active=True,
    )


@pytest.mark.parametrize("change", ["replace", "tombstone", "delete", "missing"])
def test_stale_chunk_history_is_rejected_even_while_the_record_remains_readable(historical, change):
    scene = historical
    assert readable_turns([scene["turn"]], scene["reader"]) == [scene["turn"]]
    if change == "replace":
        _replace_source(scene)
    elif change == "tombstone":
        type(scene["chunk"]).objects.filter(pk=scene["chunk"].pk).update(deleted_at=timezone.now())
    elif change == "delete":
        scene["chunk"].delete()
    else:
        TurnCitation.objects.filter(turn=scene["turn"]).update(chunk=None)
    assert readable_turns([scene["turn"]], scene["reader"]) == []


@pytest.mark.parametrize("endpoint", ["ai-ask", "ai-ask-stream"])
def test_reingested_history_reaches_neither_plan_nor_answer(
    historical, monkeypatch, embedder, endpoint,
):
    scene = historical
    _replace_source(scene)
    planner = ScriptedToolCallingLLM([compose(basis="general")])
    writer = ScriptedLLM(reply="A general explanation of model uncertainty.")
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    with use_composition_root(root):
        body = answer(scene["client"], endpoint, "Explain uncertainty generally.",
                      conversation_id=scene["conversation"].pk)
    assert body["answer"] == writer._reply
    assert planner.conversation_requests and writer.calls
    assert STALE_FINDING not in repr(planner.conversation_requests)
    assert STALE_FINDING not in repr(writer.calls)
    assert STALE_SUMMARY not in repr(planner.conversation_requests)
    assert STALE_SUMMARY not in repr(writer.calls)


def test_reingestion_during_answer_withholds_text_and_summary(historical, monkeypatch, embedder):
    scene = historical

    class ReingestingWriter(ScriptedLLM):
        def generate(self, system, user):
            assert STALE_FINDING in user, "history was current when generation started"
            result = super().generate(system, user)
            _replace_source(scene)
            return result

    planner = ScriptedToolCallingLLM([compose(basis="general")])
    writer = ReingestingWriter(reply=json.dumps({
        "answer": "A derived explanation of the prior finding.",
        "summary": "This explanation uses the prior finding.",
    }))
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    with use_composition_root(root):
        body = answer(scene["client"], "ai-ask", "Explain the earlier answer more simply.",
                      conversation_id=scene["conversation"].pk)
    assert body["answer"] is None
    assert "reasoning_summary" not in body
    new = scene["conversation"].turns.latest("id")
    assert new.pk != scene["turn"].pk and new.state == "unavailable"
    assert not new.reasoning_summary


def test_recall_excludes_stale_history_before_ranking(historical, embedder, space, settings):
    scene = historical
    settings.AI_MEMORY_RECALL_MAX_DISTANCE = 0
    vector = embedder.embed_query("flood prediction")
    TurnEmbedding.objects.create(turn=scene["turn"], space=space, embedding=vector)
    memory = ConversationMemory()
    assert memory.recall(scene["conversation"], vector, space.pk) == [scene["turn"]]
    _replace_source(scene)
    assert memory.recall(scene["conversation"], vector, space.pk) == []


def test_reopened_transcript_keeps_historical_pointer_without_stale_quote_or_summary(historical):
    scene = historical
    before = turn_for_reader(scene["turn"], scene["reader"], public=True)
    assert before["reasoning_summary"] == STALE_SUMMARY
    _replace_source(scene)
    body = turn_for_reader(scene["turn"], scene["reader"], public=True)
    assert body["answer"] == STALE_FINDING, "stored history remains readable"
    assert body["citations"][0]["record_id"] == scene["flood"].pk
    assert "text" not in body["citations"][0]
    assert "reasoning_summary" not in body


def test_reingestion_during_plan_discards_derived_tool_call_and_resolved_request(
    historical, monkeypatch, embedder,
):
    from dataclasses import replace

    from apps.ai.research import tools
    from apps.ai.resolution import QuestionResolver

    scene = historical
    stale_query = f"Find related papers for {STALE_FINDING}"
    resolved_request = f"Explain the implications of {STALE_FINDING}"
    executed = []

    def forbidden_search(run, arguments):
        executed.append(arguments)
        pytest.fail("A tool call derived from superseded history must not execute")

    monkeypatch.setattr(tools, "GENERAL_TOOLS", tuple(
        replace(tool, execute=forbidden_search) if tool.name == "search_research" else tool
        for tool in tools.GENERAL_TOOLS
    ))

    def plan(request):
        if len(planner.conversation_requests) == 1:
            payload = json.loads(request.user)
            assert payload["recent_history"][0]["answer"] == STALE_FINDING
            assert payload["request_in_context"] == resolved_request
            _replace_source(scene)
            return ScriptedToolCallingLLM.calling(
                "search_research", json.dumps({"query": stale_query, "target": "passages"}),
                "stale-search",
            )
        assert len(planner.conversation_requests) == 2, "discarded plans still use bounded rounds"
        payload = json.loads(request.user)
        assert payload["recent_history"] == []
        assert "request_in_context" not in payload
        assert STALE_FINDING not in repr(planner.conversation_requests[-1].messages)
        assert "stale-search" not in repr(planner.conversation_requests[-1].messages)
        return compose(basis="general")

    planner = ScriptedToolCallingLLM(plan)
    writer = ScriptedLLM(reply="A general explanation of uncertainty.")
    resolver_writer = ScriptedLLM(reply=resolved_request)
    resolver = QuestionResolver(llm=resolver_writer)
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    # Deliberately resolve from valid history before the PLAN callback replaces
    # that source. ANSWER and RESOLVE use distinct fakes in this race test.
    monkeypatch.setattr(root, "resolver", lambda: resolver)
    with use_composition_root(root):
        body = answer(scene["client"], "ai-ask", "Explain the earlier answer.",
                      conversation_id=scene["conversation"].pk)

    assert resolver_writer.calls and STALE_FINDING in resolver_writer.calls[0][1]
    assert executed == []
    assert len(planner.conversation_requests) == 2
    assert body["answer"] == writer._reply
    assert writer.calls and STALE_FINDING not in repr(writer.calls)
    assert stale_query not in repr(writer.calls)
    assert resolved_request not in repr(writer.calls)


def test_reingestion_during_resolve_discards_derived_request_before_first_plan(
    historical, monkeypatch, embedder,
):
    from apps.ai.resolution import QuestionResolver

    scene = historical
    question = "Explain the earlier answer in general terms."
    resolved_request = f"Explain the implications of {STALE_FINDING}"

    class ReingestingResolver(ScriptedLLM):
        def generate(self, system, user):
            assert STALE_FINDING in user, "the resolver starts with current historical evidence"
            result = super().generate(system, user)
            _replace_source(scene)
            return result

    def plan(request):
        payload = json.loads(request.user)
        assert payload["request"] == question, "the reader's original request remains intact"
        assert payload["recent_history"] == []
        assert "request_in_context" not in payload
        assert STALE_FINDING not in repr(planner.conversation_requests[-1].messages)
        return compose(basis="general")

    planner = ScriptedToolCallingLLM(plan)
    writer = ScriptedLLM(reply="A general explanation of uncertainty.")
    resolver_writer = ReingestingResolver(reply=resolved_request)
    resolver = QuestionResolver(llm=resolver_writer)
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    monkeypatch.setattr(root, "resolver", lambda: resolver)
    with use_composition_root(root):
        body = answer(scene["client"], "ai-ask", question,
                      conversation_id=scene["conversation"].pk)

    assert len(resolver_writer.calls) == 1
    assert len(planner.conversation_requests) == 1
    assert body["answer"] == writer._reply
    assert writer.calls and question in writer.calls[0][1]
    assert STALE_FINDING not in repr(writer.calls)
    assert resolved_request not in repr(writer.calls)
