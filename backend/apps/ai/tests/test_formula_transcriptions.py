"""Formulas as exact LaTeX, transcribed from their crops (IR-1102, ADR-067 §Amendment)."""

import json
import uuid

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.ai import tasks as ai_tasks
from apps.ai.chunking.document import BoundingBox, DocumentElement, NormalizedDocument
from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.extraction import document_to_json
from apps.ai.formula_transcriptions import (
    TranscriptionsOwed,
    equation_number,
    read_reply,
    transcribe_formulas,
)
from apps.ai.models import DocumentChunk
from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.providers.vision import ImageDescribingLLM
from apps.documents.models import DocumentKind, ExtractionFormula, PdfExtraction
from apps.records.models import Record, RecordType

LATEX = r"\Gamma(T) = \sum_{n=0}^{N-1} |\langle A | n \rangle|^2 \tag{3}"
DESCRIPTION = "The total weight is the sum of squared overlaps over the first N states."
OCR = "N-1 |A) = >> 2(n)|n). n=0"
PROSE = "The weight of a state is defined below."
REPLY = json.dumps({"latex": LATEX, "description": DESCRIPTION})


class ReadReplyTests:
    def test_latex_and_one_line_description(self):
        assert read_reply(REPLY) == (LATEX, DESCRIPTION)

    def test_a_fenced_reply_with_delimiters_is_unwrapped(self):
        fenced = "```json\n" + json.dumps({"latex": "$$ x^2 $$", "description": "A square.\nMore."}) + "\n```"
        assert read_reply(fenced) == ("x^2", "A square.")

    @pytest.mark.parametrize("reply", [
        "I cannot read this image.",
        json.dumps({"latex": "", "description": "No equation."}),
        json.dumps(["x^2"]),
        json.dumps({"latex": 3}),
    ])
    def test_anything_else_is_no_latex(self, reply):
        assert read_reply(reply) == ("", "")

    def test_the_equation_number_is_read_from_its_tag(self):
        assert equation_number(LATEX) == "3"
        assert equation_number("x^2") == ""


class Transcriber(ScriptedLLM, ImageDescribingLLM):
    def __init__(self, reply=REPLY):
        super().__init__()
        self.reply = reply
        self.images = []

    def describe_image(self, system, user, image, media_type):
        self.images.append(image)
        return self.reply


def manuscript(names=("eq-1",)):
    revision = uuid.uuid4()
    record = Record.objects.create(
        title="A thesis", record_type=RecordType.objects.get_or_create(name="Thesis")[0],
        abstract_file=SimpleUploadedFile("thesis.pdf", b"%PDF-1.7"), manuscript_revision=revision,
    )
    elements = [
        DocumentElement(kind="heading", text="Method", level=1, page=1),
        DocumentElement(kind="text", text=PROSE, page=1),
    ]
    for name in names:
        # Shaped as hi_res's Formula is: a crop, never its OCR text.
        elements.append(DocumentElement(
            kind="image", text="", page=1, source_label="Formula", figure=name,
            bboxes=(BoundingBox(page=1, left=72, top=200, right=300, bottom=230),),
        ))
    elements.append(DocumentElement(kind="text", text="The weight then falls with N.", page=1))
    document = NormalizedDocument(title="A thesis", elements=tuple(elements),
                                  page_sizes={1: (612.0, 792.0)}, structure_is_authoritative=True)
    extraction = PdfExtraction.objects.create(
        record=record, kind=DocumentKind.MANUSCRIPT, source_revision=revision,
        source_file=record.abstract_file.name, status="done", extractor="unstructured",
        content_hash="hash-1", structure=document_to_json(document),
        raw_result={"elements": [{"type": "Formula", "element_id": n, "text": OCR} for n in names]},
    )
    for name in names:
        formula = ExtractionFormula(extraction=extraction, source_revision=revision, name=name, page=1,
                                    bbox={"x": 72, "y": 200, "w": 228, "h": 30})
        formula.image.save("formula.png", ContentFile(b"\x89PNG " + name.encode()), save=True)
    return record, extraction


def root(transcriber=None, permits=lambda record: True):
    return use_composition_root(CompositionRoot(llm=transcriber, permits=permits))


def run(record, extraction):
    return transcribe_formulas(extraction.pk, str(record.manuscript_revision))


def chunk(record):
    ai_tasks.chunk_extraction.apply(
        args=[record.manuscript_extraction.pk, str(record.manuscript_revision)], kwargs={"force": True},
    ).get()
    return list(DocumentChunk.objects.filter(record=record, chunk_set__is_active=True).order_by("sequence"))


