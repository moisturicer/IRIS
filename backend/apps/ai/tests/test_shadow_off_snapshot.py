"""With the evidence decision off, the answer request is byte-for-byte what it
was before IR-466.

The snapshot in `snapshots/ask_adapter_request.json` was captured from the
code *before* the orchestrator existed. It is the request the real
`OpenAICompatibleAdapter` hands its client -- model, messages, temperature and
every extra -- for one follow-up question on each chat endpoint.

Regenerate only on a deliberate change to the answer prompt, with
`IRIS_WRITE_ASK_SNAPSHOT=1`, and say so in the PR.
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.test import override_settings

from apps.ai.composition import use_composition_root
from apps.ai.models import Conversation, Turn
from apps.ai.providers.openai_compatible import OpenAICompatibleAdapter

from .corpus import FLOOD_QUESTION, FLOOD_TEXT, ask, ask_stream, make_record, make_user, root_with

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

SNAPSHOT = Path(__file__).parent / "snapshots" / "ask_adapter_request.json"


class _RecordingClient:
    """The slice of the OpenAI client the adapter touches, recording requests."""

    def __init__(self):
        self.requests: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        if kwargs.get("stream"):
            delta = SimpleNamespace(content="Gauges feed it [1].", reasoning=None)
            return iter([SimpleNamespace(choices=[SimpleNamespace(delta=delta)])])
        message = SimpleNamespace(content="Gauges feed it [1].")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _request_for(endpoint, embedder, space, client_for) -> dict:
    reader = make_user("snapshot@cit.edu")
    make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    conversation = Conversation.objects.create(user=reader)
    Turn.objects.create(
        conversation=conversation,
        question="what data trained the model?",
        answer="Rainfall gauge data [1].",
        state="generated",
    )

    client = _RecordingClient()
    adapter = OpenAICompatibleAdapter(
        api_key="snapshot", model="snapshot-model", client=client
    )
    with use_composition_root(root_with(embedder=embedder, llm=adapter)):
        response = endpoint(
            client_for(reader), FLOOD_QUESTION, conversation_id=conversation.pk
        )
        if endpoint is ask_stream:
            b"".join(response.streaming_content)
    assert response.status_code == 200

    (request,) = client.requests
    return request


@override_settings(
    AI_EVIDENCE_DECISION="off",
    AI_QUESTION_RESOLUTION_ENABLED=False,
    AI_CONVERSATION_MEMORY_ENABLED=False,
    LLM_TEMPERATURE=0.1,
    LLM_REASONING_EFFORT="",
)
@pytest.mark.parametrize("name, endpoint", [("ask", ask), ("ask_stream", ask_stream)])
def test_the_answer_request_matches_the_pre_change_snapshot(
    name, endpoint, embedder, space, client_for
):
    request = _request_for(endpoint, embedder, space, client_for)

    if os.environ.get("IRIS_WRITE_ASK_SNAPSHOT") == "1":
        stored = json.loads(SNAPSHOT.read_text("utf-8")) if SNAPSHOT.exists() else {}
        stored[name] = request
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(json.dumps(stored, indent=2, sort_keys=True) + "\n", "utf-8")

    assert request == json.loads(SNAPSHOT.read_text("utf-8"))[name]
