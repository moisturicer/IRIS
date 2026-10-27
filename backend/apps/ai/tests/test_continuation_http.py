"""IR-595: an opaque continuation artifact is echoed to the vendor, never to a reader."""
import json
from dataclasses import replace

import pytest

from apps.ai.composition import use_composition_root
from apps.ai.models import Turn
from apps.ai.providers.fakes import ScriptedToolCallingLLM
from apps.ai.providers.tool_calling import AssistantMessage, ContinuationArtifact

from .test_controller_http import call, compose, controller_root
from .test_grounded_answer_http import Replies
from .test_public_protocol_http import GOOD, PUBLIC, SUMMARY, ask

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

SIGNATURE = [{"type": "reasoning.encrypted", "data": "SIG-9f3a"}]


def test_a_signature_survives_the_planner_round_and_never_reaches_a_reader(
    flood_scene, monkeypatch, embedder,
):
    first = replace(
        call("search_research", {"query": "flood prediction", "target": "passages"}, "c1"),
        continuation=(ContinuationArtifact("reasoning_details", SIGNATURE),))
    planner = ScriptedToolCallingLLM([first, compose(basis="evidence")])
    root = controller_root(monkeypatch, embedder=embedder, planner=planner,
                           writer=Replies(GOOD % SUMMARY))
    with use_composition_root(root):
        body, events = ask(flood_scene["client"], "ai-ask-stream", flood_scene["conversation"],
                           protocol=PUBLIC)

    echoed = [m for m in planner.conversation_requests[1].messages
              if isinstance(m, AssistantMessage)]
    assert echoed and echoed[0].continuation[0].payload == SIGNATURE
    turn = Turn.objects.get(conversation=flood_scene["conversation"])
    stored = f"{turn.answer}{turn.reasoning}{turn.reasoning_summary}{turn.routing}{turn.research}"
    assert "SIG-9f3a" not in json.dumps(events) and "SIG-9f3a" not in stored
