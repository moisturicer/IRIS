"""The extraction task end to end, against the in-memory extractor (IR-107).

The seam is the ``StructuredExtractor`` port, so none of this needs a Docling
container: ``InMemoryExtractor`` returning a canned document exercises
everything the task actually does — the status transitions, the two derived
outputs, the error path and the retry.

It is a real implementation of the port, not a ``MagicMock``. A mock breaks
when the call sequence changes, which is not a defect; a fake breaks when the
*contract* changes, which is.

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
    ExtractionError,
    ExtractorUnavailable,
    InMemoryExtractor,
    Provenance,
    extraction_hash,
    use_extractor,
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
            bboxes=(BoundingBox(page=12, left=72.0, top=310.5, right=540.0, bottom=352.1),),
        ),
        DocumentElement(kind=TABLE_ROW, text="| Tilapia | 412 g |", page=13),
    ),
    page_sizes={12: (612.0, 792.0)},
)


@pytest.fixture(autouse=True)
def queued_chunkings(monkeypatch):
    """Every extraction id handed to the chunking task, in place of a real
    ``delay`` -- which blocks on a broker this test process has no reason to
    need. Autouse, because a test that forgot it would hang rather than fail.

    Patched *below* the kind guard (IR-239), so the guard itself still runs:
    these tests exercise a supplementary upload, and what they assert is that
    such a row is not chunked -- a fact about its ``kind``, not about which
    task read it."""
    calls = []
    monkeypatch.setattr(tasks, "_queue_chunk_extraction", lambda extraction_id, revision=None: calls.append(extraction_id))
    return calls


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


def _run(extractor, upload_id):
    with use_extractor(extractor):
        return tasks.extract_pdf_text.apply(args=[upload_id])


# ---------------------------------------------------------------------------
# Success
# ---------------------------------------------------------------------------


def test_a_successful_extraction_reaches_done(monkeypatch, upload, extraction):
    _run(InMemoryExtractor(DOCUMENT), upload.id)

    extraction.refresh_from_db()
    assert extraction.status == "done"
    assert extraction.completed_at is not None
    assert extraction.error == ""


def test_the_flat_text_is_populated_so_full_text_search_is_unaffected(
    monkeypatch, upload, extraction
):
    _run(InMemoryExtractor(DOCUMENT), upload.id)

    extraction.refresh_from_db()
    assert "Samples were collected weekly" in extraction.extracted_text
    assert "3 Methodology" in extraction.extracted_text


def test_the_structure_is_persisted_not_only_the_flat_text(monkeypatch, upload, extraction):
    """The whole point of ADR-016: flattening at extraction is irreversible,
    so the structure the chunker needs has to be stored here or nowhere."""
    _run(InMemoryExtractor(DOCUMENT), upload.id)

    extraction.refresh_from_db()
    assert extraction.structure
    assert extraction.as_normalized_document() == DOCUMENT


def test_the_persisted_structure_keeps_the_regions_a_citation_anchors_to(
    monkeypatch, upload, extraction
):
    _run(InMemoryExtractor(DOCUMENT), upload.id)

    extraction.refresh_from_db()
    paragraph = extraction.as_normalized_document().elements[1]
    assert paragraph.page == 12
    assert paragraph.bbox == BoundingBox(
        page=12, left=72.0, top=310.5, right=540.0, bottom=352.1
    )


def test_the_row_records_which_extractor_version_and_options_produced_it(
    monkeypatch, upload, extraction
):
    provenance = Provenance(name="llamaparse", version="2.4.1", options={"tier": "agentic"})

    _run(InMemoryExtractor(DOCUMENT, provenance=provenance), upload.id)

    extraction.refresh_from_db()
    assert (extraction.extractor, extraction.extractor_version, extraction.extractor_options) == (
        "llamaparse", "2.4.1", {"tier": "agentic"}
    )


def test_the_extraction_hash_ties_a_chunk_set_to_this_extraction(
    monkeypatch, upload, extraction
):
    _run(InMemoryExtractor(DOCUMENT), upload.id)

    extraction.refresh_from_db()
    assert extraction.content_hash == extraction_hash(DOCUMENT)


def test_the_task_records_its_celery_id_before_doing_the_work(monkeypatch, upload, extraction):
    _run(InMemoryExtractor(DOCUMENT), upload.id)

    extraction.refresh_from_db()
    assert extraction.celery_task_id


def test_the_pdf_bytes_and_filename_reach_the_extractor(monkeypatch, upload, extraction):
    extractor = InMemoryExtractor(DOCUMENT)

    _run(extractor, upload.id)

    (pdf_bytes, filename) = extractor.calls[0]
    assert pdf_bytes == b"%PDF-1.7 fake bytes"
    assert filename.endswith(".pdf")
    assert "/" not in filename and "\\" not in filename


def test_a_re_extraction_clears_a_previous_error(monkeypatch, upload, extraction):
    extraction.status = "retrying"
    extraction.error = "PDF reading failed. Retry extraction or enter details manually."
    extraction.save(update_fields=["status", "error"])

    _run(InMemoryExtractor(DOCUMENT), upload.id)

    extraction.refresh_from_db()
    assert (extraction.status, extraction.error) == ("done", "")


def test_a_successful_extraction_does_not_queue_chunking(
    monkeypatch, upload, extraction, queued_chunkings
):
    """A supplementary upload (an Ethics Clearance form, a Patent Draft --
    everything ``UploadSlot`` seeds today) must never reach the RAG corpus.

    IR-239 moved the reason: this row is skipped because its ``kind`` says
    supplementary, not because ``extract_pdf_text`` is a task that never
    chunks. The ``extraction`` fixture leaves ``kind`` at its default, which
    is exactly the supplementary case."""
    _run(InMemoryExtractor(DOCUMENT), upload.id)

    assert queued_chunkings == []


# ---------------------------------------------------------------------------
# Failure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error, message",
    [
        (ExtractorUnavailable("Docling-serve unreachable at http://docling:5001"),
         "Reading is temporarily unavailable. Try again later."),
        (ExtractionError("Docling-serve rejected the document (413)"),
         "This PDF can't be read automatically. Enter the details manually."),
    ],
    ids=["unavailable", "rejected"],
)
def test_a_failed_extraction_is_recorded_with_its_reader_message(monkeypatch, upload, extraction, error, message):
    """IR-839 replaced the one message, and the retry of a rejection."""
    result = _run(InMemoryExtractor(error), upload.id)

    extraction.refresh_from_db()
    assert extraction.status == "failed"
    assert extraction.error == message
    assert str(error) not in extraction.error
    assert result.failed()


def test_a_failure_leaves_no_half_written_structure(monkeypatch, upload, extraction):
    _run(InMemoryExtractor(ExtractionError("boom")), upload.id)

    extraction.refresh_from_db()
    assert extraction.structure == {}
    assert extraction.extracted_text == ""
    assert extraction.as_normalized_document() is None


def test_the_task_retries_three_times_before_giving_up(monkeypatch, upload, extraction):
    """Enough to cover a container restart; not so many that a genuinely
    unreadable PDF occupies a worker all afternoon. Counted rather than read
    off ``max_retries``, so this fails if the retry stops being raised."""
    extractor = InMemoryExtractor(ExtractorUnavailable("container is down"))

    _run(extractor, upload.id)

    assert len(extractor.calls) == 4  # the first attempt, then three retries


def test_a_deleted_extraction_row_is_not_an_error(monkeypatch, upload):
    """The upload can be deleted between the task being queued and running."""
    extractor = InMemoryExtractor(DOCUMENT)

    _run(extractor, upload.id)

    assert extractor.calls == []
