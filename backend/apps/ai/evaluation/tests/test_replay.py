"""IR-606: replay through the authenticated reader and Conversation boundary."""

import json

import pytest
from django.urls import reverse

from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.controller.versions import CONTROLLER_ENGINE
from apps.ai.evaluation.replay import collect_case, collect_run
from apps.ai.models import Conversation
from apps.ai.providers.fakes import ScriptedLLM, ScriptedReranker, ScriptedToolCallingLLM
from apps.ai.research.tests.conftest import fresh_vector_indexes
from apps.ai.tests.corpus import FLOOD_TEXT, make_record, make_user
from apps.ai.tests.test_controller_http import call, compose, controller_root


pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


class Reader:
    def __init__(self, client):
        self.client = client

    def post(self, path, payload):
        return self.client.post(path, payload, format="json", HTTP_X_IRIS_PROTOCOL="public-1")

    def get(self, path):
        return self.client.get(path, HTTP_X_IRIS_PROTOCOL="public-1")


def test_repeating_a_case_creates_fresh_ordered_conversations(client_for, embedder, settings):
    settings.AI_DURABLE_ASK = False
    settings.AI_RESEARCH_LANE = "off"
    user = make_user("ir606-reader@cit.edu")
    reader = Reader(client_for(user))
    case = {"id": "dev-1", "family": "A01", "split": "development", "turns": [
        {"user": "Find papers about speech"}, {"user": "What about their limits?"},
    ]}
    planner = ScriptedToolCallingLLM(script=lambda request: compose(basis="general"),
                                     reply="A direct answer.")
    root = CompositionRoot(embedder=embedder, reranker=ScriptedReranker(),
                           llm=planner, permits=lambda record: True, engine=CONTROLLER_ENGINE)
    with use_composition_root(root):
        first = collect_case(reader, case)
        second = collect_case(reader, case)
    assert first["conversation_id"] != second["conversation_id"]
    assert Conversation.objects.filter(user=user).count() == 2
    for result in (first, second):
        assert [t["question"] for t in result["turns"]] == [
            "Find papers about speech", "What about their limits?"]
        assert [t["outcome"] for t in result["turns"]] == ["answered", "answered"]
        assert [t["public_answer"]["answer"] for t in result["turns"]] == [
            "A direct answer.", "A direct answer."]
        assert [t["saved_turn"]["question"] for t in result["turns"]] == [
            "Find papers about speech", "What about their limits?"]
        assert len(result["reopened_transcript"]) == 2
        assert all(t["usage_status"] == "missing" for t in result["turns"])
        assert all("routing" not in json.dumps(t["public_answer"]) for t in result["turns"])


def test_a_failed_turn_is_still_counted_and_subsequent_turns_stop(client_for, embedder, settings):
    settings.AI_DURABLE_ASK = False
    user = make_user("ir606-failure@cit.edu")
    reader = Reader(client_for(user))
    case = {"id": "failure", "family": "A09", "split": "development", "turns": [
        {"user": "one"}, {"user": "two"},
    ]}
    original = reader.post

    def fail_ask(path, payload):
        if path == reverse("ai-ask-stream"):
            raise TimeoutError("test timeout")
        return original(path, payload)

    reader.post = fail_ask
    result = collect_case(reader, case)
    assert len(result["turns"]) == 1
    assert result["turns"][0]["outcome"] == "timeout"
    assert result["turns"][0]["saved_turn"] is None
    assert result["status"] == "incomplete"


def test_run_manifest_is_scorer_readable_and_has_no_private_fields(client_for, embedder, settings):
    settings.AI_DURABLE_ASK = False
    user = make_user("ir606-manifest@cit.edu")
    reader = Reader(client_for(user))
    case = {"id": "dev-2", "family": "A01", "split": "development",
            "turns": [{"user": "Hello"}]}
    planner = ScriptedToolCallingLLM(script=lambda request: compose(basis="general"),
                                     reply="A direct answer.")
    root = CompositionRoot(embedder=embedder, reranker=ScriptedReranker(),
                           llm=planner, permits=lambda record: True, engine=CONTROLLER_ENGINE)
    with use_composition_root(root):
        result = collect_run(reader, [case], set_id="s", set_digests={"development": "abc"},
                             corpus={"snapshot_id": "fake", "paper_set_sha256": "def"},
                             model_ids={"answer": "scripted"}, limits={"case_attempts": 2},
                             data_policy="fake-only", cache="cold")
    assert result["arm"] == "controller"
    assert result["manifest"]["set_digests"] == {"development": "abc"}
    assert result["manifest"]["protocol_version"] == "public-1"
    assert result["conversations"][0]["id"] == "dev-2"
    assert result["providers"] == "fake"
    assert "credential" not in json.dumps(result["manifest"]).lower()


def test_cited_public_answer_and_reopened_turn_keep_source_ids(
    client_for, embedder, space, settings, monkeypatch,
):
    from apps.ai.controller.budget import FAKE_TEST_PROFILE

    for name, value in FAKE_TEST_PROFILE.items():
        setattr(settings, name, value)
    settings.AI_DURABLE_ASK = False
    fresh_vector_indexes()
    user = make_user("ir606-cited@cit.edu")
    paper = make_record(title="Flood Prediction", text=FLOOD_TEXT,
                        embedder=embedder, space=space)
    planner = ScriptedToolCallingLLM([
        call("search_research", {"query": "flood prediction", "target": "passages"}, "c1"),
        compose(basis="evidence"),
    ])
    root = controller_root(monkeypatch, embedder=embedder, planner=planner,
                           writer=ScriptedLLM(reply="Flood Prediction forecasts river levels [1]."))
    case = {"id": "cited", "family": "A01", "split": "development",
            "turns": [{"user": "What do papers say about flood prediction?"}]}
    with use_composition_root(root):
        result = collect_case(Reader(client_for(user)), case)
    turn = result["turns"][0]
    assert turn["outcome"] == "answered"
    assert turn["citation_record_ids"] == [paper.pk]
    assert paper.pk in turn["source_ids"]
    assert turn["saved_turn"]["id"] == result["reopened_transcript"][0]["id"]
    assert "routing" not in json.dumps(turn["public_answer"])
