"""A Figure's description is indexed and never shown (IR-852, ADR-056 §10).

The description is in the chunk's embedded ``text``, so retrieval finds the
Figure by it. Every reader-facing payload is checked for it, and so is every
prompt: a model that never sees the description cannot repeat it.
"""

import uuid

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse

from apps.ai.composition import use_composition_root
from apps.ai.models import ChunkEmbedding, ChunkSet, DocumentChunk, RecordEmbedding
from apps.ai.overview import PROMPT_VERSION, overview_for
from apps.ai.overview.service import generate_overview
from apps.ai.providers.fakes import ScriptedLLM
from apps.documents.models import DocumentKind, ExtractionFigure, PdfExtraction
from apps.records.models import Record, RecordOwner
from core.enums import PipelineStatus

from .corpus import ask, ask_stream, make_user, root_with, search

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

SENTINEL = "QZXV-DESCRIPTION-ONLY"
CAPTION = "Figure 1: Enrolment by year."
DESCRIPTION = f"A bar chart of enrolment rising every year {SENTINEL}."
QUESTION = "Which figure shows enrolment rising every year?"
PNG = b"\x89PNG figure bytes"


@pytest.fixture(autouse=True)
def suppress_task_publish(monkeypatch):
    monkeypatch.setattr("apps.ai.overview.service._enqueue_overview", lambda *args: None)


def figure_paper(embedder, space, owner):
    revision = uuid.uuid4()
    record = Record.objects.create(
        title="Enrolment Study", abstract="An abstract for the enrolment study.",
        pipeline_status=PipelineStatus.PUBLISHED, manuscript_revision=revision,
    )
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    RecordEmbedding.objects.create(
        record=record, embedding=embedder.embed_documents([f"{record.title}. {QUESTION}"])[0],
        model_name="fake-test",
    )
    chunk_set = ChunkSet.objects.create(
        record=record, extraction_hash="e", strategy_id="s", options={},
        content_hash="c", is_active=True, page_sizes={},
    )
    text = f"Enrolment Study > Results\n\n{CAPTION}\n{DESCRIPTION}"
    chunk = DocumentChunk.objects.create(
        chunk_set=chunk_set, record=record, sequence=0, max_sequence=0,
        text=text, content=CAPTION, context_path=["Enrolment Study", "Results"],
        token_count=20, text_hash="t-figure", source_page=3, element_kinds=["image"],
    )
    ChunkEmbedding.objects.create(chunk=chunk, space=space, embedding=embedder.embed_documents([text])[0])
    extraction = PdfExtraction.objects.create(
        record=record, kind=DocumentKind.MANUSCRIPT, source_revision=revision, status="done",
    )
    figure = ExtractionFigure(
        extraction=extraction, source_revision=revision, name="image_0.png",
        page=3, caption=CAPTION, media_type="image/png", description=DESCRIPTION,
    )
    figure.image.save("figure.png", ContentFile(PNG), save=True)
    return record, figure


def prompts(llm):
    return " ".join(system + user for system, user in llm.calls)


def test_retrieval_finds_the_figure_and_no_answer_citation_or_prompt_carries_its_description(
    embedder, space, client_for,
):
    reader = make_user("reader@cit.edu")
    record, _ = figure_paper(embedder, space, reader)
    llm = ScriptedLLM()

    with use_composition_root(root_with(embedder=embedder, llm=llm)):
        answered = ask(client_for(reader), QUESTION)
        streamed = ask_stream(client_for(reader), QUESTION)
        found = search(client_for(reader), QUESTION)

    citation, = answered.json()["citations"]
    assert (citation["record_id"], citation["text"]) == (record.pk, CAPTION)
    assert [p["text"] for p in found.json()["results"]] == [CAPTION]
    for payload in (answered.content, b"".join(streamed.streaming_content), found.content):
        assert SENTINEL.encode() not in payload
    assert SENTINEL not in prompts(llm)


def test_a_transcript_never_carries_the_description(embedder, space, client_for):
    reader = make_user("reader@cit.edu")
    figure_paper(embedder, space, reader)
    client = client_for(reader)

    with use_composition_root(root_with(embedder=embedder)):
        conversation = client.post(reverse("ai-conversations"), {}, format="json").json()["id"]
        ask(client, QUESTION, conversation_id=conversation)
        transcript = client.get(reverse("ai-conversation-detail", args=[conversation]))

    assert transcript.status_code == 200
    assert transcript.json()["turns"]
    assert SENTINEL.encode() not in transcript.content


def test_an_ai_overview_never_carries_the_description(embedder, space, client_for):
    reader = make_user("reader@cit.edu")
    record, _ = figure_paper(embedder, space, reader)
    llm = ScriptedLLM(reply="The study reports enrolment by year [p3].")
    chunk_set = ChunkSet.objects.get(record=record, is_active=True)

    with use_composition_root(root_with(embedder=embedder, llm=llm)):
        overview_for(record)
        generate_overview(record.pk, chunk_set.pk, chunk_set.content_hash, PROMPT_VERSION)
        shown = client_for(reader).get(reverse("ai-record-overview", args=[record.pk]))

    assert shown.status_code == 200
    assert llm.calls, "the overview was never generated"
    assert SENTINEL not in prompts(llm)
    assert SENTINEL.encode() not in shown.content


def test_the_figure_endpoint_serves_the_image_alone(embedder, space, client_for):
    reader = make_user("reader@cit.edu")
    record, figure = figure_paper(embedder, space, reader)

    response = client_for(reader).get(f"/api/v1/records/{record.pk}/figures/{figure.pk}/")
    detail = client_for(reader).get(reverse("record-detail", args=[record.pk]))

    assert b"".join(response.streaming_content) == PNG
    assert SENTINEL not in str(response.headers)
    assert SENTINEL.encode() not in detail.content
