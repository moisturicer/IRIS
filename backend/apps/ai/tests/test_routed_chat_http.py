"""IR-515 chat routing through JSON, SSE and reopened transcripts."""
import json

import pytest
from django.urls import reverse

from apps.ai.composition import use_composition_root
from apps.ai.inference import InferenceTask
from apps.ai.models import Conversation, Turn
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
    monkeypatch.setattr("apps.ai.routing.chat.configured_providers", lambda **kwargs: (jev, None))
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
    monkeypatch.setattr("apps.ai.routing.chat.configured_providers", lambda **kwargs: pytest.fail("router constructed while off"))
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
    assert body["listing"]["completeness"] == "matches_found"
    assert body["listing"]["records"] == [{"record_id": paper.pk, "title": paper.title}]
    assert "1 match among 1 assessed of 1 selected candidate paper, with 0 not assessed" in body["answer"]


@pytest.mark.parametrize("endpoint", ["ai-ask", "ai-ask-stream"])
@pytest.mark.parametrize("criterion", ["", " on methodology"])
def test_comparison_cites_each_paper_and_reports_missing_evidence(endpoint, criterion, settings, monkeypatch, embedder, space, client_for):
    settings.AI_RESEARCH_LANE = "on"
    route(monkeypatch, "comparison")
    reader = make_user("compare@cit.edu")
    a = make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    b = make_record(title="Rainfall Forecast", text=FLOOD_TEXT, embedder=embedder, space=space)
    Record.objects.create(title="Empty Study", pipeline_status=PipelineStatus.PUBLISHED)
    llm = ScriptedLLM("The supplied papers use gauges [1] [2].")
    with use_composition_root(root_with(embedder=embedder, llm=llm)):
        body = answer(client_for(reader), endpoint, 'Compare "Flood Prediction", "Rainfall Forecast" and "Empty Study"' + criterion, top_k=3)
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
    monkeypatch.setattr("apps.ai.routing.chat.configured_providers", lambda **kwargs: (None, None))
    root = root_with()
    monkeypatch.setattr(root, "retriever", lambda **kw: pytest.fail("landscape retrieved during outage"))
    with use_composition_root(root):
        body = answer(client_for(make_user("outage@cit.edu")), endpoint, "List research gaps in the state of the field")
    assert body["routing"]["lane"] == "landscape"
    assert body["mode"] == "no_results"
    assert "landscape" in body["message"]


@pytest.mark.parametrize("endpoint", ["ai-ask", "ai-ask-stream"])
def test_scoped_landscape_is_refused_without_passage_lookup(endpoint, settings, monkeypatch, embedder, space, client_for):
    settings.AI_RESEARCH_LANE = "on"
    route(monkeypatch, "landscape")
    reader = make_user("scoped-landscape@cit.edu")
    paper = make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    conversation = Conversation.objects.create(user=reader, record=paper)
    root = root_with(embedder=embedder)
    monkeypatch.setattr(root, "retriever", lambda **kw: pytest.fail("scoped landscape retrieved"))
    with use_composition_root(root):
        body = answer(client_for(reader), endpoint, "What research gaps does this paper reveal?", conversation_id=conversation.pk)
    assert body["routing"]["lane"] == "landscape"
    assert body["mode"] == "no_results" and "landscape" in body["message"]
    assert body["widened"] is False


@pytest.mark.parametrize("endpoint", ["ai-ask", "ai-ask-stream"])
@pytest.mark.parametrize("question", [
    "Compare Flood Prediction with Unknown Thesis",
    'Compare "Flood Prediction" with Unknown Thesis',
])
def test_unresolved_unquoted_comparison_requests_explicit_titles(endpoint, question, settings, monkeypatch, embedder, space, client_for):
    settings.AI_RESEARCH_LANE = "on"
    route(monkeypatch, "comparison")
    reader = make_user("unresolved-compare@cit.edu")
    make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    llm = ScriptedLLM("A single-paper answer [1].")
    with use_composition_root(root_with(embedder=embedder, llm=llm)):
        body = answer(client_for(reader), endpoint, question)
    assert body["mode"] == "no_results"
    assert "Name each paper by its full title" in body["message"]
    assert "Unknown Thesis" in body["message"]
    assert not llm.calls


