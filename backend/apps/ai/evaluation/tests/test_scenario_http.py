"""IR-608: actions use IR-606's authenticated reader collector; no paid network."""
import json
import httpx
import pytest
from apps.ai.composition import use_composition_root
from apps.ai.controller.budget import FAKE_TEST_PROFILE
from apps.ai.evaluation.replay import collect_case, CONVERSATIONS
from apps.ai.management.commands.eval_replay_conversations import LocalReader
from apps.ai.models import Conversation
from apps.ai.providers.fakes import ScriptedLLM, ScriptedToolCallingLLM
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.research.tests.conftest import fresh_vector_indexes
from apps.ai.tests.corpus import FLOOD_TEXT, make_record, make_user
from apps.records.models import Record
from apps.ai.tests.test_controller_http import call, compose, controller_root
from core.enums import PipelineStatus
pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

@pytest.fixture(autouse=True)
def isolated(settings, monkeypatch):
    for name, value in FAKE_TEST_PROFILE.items():
        setattr(settings, name, value)
    settings.AI_DURABLE_ASK = False
    settings.AI_EVIDENCE_DECISION = "off"
    settings.AI_RESEARCH_LANE = "off"
    def refuse(*args, **kwargs):
        pytest.fail("scenario attempted a real network call")
    monkeypatch.setattr(httpx.Client, "send", refuse)
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)

def scenario(identifier, turns=1):
    return {"id": identifier, "family": "A11", "split": "development",
            "turns": [{"user": "Find research about flood prediction."} for _ in range(turns)]}

def reader_for(client_for, user):
    client = client_for(user)
    client.credentials(HTTP_X_IRIS_PROTOCOL="public-1")
    return LocalReader(client)

def test_private_and_foreign_data_never_enter_review_evidence(client_for, embedder, space, monkeypatch):
    fresh_vector_indexes()
    user, owner = make_user("scenario-reader@cit.edu"), make_user("scenario-owner@cit.edu")
    hidden = make_record(title="SECRET PRIVATE TITLE", text="SECRET PRIVATE PASSAGE",
                         embedder=embedder, space=space, owner=owner, status=PipelineStatus.DRAFT)
    foreign = Conversation.objects.create(user=owner, title="SECRET CONVERSATION")
    planner = ScriptedToolCallingLLM([
        call("search_research", {"query": "flood prediction", "target": "passages"}, "c1"),
        compose(basis="evidence")])
    writer = ScriptedLLM(reply="must not compose a paper claim")
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    reader = reader_for(client_for, user)
    with use_composition_root(root):
        result = collect_case(reader, scenario("private"))
    assert not writer.calls
    assert not result["turns"][0]["citation_record_ids"]
    assert hidden.title not in json.dumps(result) and "SECRET PRIVATE PASSAGE" not in json.dumps(result)
    assert hidden.title not in repr(planner.conversation_requests)
    denied = reader.get(f"{CONVERSATIONS}{foreign.pk}/")
    assert denied.status_code == 404 and "SECRET" not in json.dumps(denied.json())

def test_revocation_between_turns_removes_old_answer_from_reopened_evidence(client_for, embedder, space, monkeypatch):
    fresh_vector_indexes()
    user = make_user("scenario-revoke@cit.edu")
    paper = make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    planner = ScriptedToolCallingLLM([
        call("search_research", {"query": "flood prediction", "target": "passages"}, "c1"),
        compose(basis="evidence"), compose(basis="general")])
    writer = ScriptedLLM(reply="Flood Prediction forecasts river levels [1].")
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    def revoke(number, conversation_id):
        if number == 2:
            paper.pipeline_status = PipelineStatus.DRAFT
            paper.save(update_fields=["pipeline_status"])
            writer._reply = "General explanation of rainfall."
    observed = []
    with use_composition_root(root):
        result = collect_case(reader_for(client_for, user), scenario("revoked", 2),
                              before_turn=revoke, observe=lambda *args: observed.append(args))
    assert result["turns"][0]["citation_record_ids"] == [paper.pk]
    assert len(observed) == 2
    assert "forecasts river levels" not in json.dumps(result["reopened_transcript"])
    assert "forecasts river levels" not in json.dumps(result["turns"][1])
    assert len(writer.calls) == 2 and FLOOD_TEXT not in writer.calls[-1][1]

@pytest.mark.parametrize("condition", ["candidates_without_passages", "no_candidates", "rejected_arguments", "failure_after_evidence"])
def test_controlled_outcomes(condition, client_for, embedder, space, monkeypatch):
    fresh_vector_indexes()
    user = make_user("scenario-outcome@cit.edu")
    paper = None
    if condition != "no_candidates":
        paper = make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        if condition == "candidates_without_passages":
            # IR-703: abstracts and best passages are sources now; this case has neither.
            from apps.ai.research.tools import search
            monkeypatch.setattr(search, "BEST_PASSAGES", 0)
            Record.objects.filter(pk=paper.pk).update(abstract="")
    arguments = {"query": "flood prediction", "target": "papers" if condition == "candidates_without_passages" else "passages"}
    if condition == "rejected_arguments":
        arguments["user"] = 999
    planner = ScriptedToolCallingLLM([call("search_research", arguments, "c1"), compose(basis="evidence")])
    class Broken(ScriptedLLM):
        def generate(self, system, user):
            self.calls.append((system, user))
            raise LLMUnavailable("PRIVATE PROVIDER DIAGNOSTIC")
    writer = Broken() if condition == "failure_after_evidence" else ScriptedLLM(reply="Unused [1].")
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    with use_composition_root(root):
        result = collect_case(reader_for(client_for, user), scenario(condition))
    turn = result["turns"][0]
    assert "PRIVATE PROVIDER DIAGNOSTIC" not in json.dumps(result)
    assert turn["public_events"]
    if condition == "failure_after_evidence":
        assert writer.calls and FLOOD_TEXT in writer.calls[0][1]
        assert turn["outcome"] == "failure"
    else:
        assert not writer.calls and not turn["citation_record_ids"]
    if condition == "candidates_without_passages":
        assert paper.title in repr(planner.conversation_requests)
    if condition == "no_candidates":
        assert "Flood Prediction" not in repr(planner.conversation_requests)
    assert not any(key in json.dumps(turn["public_answer"]) for key in ("tool_unavailable", "tool arguments", "agent_step"))
