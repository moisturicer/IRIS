"""IR-504: staff-first enablement, `agent_step` events and their replay."""
import json

import pytest
from django.urls import reverse

from apps.ai.composition import use_composition_root
from apps.ai.inference import InferenceTask
from apps.ai.models import Conversation
from apps.ai.providers.fakes import ScriptedToolCallingLLM
from core.permissions import ROLE_KTTO

from .corpus import FLOOD_QUESTION, FLOOD_TEXT, make_record, make_user, root_with
from .test_routed_chat_http import answer, route

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def events_of(response):
    events = []
    for block in b"".join(response.streaming_content).decode().split("\n\n"):
        if block:
            name, data = block.split("\n", 1)
            events.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


def planning(monkeypatch, root, *calls):
    planner = ScriptedToolCallingLLM([
        ScriptedToolCallingLLM.calling(name, json.dumps(args), f"call-{i}")
        for i, (name, args) in enumerate(calls)
    ])
    real = root.llm_for
    monkeypatch.setattr(root, "llm_for", lambda task: planner if task == InferenceTask.PLAN else real(task))
    return planner


@pytest.mark.parametrize("endpoint", ["ai-ask", "ai-ask-stream"])
def test_staff_mode_routes_office_staff_only(endpoint, settings, monkeypatch, embedder, space, client_for):
    settings.AI_RESEARCH_LANE = "staff"
    route(monkeypatch, "passage")
    make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    with use_composition_root(root_with(embedder=embedder)):
        staff = answer(client_for(make_user("ktto@cit.edu", ROLE_KTTO)), endpoint, FLOOD_QUESTION)
        monkeypatch.setattr("apps.ai.routing.chat.configured_providers",
                            lambda **kwargs: pytest.fail("router constructed for a reader"))
        reader = answer(client_for(make_user("reader@cit.edu")), endpoint, FLOOD_QUESTION,
                        route_override="research")
    assert staff["routing"]["lane"] == "passage"
    assert "routing" not in reader and "research" not in reader
    assert reader["mode"] == "generative"


def test_research_stream_reports_steps_and_a_reopened_transcript_replays_them(
    settings, monkeypatch, embedder, space, client_for,
):
    settings.AI_RESEARCH_LANE = "on"
    settings.AI_RESEARCH_MAX_TOOL_CALLS = 2
    route(monkeypatch, "research")
    reader = make_user("steps@cit.edu")
    make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    conversation = Conversation.objects.create(user=reader)
    root = root_with(embedder=embedder)
    planning(monkeypatch, root, ("plan_research", {"subtasks": ["Find findings"]}),
             ("search_passages", {"query": "flood prediction"}), ("subtask_done", {}))
    client = client_for(reader)
    with use_composition_root(root):
        response = client.post(reverse("ai-ask-stream"),
                               {"question": FLOOD_QUESTION, "conversation_id": conversation.pk},
                               format="json")
        events = events_of(response)
    names = [name for name, _ in events]
    assert names.index("routing_decided") < names.index("agent_step") < names.index("done")
    steps = [data for name, data in events if name == "agent_step"]
    search = [step for step in steps if step["tool"] == "search_passages"]
    assert [step["status"] for step in search] == ["running", "ok"]
    assert search[1]["found"] >= 1 and search[1]["coverage"]
    assert FLOOD_QUESTION not in json.dumps(steps)

    done = events[-1][1]
    research = done["research"]
    assert research["steps"] == [step for step in steps if step["status"] != "running"]
    assert research["coverage_notes"][0]["code"] == "stopped_early"
    assert "stopped before coverage" not in done["answer"]

    replay = client.get(reverse("ai-conversation-detail", args=[conversation.pk])).json()["turns"][0]
    assert replay["research"] == research


@pytest.mark.parametrize("mode", ["off", "staff"])
def test_a_reader_stream_has_no_agent_steps_unless_the_lane_is_on_for_them(
    mode, settings, monkeypatch, embedder, space, client_for,
):
    settings.AI_RESEARCH_LANE = mode
    monkeypatch.setattr("apps.ai.routing.chat.configured_providers",
                        lambda **kwargs: pytest.fail("router constructed"))
    make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    with use_composition_root(root_with(embedder=embedder)):
        response = client_for(make_user("plain@cit.edu")).post(
            reverse("ai-ask-stream"), {"question": FLOOD_QUESTION, "route_override": "research"},
            format="json")
        names = [name for name, _ in events_of(response)]
    assert "agent_step" not in names and "routing_decided" not in names
    assert names[0] == "retrieval_started" and names[-1] == "done"
