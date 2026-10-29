"""IR-616: readable evidence is present; hidden evidence never crosses HTTP."""
import json

import pytest
from django.urls import reverse

from apps.ai.composition import use_composition_root
from apps.ai.models import Conversation
from apps.records.models import Record
from core.enums import PipelineStatus

from .corpus import FLOOD_QUESTION, FLOOD_TEXT, make_record, make_user, root_with

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def payload(response):
    if not response.streaming:
        return response.json()
    events = []
    for block in b"".join(response.streaming_content).decode().split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


@pytest.mark.parametrize("role", ["Student", "Adviser", None])
@pytest.mark.parametrize("route", ["ai-ask", "ai-ask-stream", "ai-search"])
def test_live_evidence_excludes_hidden_records(role, route, embedder, space, client_for, settings):
    settings.AI_DURABLE_ASK = False
    settings.AI_RESEARCH_LANE = "off"
    reader = make_user("matrix-reader@cit.edu", role_name=role)
    owner = make_user("matrix-private-owner@cit.edu")
    public = make_record(title="Readable matrix paper", text=FLOOD_TEXT, embedder=embedder, space=space)
    hidden = make_record(title="PRIVATE_MATRIX_CANARY", text=FLOOD_TEXT+" SECRET_MATRIX_TEXT",
                         status=PipelineStatus.DRAFT, owner=owner, embedder=embedder, space=space)
    key = "query" if route == "ai-search" else "question"
    with use_composition_root(root_with(embedder=embedder)):
        response = client_for(reader).post(reverse(route), {key: FLOOD_QUESTION}, format="json")
        assert response.status_code == 200
        body = payload(response)
    wire = json.dumps(body)
    assert public.title in wire  # Empty results would make the negative assertion meaningless.
    assert hidden.title not in wire
    assert "SECRET_MATRIX_TEXT" not in wire
    responses = body if isinstance(body, list) else [body]
    for part in responses:
        for result in part.get("results", []):
            assert Record.objects.visible_to(reader).filter(pk=result["record_id"]).exists()
        for citation in part.get("citations", []):
            assert Record.objects.visible_to(reader).filter(pk=citation["record_id"]).exists()
        for source in part.get("sources", []):
            assert Record.objects.visible_to(reader).filter(pk=source["id"]).exists()


@pytest.mark.parametrize("route", ["ai-ask", "ai-ask-stream"])
def test_another_readers_conversation_is_hidden_before_answering(route, client_for):
    owner = make_user("matrix-conversation-owner@cit.edu")
    stranger = make_user("matrix-conversation-stranger@cit.edu")
    conversation = Conversation.objects.create(user=owner, title="PRIVATE_CONVERSATION_CANARY")
    client = client_for(stranger)
    responses = [client.post(reverse(route), {"question": FLOOD_QUESTION, "conversation_id": pk}, format="json")
                 for pk in (conversation.pk, 2000000000)]
    assert [response.status_code for response in responses] == [404, 404]
    assert responses[0].content == responses[1].content


def test_reopened_transcript_drops_citations_whose_source_is_now_hidden(embedder, space, client_for):
    reader = make_user("matrix-history-reader@cit.edu")
    public = make_record(title="Revocable matrix paper", text=FLOOD_TEXT, embedder=embedder, space=space)
    client = client_for(reader)
    conversation = Conversation.objects.create(user=reader)
    with use_composition_root(root_with(embedder=embedder)):
        answered = client.post(reverse("ai-ask"), {"question": FLOOD_QUESTION,
                               "conversation_id": conversation.pk}, format="json")
    assert answered.status_code == 200
    assert answered.json()["citations"]
    url = reverse("ai-conversation-detail", args=[conversation.pk])
    assert client.get(url).json()["turns"]
    Record.objects.filter(pk=public.pk).update(pipeline_status=PipelineStatus.DRAFT)
    reopened = client.get(url)
    assert reopened.status_code == 200
    # ADR-019 re-resolves citation pointers; the reader retains their question/answer.
    assert len(reopened.json()["turns"]) == 1
    assert reopened.json()["turns"][0]["citations"] == []
    assert public.title not in json.dumps(reopened.json())


@pytest.mark.parametrize("after", [0, 1])
@pytest.mark.parametrize("protocol", [None, "public-1"])
def test_queued_replay_rechecks_citations_cards_and_candidates(after, protocol, client_for):
    from datetime import timedelta
    from django.utils import timezone
    from apps.ai.models import AskRun, AskRunEvent, Turn

    reader = make_user("matrix-replay-reader@cit.edu")
    public = Record.objects.create(title="Readable replay source", pipeline_status=PipelineStatus.PUBLISHED)
    hidden = Record.objects.create(title="PRIVATE_REPLAY_CANARY", pipeline_status=PipelineStatus.DRAFT)
    conversation = Conversation.objects.create(user=reader)
    turn = Turn.objects.create(conversation=conversation, question="Question", answer="Answer", state="generated")
    run = AskRun.objects.create(user=reader, conversation=conversation, state="succeeded", turn=turn,
                               deadline_at=timezone.now()+timedelta(minutes=1), last_sequence=4)
    AskRunEvent.objects.create(run=run, sequence=1, name="started", data={})
    AskRunEvent.objects.create(run=run, sequence=2, name="citations_resolved", data={"citations": [
        {"record_id": r.pk, "record_title": r.title, "marker": i} for i, r in enumerate([public, hidden], 1)]})
    AskRunEvent.objects.create(run=run, sequence=3, name="candidates_selected", data={"candidates": [
        {"record_id": r.pk, "title": r.title} for r in [public, hidden]]})
    AskRunEvent.objects.create(run=run, sequence=4, name="done", data={"turn_id": turn.pk, "sources": [
        {"id": r.pk, "title": r.title} for r in [public, hidden]]})
    query = {"after": after}
    if protocol is not None:
        query["protocol"] = protocol
    response = client_for(reader).get(reverse("ai-ask-run-stream", args=[run.pk]), query)
    assert response.status_code == 200
    body = payload(response)
    wire = json.dumps(body)
    assert public.title in wire
    assert hidden.title not in wire
    for event in body:
        for key in ("citations", "candidates"):
            for record in event.get(key, []):
                assert record["record_id"] == public.pk
        for source in event.get("sources", []):
            assert source["id"] == public.pk
