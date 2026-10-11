"""IR-515 chat routing through JSON, SSE and reopened transcripts."""
import json

import pytest
from django.urls import reverse

from apps.ai.composition import use_composition_root
from apps.ai.inference import InferenceTask
from apps.ai.models import Conversation
from apps.ai.providers.decisions import ScriptedDecisionModel
from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.providers.ports import LLMProvider
from apps.ai.routing.router import LANES
from apps.records.models import Record
from core.enums import PipelineStatus
from .corpus import FLOOD_TEXT, FLOOD_QUESTION, make_record, make_user, root_with

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def route(monkeypatch, lane, injection=False):
    probabilities = {name: 0.01 for name in LANES}
    probabilities[lane] = 0.95
    probabilities["injection"] = 0.99 if injection else 0.01
    jev = ScriptedDecisionModel(probabilities)
    monkeypatch.setattr("apps.ai.routing.chat.configured_providers", lambda: (jev, None))
    return jev


def answer(client, endpoint, question, **options):
    response = client.post(reverse(endpoint), {"question": question, **options}, format="json")
    assert response.status_code == 200
    if endpoint == "ai-ask":
        return response.json()
    events = []
    for line in b"".join(response.streaming_content).decode().split("\n\n"):
        if line:
            name, data = line.split("\n", 1)
            events.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return next(data for name, data in events if name == "done")


@pytest.mark.parametrize("endpoint", ["ai-ask", "ai-ask-stream"])
def test_off_never_constructs_router_or_changes_response(endpoint, settings, monkeypatch, embedder, space, client_for):
    settings.AI_RESEARCH_LANE = "off"
    monkeypatch.setattr("apps.ai.routing.chat.configured_providers", lambda: pytest.fail("router constructed while off"))
    reader = make_user("off@cit.edu")
    make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    with use_composition_root(root_with(embedder=embedder)):
        body = answer(client_for(reader), endpoint, FLOOD_QUESTION, route_override="research")
    assert "routing" not in body
    assert "listing" not in body
    assert body["mode"] == "generative"


@pytest.mark.parametrize("endpoint", ["ai-ask", "ai-ask-stream"])
def test_landscape_is_refused_without_retrieval_even_with_override(endpoint, settings, monkeypatch, client_for):
    settings.AI_RESEARCH_LANE = "on"
    route(monkeypatch, "landscape")
    reader = make_user("landscape@cit.edu")
    root = root_with()
    monkeypatch.setattr(root, "retriever", lambda **kw: pytest.fail("landscape retrieved passages"))
    with use_composition_root(root):
        body = answer(client_for(reader), endpoint, "What are the research gaps?", route_override="research")
    assert body["routing"]["lane"] == "landscape"
    assert body["routing"]["override_applied"] is False
    assert body["mode"] == "no_results"
    assert body["citations"] == []
    assert "landscape" in body["message"]


@pytest.mark.parametrize("endpoint", ["ai-ask", "ai-ask-stream"])
def test_override_and_decision_survive_reload(endpoint, settings, monkeypatch, embedder, space, client_for):
    settings.AI_RESEARCH_LANE = "on"
    jev = route(monkeypatch, "research")
    reader = make_user("override@cit.edu")
    make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    conversation = Conversation.objects.create(user=reader)
    client = client_for(reader)
    with use_composition_root(root_with(embedder=embedder)):
        body = answer(client, endpoint, FLOOD_QUESTION, conversation_id=conversation.pk, route_override="passage")
    decision = body["routing"]
    assert decision["suggested_lane"] == "research"
    assert decision["lane"] == "passage"
    assert decision["override"] == "passage" and decision["override_applied"]
    transcript = client.get(reverse("ai-conversation-detail", args=[conversation.pk])).json()
    assert transcript["turns"][0]["routing"] == decision
    assert len(jev.calls) == 1


class Screen(LLMProvider):
    def generate(self, system, user):
        papers = json.loads(user)["records"]
        return json.dumps({"decisions": [
            {"record": paper["record"], "decision": "include", "quote": paper["title"]}
            for paper in papers
        ] + [{"record": "Invented extra title", "decision": "include", "quote": "Fake"}]})


