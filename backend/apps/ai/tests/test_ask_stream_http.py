"""Ask IRIS through the streaming HTTP boundary (IR-326).

Same shape as `test_ask_http.py`: driven through the composition root's
fake-injection seam, no vendor account, no network. What is different here
is the wire format -- Server-Sent Events rather than one JSON body -- so
`_parse_sse` turns a response body back into the ordered list of
``(event, data)`` pairs a reader's browser would see.
"""

import json

import pytest
from django.urls import reverse

from apps.ai.composition import use_composition_root
from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.providers.ports import StreamDelta
from core.enums import PipelineStatus

from .corpus import (
    FLOOD_QUESTION,
    FLOOD_TEXT,
    _BrokenLLM,
    ask,
    ask_stream,
    make_record,
    make_user,
    root_with,
)

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def _parse_sse(response) -> list[tuple[str, dict]]:
    """A `StreamingHttpResponse`'s events, in order.

    `.content` raises on a streaming response by design (Django's own
    anti-footgun) -- `streaming_content` is the generator this view actually
    yields from, consumed here exactly as a real client would.
    """
    text = b"".join(response.streaming_content).decode("utf-8")
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        name = None
        data = None
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = line[len("data:"):].strip()
        events.append((name, json.loads(data) if data is not None else None))
    return events


class StreamShapeTests:
    def test_the_event_vocabulary_arrives_in_order_with_streamed_text(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        flood = make_record(title="Flood Prediction", text=FLOOD_TEXT,
                            embedder=embedder, space=space)

        llm = ScriptedLLM(
            stream_deltas=[
                StreamDelta(text="Rainfall gauges "),
                StreamDelta(text="feed the model [1]."),
            ]
        )
        with use_composition_root(root_with(embedder=embedder, llm=llm)):
            response = ask_stream(client_for(reader), FLOOD_QUESTION)

        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/event-stream")
        events = _parse_sse(response)
        names = [name for name, _ in events]
        assert names == [
            "retrieval_started",
            "retrieval_finished",
            "generation_started",
            "text_delta",
            "text_delta",
            "citations_resolved",
            "done",
        ]

        finished = dict(events)["retrieval_finished"]
        assert finished == {"passage_count": 1, "record_count": 1, "degraded": False}

        deltas = [data["text"] for name, data in events if name == "text_delta"]
        assert deltas == ["Rainfall gauges ", "feed the model [1]."]

        citations_event = dict(events)["citations_resolved"]
        citation, = citations_event["citations"]
        assert citation["record_id"] == flood.pk
        assert citation["marker"] == 1

        done = dict(events)["done"]
        assert done["answer"] == "Rainfall gauges feed the model [1]."
        assert done["mode"] == "generative"
        assert done["degraded"] is False
        assert [c["record_id"] for c in done["citations"]] == [flood.pk]
        assert [s["id"] for s in done["sources"]] == [flood.pk]

    def test_the_done_event_matches_the_synchronous_endpoints_shape(
        self, embedder, space, client_for
    ):
        """The two endpoints must leave a client in an identical state --
        compared field-for-field against `/ask/`'s own JSON body, not just
        spot-checked, since that is the claim the `done` event makes."""
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder)):
            sync_body = ask(client_for(reader), FLOOD_QUESTION).json()
            events = _parse_sse(ask_stream(client_for(reader), FLOOD_QUESTION))

        done = dict(events)["done"]
        assert done == sync_body


class NoSourcesTests:
    def test_no_readable_sources_skips_generation_entirely(self, embedder, space, client_for):
        author = make_user("author@cit.edu")
        stranger = make_user("stranger@cit.edu")
        make_record(title="Unpublished Flood Draft", text=FLOOD_TEXT, owner=author,
                    status=PipelineStatus.DRAFT, embedder=embedder, space=space)

        llm = ScriptedLLM(stream_deltas=[StreamDelta(text="should never run")])
        with use_composition_root(root_with(embedder=embedder, llm=llm)):
            events = _parse_sse(
                ask_stream(client_for(stranger), FLOOD_QUESTION)
            )

        names = [name for name, _ in events]
        assert names == ["retrieval_started", "retrieval_finished", "done"]
        assert llm.calls == []

        done = dict(events)["done"]
        assert done["mode"] == "no_results"
        assert done["citations"] == []
        assert done["sources"] == []


class VendorFailureTests:
    def test_a_vendor_failure_mid_answer_still_ends_in_an_honest_done(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        flood = make_record(title="Flood Prediction", text=FLOOD_TEXT,
                            embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder, llm=_BrokenLLM())):
            events = _parse_sse(ask_stream(client_for(reader), FLOOD_QUESTION))

        names = [name for name, _ in events]
        assert names == [
            "retrieval_started", "retrieval_finished", "generation_started", "done",
        ]
        done = dict(events)["done"]
        assert done["answer"] is None
        assert done["mode"] == "unavailable"
        assert done["degraded"] is True
        assert [s["id"] for s in done["sources"]] == [flood.pk]


