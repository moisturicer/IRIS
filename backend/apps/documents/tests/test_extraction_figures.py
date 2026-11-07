"""A Manuscript's Figures are stored when it is read (IR-845, ADR-056 §9).

IR-849's recordings hold no image crop (their synthetic PDFs draw vector
shapes), so the Figures here are real PNG bytes in the shape IR-841's
adapter returns.
"""

import base64
import uuid

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.ai.chunking.document import PARAGRAPH, DocumentElement, NormalizedDocument
from apps.ai.extraction import ExtractedDocument, FigureImage, Provenance, use_extractor
from apps.documents import tasks
from apps.documents.models import DocumentKind, PdfExtraction
from apps.documents.sources import reset_manuscript
from apps.records.models import Record, RecordType

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

#: A 1x1 PNG.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
BOX = {"x": 72.0, "y": 300.0, "w": 200.0, "h": 100.0}


class FigureExtractor:
    timeout_seconds = 60
    # Storage only; gating and admission are IR-850's tests.
    leaves_campus = False

    def __init__(self, *figures):
        self.figures = figures

    def extract(self, pdf_bytes, *, filename):
        return ExtractedDocument(
            document=NormalizedDocument(
                title="", elements=(DocumentElement(kind=PARAGRAPH, text="A passage.", page=1),),
                page_sizes={1: (612.0, 792.0)},
            ),
            provenance=Provenance(name="llamaparse", version="2026-09-28"),
            figures=self.figures,
        )


@pytest.fixture(autouse=True)
def no_chunking(monkeypatch):
    monkeypatch.setattr(tasks, "_queue_chunk_extraction", lambda *args, **kwargs: None)


def _manuscript():
    revision = uuid.uuid4()
    record = Record.objects.create(
        title="A thesis", record_type=RecordType.objects.get_or_create(name="Thesis")[0],
        abstract_file=SimpleUploadedFile("thesis.pdf", b"%PDF-1.7 fake bytes"),
        manuscript_revision=revision,
    )
    extraction = PdfExtraction.objects.create(
        record=record, kind=DocumentKind.MANUSCRIPT, source_revision=revision,
        source_file=record.abstract_file.name,
    )
    return record, extraction


def _read(record, extractor):
    with use_extractor(extractor):
        tasks.extract_manuscript_text.apply(args=[record.id, str(record.manuscript_revision)])


def test_a_figure_is_stored_with_its_page_box_caption_and_revision():
    record, extraction = _manuscript()

    _read(record, FigureExtractor(
        FigureImage(page=2, bbox=BOX, media_type="image/png", data=PNG, caption="Figure 1: A rectangle."),
    ))

    (figure,) = extraction.figures.all()
    assert (figure.page, figure.bbox, figure.caption) == (2, BOX, "Figure 1: A rectangle.")
    assert figure.media_type == "image/png"
    assert figure.source_revision == record.manuscript_revision
    with figure.image.open("rb") as stored:
        assert stored.read() == PNG


def test_an_uncaptioned_figure_is_kept():
    record, extraction = _manuscript()

    _read(record, FigureExtractor(FigureImage(page=1, bbox=BOX, media_type="image/png", data=PNG)))

    (figure,) = extraction.figures.all()
    assert figure.caption == ""


def test_bytes_that_are_not_an_image_are_never_stored():
    """The media type is the vendor's word. A file that is not the image it
    claims could be served as something a browser runs, so it is dropped."""
    record, extraction = _manuscript()

    _read(record, FigureExtractor(
        FigureImage(page=1, bbox=BOX, media_type="image/png", data=b"<html><script>alert(1)</script>"),
        FigureImage(page=1, bbox=BOX, media_type="text/html", data=PNG),
        FigureImage(page=2, bbox=BOX, media_type="image/png", data=PNG),
    ))

    assert [figure.page for figure in extraction.figures.all()] == [2]
    extraction.refresh_from_db()
    assert extraction.status == "done"


# -- clean-up: an Extraction's images go when it is superseded ----------------


def _stored_names(extraction):
    return [figure.image.name for figure in extraction.figures.all()]


def _exists(name):
    return default_storage.exists(name)


def test_a_new_read_replaces_the_figures_and_removes_the_old_images(django_capture_on_commit_callbacks):
    record, extraction = _manuscript()
    _read(record, FigureExtractor(FigureImage(page=1, bbox=BOX, media_type="image/png", data=PNG)))
    (old,) = _stored_names(extraction)
    PdfExtraction.objects.filter(pk=extraction.pk).update(status="queued")

    with django_capture_on_commit_callbacks(execute=True):
        _read(record, FigureExtractor(FigureImage(page=3, bbox=BOX, media_type="image/png", data=PNG)))

    assert [figure.page for figure in extraction.figures.all()] == [3]
    assert not _exists(old)


def test_a_new_manuscript_removes_the_old_revisions_figures(django_capture_on_commit_callbacks, monkeypatch):
    monkeypatch.setattr(tasks.extract_manuscript_text, "delay", lambda *args, **kwargs: None)
    record, extraction = _manuscript()
    _read(record, FigureExtractor(FigureImage(page=1, bbox=BOX, media_type="image/png", data=PNG)))
    (old,) = _stored_names(extraction)

    record.abstract_file = SimpleUploadedFile("revised.pdf", b"%PDF-1.7 revised bytes")
    record.manuscript_revision = uuid.uuid4()
    record.save()
    with django_capture_on_commit_callbacks(execute=True):
        reset_manuscript(record)

    assert not extraction.figures.exists()
    assert not _exists(old)


def test_a_revision_awaiting_submission_keeps_the_submitted_figures(django_capture_on_commit_callbacks):
    """Readers are still served the submitted Manuscript, and its chunks are
    kept, until the owner submits the revision (IR-273). So are its Figures."""
    record, extraction = _manuscript()
    submitted = record.manuscript_revision
    _read(record, FigureExtractor(FigureImage(page=1, bbox=BOX, media_type="image/png", data=PNG)))
    (kept,) = _stored_names(extraction)

    record.abstract_file = SimpleUploadedFile("revised.pdf", b"%PDF-1.7 revised bytes")
    record.manuscript_revision = uuid.uuid4()
    record.save()
    with django_capture_on_commit_callbacks(execute=True):
        reset_manuscript(record, defer=True)

    (figure,) = extraction.figures.all()
    assert figure.source_revision == submitted
    assert _exists(kept)


def test_removing_the_manuscript_removes_its_images(django_capture_on_commit_callbacks):
    record, extraction = _manuscript()
    _read(record, FigureExtractor(FigureImage(page=1, bbox=BOX, media_type="image/png", data=PNG)))
    (old,) = _stored_names(extraction)

    record.abstract_file = None
    record.save()
    with django_capture_on_commit_callbacks(execute=True):
        reset_manuscript(record)

    assert not _exists(old)
