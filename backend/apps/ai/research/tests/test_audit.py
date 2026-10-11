import json
from io import StringIO

import pytest
from django.core.management import call_command, CommandError
from rest_framework.test import APIClient

from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.models import Conversation
from apps.ai.providers.fakes import ScriptedReranker
from .test_planner import run, planning
from .helpers import TOPIC

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def read(user, run_id):
    client = APIClient()
    client.force_authenticate(user=user)
    return client.get(f"/api/v1/ai/research/runs/{run_id}/")


def test_audit_has_only_telemetry_and_is_private_to_the_owner(corpus, embedder):
    model = planning(("search_passages", {"query": TOPIC}), ("finish", {}))
    result = run(corpus, embedder, model)
    response = read(corpus["student"], result.run_id)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "generated"
    assert len(data["steps"]) == 5
    assert len(data["steps"][1]["argument_digest"]) == 64
    serialized = json.dumps(data)
    assert TOPIC not in serialized
    assert "Flood forecasting" not in serialized
    assert result.answer.text not in serialized
    assert read(corpus["other"], result.run_id).status_code == 404
    assert APIClient().get(f"/api/v1/ai/research/runs/{result.run_id}/").status_code in (401, 403)


def test_command_runs_as_user_and_prints_steps_and_citations(corpus, embedder):
    fake = planning(("search_passages", {"query": TOPIC}), ("finish", {}))
    stack = CompositionRoot(embedder=embedder, reranker=ScriptedReranker(), llm=fake, permits=lambda record: True)
    output = StringIO()
    with use_composition_root(stack):
        call_command("ask_agent", TOPIC, user=corpus["student"].email, stdout=output)
    assert "search_passages: ok" in output.getvalue()
    assert "[1] E" in output.getvalue()


def test_command_cannot_borrow_another_readers_conversation(corpus):
    conversation = Conversation.objects.create(user=corpus["other"])
    with pytest.raises(CommandError, match="No such Conversation"):
        call_command("ask_agent", TOPIC, user=corpus["student"].email, conversation=conversation.pk)
