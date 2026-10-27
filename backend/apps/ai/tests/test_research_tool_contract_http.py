"""IR-590: the tool contract at the HTTP boundary, captured at the fake vendor.

The legacy research lane is the only HTTP caller of the registry until the
general-tools controller lands, so this pins that its wrappers still reject
malformed calls and other runs' handles and leak no hidden record.
"""
import json

import pytest
from django.urls import reverse

from apps.ai.composition import use_composition_root
from apps.ai.inference import InferenceTask
from apps.ai.models import Conversation
from apps.ai.providers.fakes import ScriptedToolCallingLLM
from apps.ai.research.tests.conftest import fresh_vector_indexes
from core.enums import PipelineStatus

from .corpus import FLOOD_QUESTION, FLOOD_TEXT, make_record, make_user, root_with
from .test_research_rollout_http import events_of
from .test_routed_chat_http import route

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

HIDDEN = "Secret flood draft"


def scripted(monkeypatch, root, calls):
    pending = [ScriptedToolCallingLLM.calling(name, json.dumps(args), f"call-{i}")
               for i, (name, args) in enumerate(calls)]
    finish = ScriptedToolCallingLLM.calling("finish", "{}", "call-finish")
    planner = ScriptedToolCallingLLM(lambda request: pending.pop(0) if pending else finish)
    real = root.llm_for
    monkeypatch.setattr(root, "llm_for",
                        lambda task: planner if task == InferenceTask.PLAN else real(task))
    return planner


def sent(planner):
    parts = [f"{r.system}\n{r.user}" for r in planner.tool_requests]
    parts += [repr(m) for r in planner.conversation_requests for m in r.messages]
    return "\n".join(parts)


def test_malformed_and_foreign_calls_are_rejected_and_nothing_hidden_reaches_the_vendor(
    settings, monkeypatch, embedder, space, client_for,
):
    fresh_vector_indexes()
    settings.AI_RESEARCH_LANE = "on"
    settings.AI_RESEARCH_MAX_TOOL_CALLS = 10
    route(monkeypatch, "research")
    reader = make_user("contract@cit.edu")
    make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    make_record(title=HIDDEN, text=FLOOD_TEXT, embedder=embedder, space=space,
                status=PipelineStatus.DRAFT, owner=make_user("owner@cit.edu"))
    conversation = Conversation.objects.create(user=reader)
    root = root_with(embedder=embedder)
    planner = scripted(monkeypatch, root, [
        ("plan_research", {"subtasks": ["Find findings"]}),
        ("find_records", {"topic": "the flood draft that is secret"}),
        ("search_passages", {"query": "flood prediction"}),
        ("search_passages", {"query": "flood", "user": 1}),
        ("read_record_sections", {"record": "R1-ffffff"}),
        ("subtask_done", {}),
    ])
    with use_composition_root(root):
        response = client_for(reader).post(
            reverse("ai-ask-stream"),
            {"question": FLOOD_QUESTION, "conversation_id": conversation.pk}, format="json")
        events = events_of(response)

    assert response.status_code == 200
    steps = [data for name, data in events if name == "agent_step" and data["status"] != "running"]
    by_tool = [(step["tool"], step["status"]) for step in steps if step["kind"] == "tool"]
    assert by_tool[1:5] == [("find_records", "ok"), ("search_passages", "ok"),
                            ("search_passages", "rejected"), ("read_record_sections", "rejected")]

    captured = sent(planner)
    assert "Flood Prediction" in captured
    assert HIDDEN not in captured
    done = events[-1][1]
    assert HIDDEN not in json.dumps(done)
