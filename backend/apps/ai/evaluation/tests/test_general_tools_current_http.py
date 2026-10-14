"""IR-589: execute every proposed conversation against the current reader boundary.

This is a current-system control, not a test that the proposed controller exists.
The deterministic vendors and snapshot keep it free of paid calls. The richer
expected outcomes in general_tools_contract_v1.json are intentionally scored
only after the corresponding runtime tickets land.
"""

import json
from pathlib import Path

import httpx
import pytest
from django.urls import reverse

from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.models import Conversation
from apps.ai.providers.fakes import ScriptedLLM, ScriptedReranker
from apps.ai.tests.corpus import make_record, make_user
from core.enums import PipelineStatus


pytestmark = [pytest.mark.db_required, pytest.mark.django_db]
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "general_tools_contract_v1.json"
PACK = json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def no_paid_network(monkeypatch):
    def refuse(*args, **kwargs):
        pytest.fail("IR-589 current baseline reached the network")

    monkeypatch.setattr(httpx.Client, "send", refuse)
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)


@pytest.fixture
def corpus(embedder, space):
    other = make_user("ir589-other@cit.edu")
    return {
        paper["key"]: make_record(
            title=paper["title"], text=paper["text"], embedder=embedder,
            space=space, status=PipelineStatus.PUBLISHED,
            owner=other if not paper["readable"] else None,
        )
        for paper in PACK["paper_set"]
    }


def _done(response, endpoint):
    assert response.status_code == 200
    if endpoint == "ai-ask":
        return response.json()
    events = []
    for block in b"".join(response.streaming_content).decode().split("\n\n"):
        if block:
            name, data = block.split("\n", 1)
            events.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return next(data for name, data in events if name == "done")


@pytest.mark.parametrize("endpoint", ["ai-ask", "ai-ask-stream"])
@pytest.mark.parametrize("case", PACK["cases"], ids=lambda case: case["id"])
def test_current_boundary_replays_each_scenario_without_private_data(
    case, endpoint, settings, embedder, corpus, client_for
):
    """Pin the control path's shape; proposed outcomes stay separate in JSON."""
    settings.AI_RESEARCH_LANE = "off"
    settings.AI_DURABLE_ASK = False
    reader = make_user("ir589-reader@cit.edu")
    conversation = Conversation.objects.create(user=reader)
    client = client_for(reader)
    root = CompositionRoot(
        embedder=embedder, reranker=ScriptedReranker(), llm=ScriptedLLM(),
        permits=lambda record: record.pk != corpus["private-draft"].pk,
    )
    with use_composition_root(root):
        for question in case["turns"]:
            response = client.post(reverse(endpoint), {
                "question": question, "conversation_id": conversation.pk,
            }, format="json")
            body = _done(response, endpoint)
            assert body["mode"] in {"generative", "no_sources", "no_results", "unavailable", "partial"}
            assert "routing" not in body  # the current fixed lane is disabled
            assert corpus["private-draft"].title not in json.dumps(body)

    replay = client.get(reverse("ai-conversation-detail", args=[conversation.pk]))
    assert replay.status_code == 200
    turns = replay.json()["turns"]
    assert len(turns) == len(case["turns"])
    assert corpus["private-draft"].title not in json.dumps(turns)
