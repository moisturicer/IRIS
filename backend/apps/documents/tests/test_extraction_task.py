"""The extraction task end to end, against a fake extractor (IR-107).

The seam is the ``StructuredExtractor`` port, so none of this needs a Docling
container: a fake returning a canned document exercises everything the task
actually does — the status transitions, the two derived outputs, the error
path and the retry.

The fakes below are real implementations of the port, not ``MagicMock``s.
That matters: a mock breaks when the call sequence changes, which is not a
defect; a fake breaks when the *contract* changes, which is.

Needs a database because ``PdfExtraction`` is the thing under test.
``db_required`` skips these cleanly where no Postgres is reachable rather
than reporting a missing database as a pass.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.ai.chunking.document import (
    HEADING,
    PARAGRAPH,
    TABLE_ROW,
    BoundingBox,
    DocumentElement,
    NormalizedDocument,
)
from apps.ai.extraction import (
    ExtractedDocument,
    ExtractionError,
    ExtractorUnavailable,
    extraction_hash,
)
from apps.documents import tasks
from apps.documents.models import PdfExtraction, RecordUpload, UploadSlot
from apps.records.models import Record, RecordType

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


DOCUMENT = NormalizedDocument(
    title="Optimization of Tilapia Feed Conversion",
    elements=(
        DocumentElement(kind=HEADING, text="3 Methodology", level=2, page=12),
        DocumentElement(
            kind=PARAGRAPH,
            text="Samples were collected weekly from twelve ponds.",
            page=12,
            bbox=BoundingBox(page=12, left=72.0, top=310.5, right=540.0, bottom=352.1),
        ),
        DocumentElement(kind=TABLE_ROW, text="| Tilapia | 412 g |", page=13),
    ),
    page_sizes={12: (612.0, 792.0)},
)


class FakeExtractor:
    """Returns a canned document. A real implementation of the port."""

    def __init__(self, document=DOCUMENT, name="fake"):
        self._document = document
        self._name = name
        self.calls = []

    def extract(self, pdf_bytes, *, filename):
        self.calls.append((pdf_bytes, filename))
        return ExtractedDocument(document=self._document, extractor=self._name)


class FailingExtractor:
    """Raises whatever it was given. Also a real implementation."""

    def __init__(self, error):
        self._error = error
        self.calls = 0

    def extract(self, pdf_bytes, *, filename):
        self.calls += 1
        raise self._error


@pytest.fixture
def upload(db):
    record_type = RecordType.objects.create(name="Thesis")
    record = Record.objects.create(title="A thesis", record_type=record_type)
    slot = UploadSlot.objects.create(name="Manuscript", record_type=record_type)
    return RecordUpload.objects.create(
        record=record,
        slot=slot,
        file=SimpleUploadedFile("thesis.pdf", b"%PDF-1.7 fake bytes"),
    )


@pytest.fixture
def extraction(upload):
    return PdfExtraction.objects.create(upload=upload)


def _run(monkeypatch, extractor, upload_id):
    monkeypatch.setattr(tasks, "_build_extractor", lambda: extractor)
    return tasks.extract_pdf_text.apply(args=[upload_id])


# ---------------------------------------------------------------------------
# Success
# ---------------------------------------------------------------------------


def test_a_successful_extraction_reaches_done(monkeypatch, upload, extraction):
    _run(monkeypatch, FakeExtractor(), upload.id)

    extraction.refresh_from_db()
    assert extraction.status == "done"
    assert extraction.completed_at is not None
    assert extraction.error == ""


def test_the_flat_text_is_populated_so_full_text_search_is_unaffected(
    monkeypatch, upload, extraction
):
    _run(monkeypatch, FakeExtractor(), upload.id)

    extraction.refresh_from_db()
    assert "Samples were collected weekly" in extraction.extracted_text
    assert "3 Methodology" in extraction.extracted_text


def test_the_structure_is_persisted_not_only_the_flat_text(monkeypatch, upload, extraction):
    """The whole point of ADR-016: flattening at extraction is irreversible,
    so the structure the chunker needs has to be stored here or nowhere."""
    _run(monkeypatch, FakeExtractor(), upload.id)

    extraction.refresh_from_db()
    assert extraction.structure
    assert extraction.as_normalized_document() == DOCUMENT


def test_the_persisted_structure_keeps_the_regions_a_citation_anchors_to(
    monkeypatch, upload, extraction
):
    _run(monkeypatch, FakeExtractor(), upload.id)

    extraction.refresh_from_db()
    paragraph = extraction.as_normalized_document().elements[1]
    assert paragraph.page == 12
    assert paragraph.bbox == BoundingBox(
        page=12, left=72.0, top=310.5, right=540.0, bottom=352.1
    )


def test_the_row_records_which_extractor_produced_the_result(monkeypatch, upload, extraction):
    _run(monkeypatch, FakeExtractor(name="docling"), upload.id)

    extraction.refresh_from_db()
    assert extraction.extractor == "docling"


def test_the_extraction_hash_ties_a_chunk_set_to_this_extraction(
    monkeypatch, upload, extraction
):
    _run(monkeypatch, FakeExtractor(), upload.id)

    extraction.refresh_from_db()
    assert extraction.content_hash == extraction_hash(DOCUMENT)


def test_the_task_records_its_celery_id_before_doing_the_work(monkeypatch, upload, extraction):
    _run(monkeypatch, FakeExtractor(), upload.id)

    extraction.refresh_from_db()
    assert extraction.celery_task_id


def test_the_pdf_bytes_and_filename_reach_the_extractor(monkeypatch, upload, extraction):
    extractor = FakeExtractor()

    _run(monkeypatch, extractor, upload.id)

    (pdf_bytes, filename) = extractor.calls[0]
    assert pdf_bytes == b"%PDF-1.7 fake bytes"
    assert filename.endswith(".pdf")
    assert "/" not in filename and "\\" not in filename


def test_a_re_extraction_clears_a_previous_error(monkeypatch, upload, extraction):
    extraction.status = "failed"
    extraction.error = "Docling-serve unreachable"
    extraction.save(update_fields=["status", "error"])

    _run(monkeypatch, FakeExtractor(), upload.id)

    extraction.refresh_from_db()
    assert (extraction.status, extraction.error) == ("done", "")


# ---------------------------------------------------------------------------
# Failure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        ExtractorUnavailable("Docling-serve unreachable at http://docling:5001"),
        ExtractionError("Docling-serve rejected the document (413)"),
    ],
    ids=["unavailable", "rejected"],
)
def test_a_failed_extraction_is_recorded_and_retried(monkeypatch, upload, extraction, error):
    result = _run(monkeypatch, FailingExtractor(error), upload.id)

    extraction.refresh_from_db()
    assert extraction.status == "failed"
    assert str(error) in extraction.error
    assert result.failed()


def test_a_failure_leaves_no_half_written_structure(monkeypatch, upload, extraction):
    _run(monkeypatch, FailingExtractor(ExtractionError("boom")), upload.id)

    extraction.refresh_from_db()
    assert extraction.structure == {}
    assert extraction.extracted_text == ""
    assert extraction.as_normalized_document() is None


def test_the_task_retries_three_times_before_giving_up(monkeypatch, upload, extraction):
    """Enough to cover a container restart; not so many that a genuinely
    unreadable PDF occupies a worker all afternoon. Counted rather than read
    off ``max_retries``, so this fails if the retry stops being raised."""
    extractor = FailingExtractor(ExtractorUnavailable("container is down"))

    _run(monkeypatch, extractor, upload.id)

    assert extractor.calls == 4  # the first attempt, then three retries


def test_a_deleted_extraction_row_is_not_an_error(monkeypatch, upload):
    """The upload can be deleted between the task being queued and running."""
    extractor = FakeExtractor()

    _run(monkeypatch, extractor, upload.id)

    assert extractor.calls == []
