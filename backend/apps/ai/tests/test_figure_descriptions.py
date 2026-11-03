"""Figures are described for retrieval only (IR-852, ADR-056 §10)."""

import uuid

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.ai import tasks as ai_tasks
from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.extraction.tests.llamaparse_fixtures import result_with
from apps.ai.figure_descriptions import describe_figures
from apps.ai.models import DocumentChunk
from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.providers.vision import ImageDescribingLLM
from apps.documents.models import DocumentKind, ExtractionFigure, PdfExtraction
from apps.records.models import Record, RecordType

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

CAPTION = "Figure 1: Enrolment by year."
DESCRIPTION = "A bar chart rising from 120 in 2019 to 410 in 2024."


class Describer(ScriptedLLM, ImageDescribingLLM):
    def __init__(self, reply=DESCRIPTION):
        super().__init__()
        self.reply = reply
        self.images = []

    def describe_image(self, system, user, image, media_type):
        self.images.append((image, media_type))
        return self.reply


def box(x):
    return [{"x": x, "y": 300, "w": 200, "h": 100}]


def manuscript():
    revision = uuid.uuid4()
    record = Record.objects.create(
        title="A thesis", record_type=RecordType.objects.get_or_create(name="Thesis")[0],
        abstract_file=SimpleUploadedFile("thesis.pdf", b"%PDF-1.7"), manuscript_revision=revision,
    )
    extraction = PdfExtraction.objects.create(
        record=record, kind=DocumentKind.MANUSCRIPT, source_revision=revision,
        source_file=record.abstract_file.name, status="done", extractor="llamaparse",
        content_hash="hash-1",
        raw_result=result_with([
            {"type": "heading", "level": 1, "value": "Results"},
            {"type": "text", "value": "Enrolment grew every year of the study."},
            {"type": "image", "url": "image_0.png", "caption": CAPTION, "bbox": box(72)},
            {"type": "image", "url": "image_1.png", "bbox": box(300)},
        ]),
    )
    for sequence, name in enumerate(("image_0.png", "image_1.png"), start=1):
        figure = ExtractionFigure(
            extraction=extraction, source_revision=revision, name=name, page=1,
            caption=CAPTION if sequence == 1 else "", media_type="image/png",
        )
        figure.image.save(name, ContentFile(b"\x89PNG " + name.encode()), save=True)
    return record, extraction


def chunk(record, *, force=False):
    return ai_tasks.chunk_extraction.apply(
        args=[record.manuscript_extraction.pk, str(record.manuscript_revision)], kwargs={"force": force},
    ).get()


@pytest.fixture(autouse=True)
def no_followups(monkeypatch):
    monkeypatch.setattr(ai_tasks.embed_chunk_set, "delay", lambda *a, **k: None)
    monkeypatch.setattr("apps.ai.overview.service.queue_overview_for_chunk_set", lambda *a, **k: None)
    monkeypatch.setattr("apps.ai.figure_descriptions._queue_rechunk", lambda *a, **k: None)


def root(describer=None, permits=lambda record: True):
    return use_composition_root(CompositionRoot(llm=describer, permits=permits))


def figure_chunks(record):
    return list(DocumentChunk.objects.filter(
        record=record, chunk_set__is_active=True, element_kinds__contains=["image"],
    ).order_by("sequence"))


def test_each_figure_gets_one_description_appended_to_text_and_never_to_content():
    record, extraction = manuscript()
    describer = Describer()

    with root(describer):
        describe_figures(extraction.pk, str(record.manuscript_revision))
        describe_figures(extraction.pk, str(record.manuscript_revision))
    chunk(record, force=True)

    assert [image for image, _ in describer.images] == [b"\x89PNG image_0.png", b"\x89PNG image_1.png"]
    captioned, uncaptioned = figure_chunks(record)
    assert DESCRIPTION in captioned.text and CAPTION in captioned.text
    assert captioned.content == CAPTION
    # Uncaptioned Figures are kept and indexed: the description makes them findable.
    assert DESCRIPTION in uncaptioned.text
    assert DESCRIPTION not in uncaptioned.content


def test_with_no_describe_figure_profile_there_are_no_descriptions_and_no_failure(settings):
    settings.LLM_DESCRIBE_FIGURE_MODEL = ""
    record, extraction = manuscript()

    with use_composition_root(CompositionRoot(permits=lambda record: True)):
        describe_figures(extraction.pk, str(record.manuscript_revision))

    assert not ExtractionFigure.objects.exclude(description="").exists()


def test_a_record_the_gate_refuses_is_never_described():
    record, extraction = manuscript()
    describer = Describer()

    with root(describer, permits=lambda record: False):
        describe_figures(extraction.pk, str(record.manuscript_revision))

    assert describer.images == []
    assert not ExtractionFigure.objects.exclude(description="").exists()


def test_a_stale_revision_describes_nothing():
    record, extraction = manuscript()
    describer = Describer()

    with root(describer):
        describe_figures(extraction.pk, str(uuid.uuid4()))

    assert describer.images == []


def test_a_failed_description_is_skipped_and_the_rest_are_written():
    from apps.ai.providers.openai_compatible import LLMUnavailable

    record, extraction = manuscript()

    class Flaky(Describer):
        def describe_image(self, system, user, image, media_type):
            if image.endswith(b"image_0.png"):
                raise LLMUnavailable("down")
            return super().describe_image(system, user, image, media_type)

    with root(Flaky()):
        describe_figures(extraction.pk, str(record.manuscript_revision))

    assert list(ExtractionFigure.objects.order_by("pk").values_list("description", flat=True)) == [
        "", DESCRIPTION,
    ]


def test_describing_re_embeds_only_the_figure_chunks():
    record, extraction = manuscript()
    first = chunk(record)

    with root(Describer()):
        describe_figures(extraction.pk, str(record.manuscript_revision))
    second = chunk(record, force=True)

    assert first["to_embed"] == first["chunk_count"]
    assert second["chunk_count"] == first["chunk_count"]
    assert second["to_embed"] == 2
    assert second["reused"] == first["chunk_count"] - 2
