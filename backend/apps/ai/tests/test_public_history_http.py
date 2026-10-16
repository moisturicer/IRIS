"""IR-595: replay, reconnect and reopened history under the public protocol (A13, A14).

Old Turns keep their raw reasoning, routing and research in the database; the
public projection never sends them. Fakes only.
"""
import json

import pytest
from django.urls import reverse

from apps.ai.composition import use_composition_root
from apps.ai.models import Conversation, Turn, TurnCitation
from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.providers.ports import StreamDelta
from apps.ai.tasks import answer_queued_question
from core.enums import PipelineStatus

from .corpus import FLOOD_QUESTION, FLOOD_TEXT, ask_stream, make_record, make_user, root_with
from .test_durable_ask_http import _submit

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

PUBLIC = "public-1"
RAW = "OLD RAW REASONING text"
LEAKS = (RAW, "agent_step", "allowed_overrides", "search_research", "lane")


def _frames(chunks):
    """`(id or None, event, data)`; an activity frame shares its event's id with the frame after it."""
    frames = []
    for block in b"".join(chunks).decode("utf-8").split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.strip().split("\n")
                      if line and not line.startswith(":"))
        if "event" in fields:
            frames.append((int(fields["id"]) if "id" in fields else None,
                           fields["event"], json.loads(fields["data"])))
    return frames


def legacy_turn(conversation, **fields):
    return Turn.objects.create(
        conversation=conversation, question="Old question?", answer="Old answer.",
        state="generated", had_reasoning=True, reasoning=RAW,
        routing={"lane": "listing", "allowed_overrides": ["passages"], "probabilities": {"a": 1}},
        research={"steps": [{"tool": "search_research", "kind": "agent_step"}]}, **fields)


def detail(client, conversation, **params):
    response = client.get(reverse("ai-conversation-detail", args=[conversation.pk]), params)
    assert response.status_code == 200
    return response.json()


def test_old_turns_are_projected_without_raw_internals_and_stay_stored(client_for):
    reader = make_user("history@cit.edu")
    conversation = Conversation.objects.create(user=reader)
    turn = legacy_turn(conversation)
    client = client_for(reader)

    public = detail(client, conversation, protocol=PUBLIC)
    legacy = detail(client, conversation)

    (shown,) = public["turns"]
    assert shown["answer"] == "Old answer." and shown["mode"] == "generative"
    assert "reasoning_summary" not in shown
    assert not any(leak in json.dumps(public) for leak in LEAKS)
    assert legacy["turns"][0]["reasoning"] == RAW
    turn.refresh_from_db()
    assert turn.reasoning == RAW and turn.routing["lane"] == "listing" and turn.research


def test_a_stored_summary_follows_the_turn_and_is_withheld_when_a_cited_source_is_gone(
    embedder, space, client_for,
):
    reader = make_user("summary-history@cit.edu")
    other = make_user("owner@cit.edu")
    visible = make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    hidden = make_record(title="Hidden draft", text=FLOOD_TEXT, embedder=embedder, space=space,
                         status=PipelineStatus.DRAFT, owner=other)
    conversation = Conversation.objects.create(user=reader)
    turn = legacy_turn(conversation, reasoning_summary="Only one paper addresses forecasting.",
                       reasoning_summary_source="controller-v1/answer-1")
    TurnCitation.objects.create(turn=turn, marker=1, record=visible)
    client = client_for(reader)

    assert detail(client, conversation, protocol=PUBLIC)["turns"][0]["reasoning_summary"] == (
        "Only one paper addresses forecasting.")

    TurnCitation.objects.create(turn=turn, marker=2, record=hidden)
    shown = detail(client, conversation, protocol=PUBLIC)["turns"][0]
    assert "reasoning_summary" not in shown
    assert [c["record_id"] for c in shown["citations"]] == [visible.pk]