@pytest.mark.parametrize("endpoint", ["ai-ask", "ai-ask-stream"])
def test_listing_has_only_visible_database_matches_and_replays(endpoint, settings, monkeypatch, embedder, space, client_for):
    settings.AI_RESEARCH_LANE = "on"
    route(monkeypatch, "listing")
    reader = make_user("list@cit.edu")
    paper = make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    make_record(title="Secret Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space, status=PipelineStatus.DRAFT)
    root = root_with(embedder=embedder, llm=ScriptedLLM("Invented extra title"))
    real = root.llm_for
    monkeypatch.setattr(root, "llm_for", lambda task: Screen() if task == InferenceTask.SCREEN else real(task))
    conversation = Conversation.objects.create(user=reader)
    client = client_for(reader)
    with use_composition_root(root):
        body = answer(client, endpoint, FLOOD_QUESTION, conversation_id=conversation.pk)
    assert body["listing"]["records"] == [{"record_id": paper.pk, "title": paper.title}]
    assert "Invented" not in json.dumps(body)
    assert body["listing"]["completeness"] == "matches_found"
    replay = client.get(reverse("ai-conversation-detail", args=[conversation.pk])).json()["turns"][0]
    assert replay["listing"] == body["listing"]
    Record.objects.filter(pk=paper.pk).update(pipeline_status=PipelineStatus.DRAFT)
    replay = client.get(reverse("ai-conversation-detail", args=[conversation.pk])).json()["turns"][0]
    assert replay["listing"]["records"] == []
    assert paper.title not in replay["answer"]


@pytest.mark.parametrize("endpoint", ["ai-ask", "ai-ask-stream"])
@pytest.mark.parametrize("scoped,flagged", [(True, False), (False, True)])
def test_scoped_and_flagged_questions_cannot_override_into_planner(endpoint, scoped, flagged, settings, monkeypatch, embedder, space, client_for):
    settings.AI_RESEARCH_LANE = "on"
    route(monkeypatch, "research", injection=flagged)
    reader = make_user("scope@cit.edu")
    paper = make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    conversation = Conversation.objects.create(user=reader, record=paper if scoped else None)
    with use_composition_root(root_with(embedder=embedder)):
        body = answer(client_for(reader), endpoint, FLOOD_QUESTION, conversation_id=conversation.pk, route_override="research")
    assert body["routing"]["lane"] == "passage"
    assert body["routing"]["allowed_overrides"] == ["passage"]
    assert not body["routing"]["planner_allowed"]


def test_invalid_override_is_a_bad_request(settings, client_for):
    settings.AI_RESEARCH_LANE = "on"
    client = client_for(make_user("invalid@cit.edu"))
    for override in ("outside", {}, 3):
        response = client.post(reverse("ai-ask"), {"question": "hello", "route_override": override}, format="json")
        assert response.status_code == 400


@pytest.mark.parametrize("endpoint", ["ai-ask", "ai-ask-stream"])
def test_count_uses_screened_rows_and_reports_coverage(endpoint, settings, monkeypatch, embedder, space, client_for):
    settings.AI_RESEARCH_LANE = "on"
    route(monkeypatch, "count")
    reader = make_user("count@cit.edu")
    paper = make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    root = root_with(embedder=embedder)
    real = root.llm_for
    monkeypatch.setattr(root, "llm_for", lambda task: Screen() if task == InferenceTask.SCREEN else real(task))
    with use_composition_root(root):
        body = answer(client_for(reader), endpoint, "How many papers about rainfall?")
    assert body["routing"]["lane"] == "count"
    assert body["listing"]["completeness"] == "screened"
    assert body["listing"]["records"] == [{"record_id": paper.pk, "title": paper.title}]
    assert "1 matched out of 1 checked; 0 could not be assessed" in body["answer"]


@pytest.mark.parametrize("endpoint", ["ai-ask", "ai-ask-stream"])
def test_comparison_cites_each_paper_and_reports_missing_evidence(endpoint, settings, monkeypatch, embedder, space, client_for):
    settings.AI_RESEARCH_LANE = "on"
    route(monkeypatch, "comparison")
    reader = make_user("compare@cit.edu")
    a = make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    b = make_record(title="Rainfall Forecast", text=FLOOD_TEXT, embedder=embedder, space=space)
    Record.objects.create(title="Empty Study", pipeline_status=PipelineStatus.PUBLISHED)
    llm = ScriptedLLM("The supplied papers use gauges [1] [2].")
    with use_composition_root(root_with(embedder=embedder, llm=llm)):
        body = answer(client_for(reader), endpoint, 'Compare "Flood Prediction", "Rainfall Forecast" and "Empty Study"', top_k=3)
    assert {c["record_id"] for c in body["citations"]} == {a.pk, b.pk}
    assert "No readable passage evidence was found for: Empty Study" in body["answer"]
    assert {row["id"] for row in body["sources"]} == {a.pk, b.pk}


@pytest.mark.parametrize("endpoint", ["ai-ask", "ai-ask-stream"])
def test_research_reaches_bounded_planner_after_explicit_widen(endpoint, settings, monkeypatch, embedder, space, client_for):
    from apps.ai.providers.fakes import ScriptedToolCallingLLM

    settings.AI_RESEARCH_LANE = "on"
    route(monkeypatch, "research")
    reader = make_user("research@cit.edu")
    paper = make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    conversation = Conversation.objects.create(user=reader, record=paper)
    planner = ScriptedToolCallingLLM([ScriptedToolCallingLLM.calling("finish", "{}", "finish")])
    root = root_with(embedder=embedder)
    real = root.llm_for
    monkeypatch.setattr(root, "llm_for", lambda task: planner if task == InferenceTask.PLAN else real(task))
    with use_composition_root(root):
        body = answer(client_for(reader), endpoint, FLOOD_QUESTION, conversation_id=conversation.pk, widen=True)
    assert body["routing"]["lane"] == "research"
    assert body["widened"] is True
    assert body["mode"] == "no_results"
    assert len(planner.conversation_requests) == 1


@pytest.mark.parametrize("endpoint", ["ai-ask", "ai-ask-stream"])
def test_landscape_refusal_survives_router_outage(endpoint, settings, monkeypatch, client_for):
    settings.AI_RESEARCH_LANE = "on"
    monkeypatch.setattr("apps.ai.routing.chat.configured_providers", lambda: (None, None))
    root = root_with()
    monkeypatch.setattr(root, "retriever", lambda **kw: pytest.fail("landscape retrieved during outage"))
    with use_composition_root(root):
        body = answer(client_for(make_user("outage@cit.edu")), endpoint, "List research gaps in the state of the field")
    assert body["routing"]["lane"] == "landscape"
    assert body["mode"] == "no_results"
    assert "landscape" in body["message"]
