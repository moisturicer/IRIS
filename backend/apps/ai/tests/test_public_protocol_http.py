"""IR-595: the public reader protocol, captured at the HTTP boundary (A11, A13, A14).

Fakes only. The new protocol is opt-in (`protocol=public-1`); the legacy body
stays exactly as it was. Every assertion reads the bytes a client receives.
"""
import json

import pytest
from django.urls import reverse

from apps.ai.composition import use_composition_root
from apps.ai.models import Conversation, Turn
from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.providers.ports import StreamDelta

from .corpus import FLOOD_QUESTION, FLOOD_TEXT, make_record, make_user, root_with
from .test_controller_http import asked_flood, call, compose, controller_root
from .test_grounded_answer_http import Replies, searched

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

PUBLIC = "public-1"
INTERNAL_KEYS = ("routing", "research", "reasoning", "had_reasoning", "validation", "agent_step")
SUMMARY = "Only one paper addresses forecasting here."
GOOD = ('Flood Prediction forecasts river levels [1].\n```bindings\n'
        '{"summary": "%s"}\n```')


def events_of(response) -> list[tuple[str, dict]]:
    events = []
    for block in b"".join(response.streaming_content).decode().split("\n\n"):
        lines = [line for line in block.split("\n") if line and not line.startswith(":")]
        fields = dict(line.split(": ", 1) for line in lines)
        if "event" in fields:
            events.append((fields["event"], json.loads(fields["data"])))
    return events


def ask(client, endpoint, conversation, **options):
    response = client.post(
        reverse(endpoint),
        {"question": "What do papers say about flood prediction?",
         "conversation_id": conversation.pk, **options}, format="json")
    assert response.status_code == 200, response.content
    if endpoint == "ai-ask":
        return response.json(), [("done", response.json())]
    events = events_of(response)
    return next(data for name, data in events if name == "done"), events


def scene_root(monkeypatch, embedder, *replies):
    return searched(monkeypatch, embedder, Replies(*replies))


@pytest.mark.parametrize("endpoint", ["ai-ask", "ai-ask-stream"])
def test_a_supported_summary_is_public_and_internals_are_absent(
    endpoint, flood_scene, monkeypatch, embedder,
):
    root = scene_root(monkeypatch, embedder, GOOD % SUMMARY, GOOD % SUMMARY)
    with use_composition_root(root):
        body, events = ask(flood_scene["client"], endpoint, flood_scene["conversation"],
                           protocol=PUBLIC)

    assert body["answer"] == "Flood Prediction forecasts river levels [1]."
    assert body["reasoning_summary"] == SUMMARY
    assert not any(key in body for key in INTERNAL_KEYS)
    for name, data in events:
        assert name in {"activity", "done", "citations_resolved", "text_delta"}
        assert not any(key in data for key in INTERNAL_KEYS)
    turn = Turn.objects.get(conversation=flood_scene["conversation"])
    assert turn.reasoning_summary == SUMMARY and turn.reasoning == ""


def test_the_legacy_body_is_unchanged_and_carries_no_summary(flood_scene, monkeypatch, embedder):
    root = scene_root(monkeypatch, embedder, GOOD % SUMMARY)
    with use_composition_root(root):
        body, _ = ask(flood_scene["client"], "ai-ask", flood_scene["conversation"])

    assert "reasoning_summary" not in body
    assert {"had_reasoning", "reasoning", "mode", "sources"} <= set(body)


def test_activity_is_neutral_lifecycle_state_and_never_repeats(flood_scene, monkeypatch, embedder):
    root = scene_root(monkeypatch, embedder, GOOD % SUMMARY)
    with use_composition_root(root):
        _, events = ask(flood_scene["client"], "ai-ask-stream", flood_scene["conversation"],
                        protocol=PUBLIC)

    states = [data["state"] for name, data in events if name == "activity"]
    assert states and states[0] == "thinking"
    assert all(a != b for a, b in zip(states, states[1:]))
    assert set(states) <= {"waiting", "thinking", "preparing"}
    assert all(set(data) == {"state", "label"} for name, data in events if name == "activity")
    assert events[-1][0] == "done"


@pytest.mark.parametrize("narration", [
    "I called search_research twice to find this.",
    "The planner chose the listing route before answering.",
    "Reached 97% accuracy.",
    "The Mananga catchment study by Acme Corp proves it.",
])
def test_an_unsupported_or_narrating_summary_is_omitted(
    narration, flood_scene, monkeypatch, embedder,
):
    root = scene_root(monkeypatch, embedder, GOOD % narration)
    with use_composition_root(root):
        body, events = ask(flood_scene["client"], "ai-ask-stream", flood_scene["conversation"],
                           protocol=PUBLIC)

    assert body["answer"] == "Flood Prediction forecasts river levels [1]."
    assert "reasoning_summary" not in body
    assert "secret chain" not in json.dumps(events)
    assert Turn.objects.get(conversation=flood_scene["conversation"]).reasoning_summary == ""


def test_raw_think_tags_never_reach_the_answer_or_the_summary(flood_scene, monkeypatch, embedder):
    reply = ("<think>private plan</think>"
             + GOOD % ("<think>secret chain</think>" + SUMMARY))
    root = scene_root(monkeypatch, embedder, reply)
    with use_composition_root(root):
        body, events = ask(flood_scene["client"], "ai-ask", flood_scene["conversation"],
                           protocol=PUBLIC)

    assert "private plan" not in json.dumps(body) and "<think>" not in json.dumps(body)
    assert body["reasoning_summary"] == SUMMARY and "secret chain" not in json.dumps(body)


def test_a_reasoning_only_completion_is_unavailable_not_a_blank_answer(
    flood_scene, monkeypatch, embedder,
):
    root = scene_root(monkeypatch, embedder, "<think>only thinking</think>")
    with use_composition_root(root):
        body, _ = ask(flood_scene["client"], "ai-ask", flood_scene["conversation"],
                      protocol=PUBLIC)

    assert body["answer"] is None and body["mode"] == "unavailable"
    assert "reasoning_summary" not in body and "only thinking" not in json.dumps(body)


def test_a_streamed_reasoning_only_reply_is_unavailable_in_the_public_protocol(
    embedder, space, client_for,
):
    reader = make_user("reasoning-only@cit.edu")
    make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    conversation = Conversation.objects.create(user=reader)
    llm = ScriptedLLM(stream_deltas=[StreamDelta(reasoning="hidden working")])
    with use_composition_root(root_with(embedder=embedder, llm=llm)):
        response = client_for(reader).post(
            reverse("ai-ask-stream"),
            {"question": FLOOD_QUESTION, "conversation_id": conversation.pk, "protocol": PUBLIC},
            format="json")
        events = events_of(response)

    done = dict(events)["done"]
    assert done["answer"] is None and done["mode"] == "unavailable"
    assert "hidden working" not in json.dumps(events)
    assert not any(name == "reasoning_delta" for name, _ in events)


def test_an_unknown_protocol_is_refused(flood_scene):
    response = flood_scene["client"].post(
        reverse("ai-ask"), {"question": "x?", "protocol": "public-9"}, format="json")
    assert response.status_code == 400