@pytest.mark.parametrize("endpoint", ["ai-ask", "ai-ask-stream"])
def test_original_turn_override_keeps_resolution_history_and_scope(endpoint, settings, monkeypatch, embedder, space, client_for):
    settings.AI_RESEARCH_LANE = "on"
    route(monkeypatch, "research")
    reader = make_user("old-override@cit.edu")
    paper = make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    conversation = Conversation.objects.create(user=reader, record=paper)
    Turn.objects.create(conversation=conversation, question="What trained Flood Prediction?", answer="Rainfall gauges.", state="generated")
    source = Turn.objects.create(conversation=conversation, question="What are its methods?", resolved_question=FLOOD_QUESTION, answer="Rainfall method.", state="generated", widened=False)
    Turn.objects.create(conversation=conversation, question="Tell me about Other Study", answer="Other Study is about ponds.", state="generated")
    root = root_with(embedder=embedder)
    monkeypatch.setattr(root, "resolver", lambda: pytest.fail("saved override re-resolved"))
    llm = root.llm_for(InferenceTask.ANSWER)
    with use_composition_root(root):
        body = answer(client_for(reader), endpoint, source.question, conversation_id=conversation.pk,
                      route_override="passage", route_override_turn_id=source.pk, widen=True)
    assert body["resolved_question"] == FLOOD_QUESTION
    assert body["widened"] is False
    assert body["turn_id"] > source.pk
    assert body["routing"]["override_applied"]
    assert FLOOD_QUESTION in llm.calls[0][1]
    assert "Other Study" not in llm.calls[0][1]
    replay = client_for(reader).get(reverse("ai-conversation-detail", args=[conversation.pk])).json()["turns"][-1]
    assert replay["question"] == source.question
    assert replay["resolved_question"] == source.resolved_question


def test_override_reference_must_belong_to_owned_conversation(settings, client_for):
    settings.AI_RESEARCH_LANE = "on"
    reader, other = make_user("ref-reader@cit.edu"), make_user("ref-other@cit.edu")
    own = Conversation.objects.create(user=reader)
    foreign = Conversation.objects.create(user=other)
    turn = Turn.objects.create(conversation=foreign, question="secret", answer="secret", state="generated")
    client = client_for(reader)
    for reference in (turn.pk, turn.pk + 999):
        response = client.post(reverse("ai-ask"), {"question": "q", "conversation_id": own.pk,
            "route_override": "passage", "route_override_turn_id": reference}, format="json")
        assert response.status_code == 404


def test_count_totals_do_not_reach_planner_after_permission_change(settings, monkeypatch, embedder, space, client_for):
    from apps.ai.providers.fakes import ScriptedToolCallingLLM

    settings.AI_RESEARCH_LANE = "on"
    route(monkeypatch, "count")
    reader = make_user("count-history@cit.edu")
    paper = make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    conversation = Conversation.objects.create(user=reader)
    root = root_with(embedder=embedder)
    planner = ScriptedToolCallingLLM([ScriptedToolCallingLLM.calling("finish", "{}", "finish")])
    real = root.llm_for
    monkeypatch.setattr(root, "llm_for", lambda task: Screen() if task == InferenceTask.SCREEN else planner if task == InferenceTask.PLAN else real(task))
    with use_composition_root(root):
        counted = answer(client_for(reader), "ai-ask", "How many papers about rainfall?", conversation_id=conversation.pk)
        assert "1 match among 1 assessed of 1 selected candidate paper" in counted["answer"]
        Record.objects.filter(pk=paper.pk).update(pipeline_status=PipelineStatus.DRAFT)
        route(monkeypatch, "research")
        answer(client_for(reader), "ai-ask", "Investigate pond methods", conversation_id=conversation.pk)
    sent = str(planner.conversation_requests)
    assert "match among" not in sent and "selected candidate" not in sent
    replay = client_for(reader).get(reverse("ai-conversation-detail", args=[conversation.pk])).json()["turns"]
    # A reopened count is rebuilt for what the reader can read now: the revoked paper is gone.
    assert "match among" not in replay[0]["answer"] and paper.title not in str(replay[0])


@pytest.mark.parametrize("endpoint", ["ai-ask", "ai-ask-stream"])
def test_research_override_uses_original_history_boundary(endpoint, settings, monkeypatch, embedder, space, client_for):
    from apps.ai.providers.fakes import ScriptedToolCallingLLM

    settings.AI_RESEARCH_LANE = "on"
    route(monkeypatch, "research")
    reader = make_user("research-old@cit.edu")
    conversation = Conversation.objects.create(user=reader)
    Turn.objects.create(conversation=conversation, question="Earlier reader question", answer="Earlier answer", state="generated")
    source = Turn.objects.create(conversation=conversation, question="What are its methods?", resolved_question=FLOOD_QUESTION, answer="ORIGINALANSWER", state="generated")
    Turn.objects.create(conversation=conversation, question="UNRELATEDQUESTION", answer="UNRELATEDANSWER", state="generated")
    root = root_with(embedder=embedder)
    planner = ScriptedToolCallingLLM([ScriptedToolCallingLLM.calling("finish", "{}", "finish")])
    real = root.llm_for
    monkeypatch.setattr(root, "llm_for", lambda task: planner if task == InferenceTask.PLAN else real(task))
    with use_composition_root(root):
        body = answer(client_for(reader), endpoint, source.question, conversation_id=conversation.pk,
                      route_override="research", route_override_turn_id=source.pk)
    assert body["routing"]["lane"] == "research" and body["resolved_question"] == FLOOD_QUESTION
    sent = str(planner.conversation_requests)
    assert "Earlier reader question" in sent and "Earlier answer" in sent
    assert "UNRELATEDQUESTION" not in sent and "UNRELATEDANSWER" not in sent
    assert "ORIGINALANSWER" not in sent