class ValidationTests:
    def test_a_blank_question_is_rejected_before_any_retrieval(self, client_for):
        reader = make_user("reader@cit.edu")
        assert ask_stream(client_for(reader), "   ").status_code == 400

    def test_an_anonymous_caller_is_refused(self):
        from rest_framework.test import APIClient

        response = APIClient().post(
            reverse("ai-ask-stream"), {"question": "x"}, format="json"
        )
        assert response.status_code in (401, 403)


class ReasoningTests:
    """The reasoning channel at the HTTP seam (IR-327): a scripted fake
    emitting `StreamDelta.reasoning`, the same seam `StreamShapeTests` above
    drives for text -- no vendor account, no network."""

    def test_reasoning_deltas_arrive_as_their_own_sse_event(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        flood = make_record(title="Flood Prediction", text=FLOOD_TEXT,
                            embedder=embedder, space=space)

        llm = ScriptedLLM(
            stream_deltas=[
                StreamDelta(reasoning="Checking the sources. "),
                StreamDelta(text="Rainfall gauges "),
                StreamDelta(reasoning="Looks right."),
                StreamDelta(text="feed the model [1]."),
            ]
        )
        with use_composition_root(root_with(embedder=embedder, llm=llm)):
            response = ask_stream(client_for(reader), FLOOD_QUESTION)

        events = _parse_sse(response)
        names = [name for name, _ in events]
        assert names == [
            "retrieval_started",
            "retrieval_finished",
            "generation_started",
            "reasoning_delta",
            "text_delta",
            "reasoning_delta",
            "text_delta",
            "citations_resolved",
            "done",
        ]

        reasoning_texts = [data["text"] for name, data in events if name == "reasoning_delta"]
        assert reasoning_texts == ["Checking the sources. ", "Looks right."]
        text_texts = [data["text"] for name, data in events if name == "text_delta"]
        assert text_texts == ["Rainfall gauges ", "feed the model [1]."]

        done = dict(events)["done"]
        assert done["answer"] == "Rainfall gauges feed the model [1]."
        assert "Checking the sources" not in done["answer"]
        assert done["had_reasoning"] is True
        assert [c["record_id"] for c in done["citations"]] == [flood.pk]

    def test_a_leaked_think_block_never_reaches_the_stored_answer(
        self, embedder, space, client_for
    ):
        """The defensive case: reasoning arriving in the text channel as
        `<think>...</think>` (the known gpt-oss-120b/Groq behaviour) must
        still surface as `reasoning_delta`, not `text_delta`, and must not
        appear in the persisted Turn."""
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)

        llm = ScriptedLLM(
            stream_deltas=[
                StreamDelta(text="<think>internal notes on rainfall gauges</think>"),
                StreamDelta(text="Rainfall gauges feed the model [1]."),
            ]
        )
        with use_composition_root(root_with(embedder=embedder, llm=llm)):
            response = ask_stream(client_for(reader), FLOOD_QUESTION)

        events = _parse_sse(response)
        text_texts = "".join(data["text"] for name, data in events if name == "text_delta")
        reasoning_texts = "".join(
            data["text"] for name, data in events if name == "reasoning_delta"
        )
        assert text_texts == "Rainfall gauges feed the model [1]."
        assert reasoning_texts == "internal notes on rainfall gauges"

        done = dict(events)["done"]
        assert done["answer"] == "Rainfall gauges feed the model [1]."
        assert "internal notes" not in done["answer"]
        assert done["had_reasoning"] is True

    def test_had_reasoning_is_false_with_no_reasoning_at_all(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)

        llm = ScriptedLLM(
            stream_deltas=[
                StreamDelta(text="Rainfall gauges "),
                StreamDelta(text="feed the model [1]."),
            ]
        )
        with use_composition_root(root_with(embedder=embedder, llm=llm)):
            events = _parse_sse(ask_stream(client_for(reader), FLOOD_QUESTION))

        assert not any(name == "reasoning_delta" for name, _ in events)
        assert dict(events)["done"]["had_reasoning"] is False

    def test_a_stored_turn_records_had_reasoning_without_the_reasoning_text(
        self, embedder, space, client_for
    ):
        from apps.ai.models import Conversation, Turn

        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        conversation = Conversation.objects.create(user=reader)

        llm = ScriptedLLM(
            stream_deltas=[
                StreamDelta(reasoning="a secret train of thought"),
                StreamDelta(text="Rainfall gauges feed the model [1]."),
            ]
        )
        with use_composition_root(root_with(embedder=embedder, llm=llm)):
            _parse_sse(
                ask_stream(
                    client_for(reader), FLOOD_QUESTION, conversation_id=conversation.pk
                )
            )

        turn = Turn.objects.get(conversation=conversation)
        assert turn.had_reasoning is True
        assert "secret train of thought" not in turn.answer


class VisibilityTests:
    def test_a_passage_from_an_unreadable_record_is_never_on_the_wire(
        self, embedder, space, client_for
    ):
        author = make_user("author@cit.edu")
        stranger = make_user("stranger@cit.edu")
        make_record(title="Unpublished Flood Draft", text=FLOOD_TEXT, owner=author,
                    status=PipelineStatus.DRAFT, embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder)):
            response = ask_stream(client_for(stranger), FLOOD_QUESTION)
            content = b"".join(response.streaming_content)

        assert b"rainfall gauge" not in content