def test_the_header_selects_the_protocol_and_an_unknown_one_is_refused(client_for):
    reader = make_user("header@cit.edu")
    conversation = Conversation.objects.create(user=reader)
    legacy_turn(conversation)
    client = client_for(reader)
    url = reverse("ai-conversation-detail", args=[conversation.pk])

    assert RAW not in json.dumps(client.get(url, HTTP_X_IRIS_PROTOCOL=PUBLIC).json())
    assert client.get(url, HTTP_X_IRIS_PROTOCOL="public-9").status_code == 400


@pytest.fixture(autouse=True)
def queued(settings):
    settings.AI_DURABLE_ASK = True
    settings.AI_DURABLE_ASK_POLL_SECONDS = 0
    settings.AI_RESEARCH_LANE = "off"
    settings.AI_JEV_ROUTING_ENABLED = False


@pytest.fixture
def dispatched(monkeypatch):
    sent = []
    monkeypatch.setattr(
        answer_queued_question, "apply_async", lambda args, **limits: sent.append((args[0], limits)))
    return sent


def finished_run(embedder, space, client_for, dispatched, capture):
    reader = make_user("queued@cit.edu")
    make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    conversation = Conversation.objects.create(user=reader)
    llm = ScriptedLLM(stream_deltas=[
        StreamDelta(reasoning="private working "),
        StreamDelta(text="Rainfall gauges feed the model [1]."),
    ])
    client = client_for(reader)
    run_id, _ = _submit(client, conversation, dispatched, capture)
    with use_composition_root(root_with(embedder=embedder, llm=llm)):
        answer_queued_question(run_id)
    return client, run_id


def test_replay_and_reconnect_are_public_and_never_repeat_activity_or_the_final_event(
    embedder, space, client_for, dispatched, django_capture_on_commit_callbacks,
):
    client, run_id = finished_run(embedder, space, client_for, dispatched,
                                  django_capture_on_commit_callbacks)

    response = client.get(reverse("ai-ask-run-stream", args=[run_id]), {"protocol": PUBLIC})
    frames = _frames(response.streaming_content)
    names = [name for _, name, _ in frames]
    published = json.dumps(frames)

    assert set(names) <= {"activity", "run_queued", "run_started", "text_delta",
                          "citations_resolved", "done"}
    assert names.count("done") == 1 and names[-1] == "done"
    assert not any(leak in published for leak in ("routing", "agent_step", "private working"))
    states = [data["state"] for _, name, data in frames if name == "activity"]
    assert states == ["waiting", "thinking", "preparing"]

    resume_at = next(sequence for sequence, name, _ in frames if name == "text_delta")
    assert resume_at is not None
    again = _frames(client.get(
        reverse("ai-ask-run-stream", args=[run_id]),
        {"protocol": PUBLIC, "after": resume_at}).streaming_content)
    assert [name for _, name, _ in again if name == "activity"] == []
    assert [name for _, name, _ in again].count("done") == 1


def test_the_legacy_replay_is_unchanged_without_the_protocol(
    embedder, space, client_for, dispatched, django_capture_on_commit_callbacks,
):
    client, run_id = finished_run(embedder, space, client_for, dispatched,
                                  django_capture_on_commit_callbacks)
    frames = _frames(client.get(reverse("ai-ask-run-stream", args=[run_id])).streaming_content)
    assert "activity" not in [name for _, name, _ in frames]
    assert "retrieval_started" in [name for _, name, _ in frames]


def test_a_queued_submission_streams_public_frames_from_the_first_event(
    embedder, space, client_for, dispatched, django_capture_on_commit_callbacks,
):
    reader = make_user("submit@cit.edu")
    conversation = Conversation.objects.create(user=reader)
    with django_capture_on_commit_callbacks(execute=True):
        response = ask_stream(client_for(reader), FLOOD_QUESTION,
                              conversation_id=conversation.pk, protocol=PUBLIC)
    first = next(iter(response.streaming_content))
    response._iterator.close()
    names = [name for _, name, _ in _frames([first])]
    assert names == ["activity"]