@pytest.mark.db_required
@pytest.mark.django_db
class TranscriptionTests:
    @pytest.fixture(autouse=True)
    def no_followups(self, monkeypatch):
        monkeypatch.setattr(ai_tasks.embed_chunk_set, "delay", lambda *a, **k: None)
        monkeypatch.setattr("apps.ai.overview.service.queue_overview_for_chunk_set", lambda *a, **k: None)
        self.rechunks = []
        monkeypatch.setattr("apps.ai.formula_transcriptions._queue_rechunk", lambda *a: self.rechunks.append(a))

    def test_each_formula_is_stored_with_its_latex_description_number_model_and_request(self, settings):
        settings.AI_FORMULA_TEXT_INDEXED = True
        record, extraction = manuscript()
        transcriber = Transcriber()

        with root(transcriber):
            assert run(record, extraction) == 1
            assert run(record, extraction) == 0

        assert transcriber.images == [b"\x89PNG eq-1"]
        stored = ExtractionFormula.objects.get()
        assert (stored.latex, stored.description, stored.equation_number) == (LATEX, DESCRIPTION, "3")
        assert (stored.page, stored.bbox) == (1, {"x": 72, "y": 200, "w": 228, "h": 30})
        assert stored.model == "Transcriber"
        assert stored.request == {"prompt_version": 1, "dpi": 300, "models": ["Transcriber"]}
        assert self.rechunks == [(extraction.pk, str(record.manuscript_revision))]

    def test_an_unavailable_call_leaves_the_crop_and_is_owed(self):
        from apps.ai.providers.openai_compatible import LLMUnavailable

        record, extraction = manuscript()

        class Down(Transcriber):
            def describe_image(self, *args):
                raise LLMUnavailable("down")

        with root(Down()), pytest.raises(TranscriptionsOwed):
            run(record, extraction)

        stored = ExtractionFormula.objects.get()
        assert (stored.latex, stored.transcribed_at) == ("", None)
        with root(Transcriber()):
            assert run(record, extraction) == 1

    def test_a_refused_reply_is_recorded_once_and_never_replaced_by_ocr(self, settings):
        settings.AI_FORMULA_TEXT_INDEXED = True
        record, extraction = manuscript()
        refusing = Transcriber(reply="I can't help with that.")

        with root(refusing):
            run(record, extraction)
            run(record, extraction)

        assert len(refusing.images) == 1
        stored = ExtractionFormula.objects.get()
        assert stored.latex == "" and stored.transcribed_at is not None
        chunks = chunk(record)
        assert all(OCR not in c.text and OCR not in c.content for c in chunks)
        assert any("image" in c.element_kinds for c in chunks)

    def test_a_refused_admission_stops_the_rest(self):
        from apps.ai.admission.errors import AdmissionDenied

        record, extraction = manuscript(names=("eq-1", "eq-2"))

        class Refused(Transcriber):
            def describe_image(self, system, user, image, media_type):
                self.images.append(image)
                raise AdmissionDenied("campaign_exhausted")

        transcriber = Refused()
        with root(transcriber), pytest.raises(TranscriptionsOwed):
            run(record, extraction)

        assert len(transcriber.images) == 1
        assert not ExtractionFormula.objects.exclude(latex="").exists()

    def test_a_record_the_gate_refuses_is_never_sent(self):
        record, extraction = manuscript()
        transcriber = Transcriber()

        with root(transcriber, permits=lambda record: False):
            run(record, extraction)

        assert transcriber.images == []

    def test_with_no_profile_nothing_is_sent(self, settings):
        settings.LLM_TRANSCRIBE_FORMULA_MODEL = ""
        record, extraction = manuscript()

        with use_composition_root(CompositionRoot(permits=lambda record: True)):
            assert run(record, extraction) == 0

        assert ExtractionFormula.objects.get().transcribed_at is None

    def test_a_stale_revision_sends_nothing(self):
        record, extraction = manuscript()
        transcriber = Transcriber()

        with root(transcriber):
            transcribe_formulas(extraction.pk, str(uuid.uuid4()))

        assert transcriber.images == []

    def test_off_the_chunks_are_unchanged_by_a_transcription(self, settings):
        settings.AI_FORMULA_TEXT_INDEXED = False
        record, extraction = manuscript()
        before = [(c.text, c.content) for c in chunk(record)]
        assert before

        with root(Transcriber()):
            run(record, extraction)

        assert [(c.text, c.content) for c in chunk(record)] == before
        assert all(LATEX not in text and DESCRIPTION not in text for text, _ in before)
        assert self.rechunks == []

    def test_on_the_latex_and_description_are_embedded_and_indexed_at_the_formula(self, settings):
        settings.AI_FORMULA_TEXT_INDEXED = True
        record, extraction = manuscript()

        with root(Transcriber()):
            run(record, extraction)
        (formula_chunk,) = [c for c in chunk(record) if "formula" in c.element_kinds]

        assert formula_chunk.text.index(PROSE) < formula_chunk.text.index(LATEX) \
            < formula_chunk.text.index(DESCRIPTION)
        assert f"$$\n{LATEX}\n$$\n{DESCRIPTION}" in formula_chunk.content
        hits = DocumentChunk.objects.filter(pk=formula_chunk.pk, search_vector="overlaps")
        assert hits.exists()
