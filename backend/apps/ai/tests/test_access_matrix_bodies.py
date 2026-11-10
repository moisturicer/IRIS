"""IR-616: readable evidence is present; hidden evidence never crosses HTTP."""
import json

import pytest
from django.urls import reverse

from apps.ai.models import Conversation, Turn, TurnCitation
from apps.records.models import Record
from core.enums import PipelineStatus

from .corpus import FLOOD_QUESTION, FLOOD_TEXT, make_record, make_user

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


def test_reopened_transcript_drops_citations_whose_source_is_now_hidden(embedder, space, client_for):
    reader = make_user("matrix-history-reader@cit.edu")
    public = make_record(title="Revocable matrix paper", text=FLOOD_TEXT, embedder=embedder, space=space)
    client = client_for(reader)
    conversation = Conversation.objects.create(user=reader)
    # Written as Django's answer path wrote it before IR-957 retired that path.
    turn = Turn.objects.create(conversation=conversation, question=FLOOD_QUESTION,
                               answer="Rainfall gauges [1].", state="generated")
    chunk = public.document_chunks.get()
    TurnCitation.objects.create(turn=turn, marker=1, record=public, chunk=chunk, page=chunk.source_page)
    url = reverse("ai-conversation-detail", args=[conversation.pk])
    assert client.get(url).json()["turns"][0]["citations"]
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
