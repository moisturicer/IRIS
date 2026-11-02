"""The manuscript extraction task end to end, against the in-memory extractor (IR-195).

Mirrors ``test_extraction_task.py``'s approach for ``extract_pdf_text``, but
for ``extract_manuscript_text``: same fake-port pattern, same status
lifecycle assertions. The one behaviour that must differ, and the reason
this ticket exists, is the last one below -- a successful run here *does*
queue chunking, where a supplementary upload's extraction never does.

Needs a database because ``PdfExtraction`` is the thing under test.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.ai.chunking.document import HEADING, PARAGRAPH, DocumentElement, NormalizedDocument
from apps.ai.extraction import (
    ExtractionError,
    ExtractorUnavailable,
    InMemoryExtractor,
    extraction_hash,
    use_extractor,
)
from apps.documents import tasks
from apps.documents.models import DocumentKind, PdfExtraction
from apps.records.models import Record, RecordType

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


DOCUMENT = NormalizedDocument(
    title="Optimization of Tilapia Feed Conversion",
    elements=(
        DocumentElement(kind=HEADING, text="3 Methodology", level=2, page=12),
        DocumentElement(kind=PARAGRAPH, text="Samples were collected weekly.", page=12),
    ),
    page_sizes={12: (612.0, 792.0)},
)


@pytest.fixture(autouse=True)
def queued_chunkings(monkeypatch):
    """Patched below the kind guard (IR-239), so the guard still runs and
    what these tests assert is a consequence of the row's ``kind``."""
    calls = []
    monkeypatch.setattr(tasks, "_queue_chunk_extraction", lambda extraction_id, revision=None: calls.append(extraction_id))
    return calls


@pytest.fixture
def record(db):
    record_type = RecordType.objects.create(name="Thesis")
    return Record.objects.create(
        title="A thesis",
        record_type=record_type,
        abstract_file=SimpleUploadedFile("thesis.pdf", b"%PDF-1.7 fake bytes"),
    )


@pytest.fixture
def extraction(record):
    # kind is stated, not implied by the record FK (IR-239) -- this fixture
    # stands in for what RecordViewSet writes, and that is what it writes.
    return PdfExtraction.objects.create(record=record, kind=DocumentKind.MANUSCRIPT)


def _run(extractor, record_id):
    with use_extractor(extractor):
        return tasks.extract_manuscript_text.apply(args=[record_id])


def test_a_successful_extraction_reaches_done(monkeypatch, record, extraction):
    _run(InMemoryExtractor(DOCUMENT), record.id)

    extraction.refresh_from_db()
    assert extraction.status == "done"
    assert extraction.completed_at is not None
    assert extraction.error == ""


def test_the_structure_is_persisted(monkeypatch, record, extraction):
    _run(InMemoryExtractor(DOCUMENT), record.id)

    extraction.refresh_from_db()
    assert extraction.structure
    assert extraction.as_normalized_document() == DOCUMENT


def test_the_extraction_hash_ties_a_chunk_set_to_this_extraction(monkeypatch, record, extraction):
    _run(InMemoryExtractor(DOCUMENT), record.id)

    extraction.refresh_from_db()
    assert extraction.content_hash == extraction_hash(DOCUMENT)


def test_resolved_record_id_reads_through_the_record_fk(record, extraction):
    """The chunker's one entry point into 'which record is this' -- must
    resolve for a manuscript-keyed row exactly as it does for an upload-keyed
    one."""
    assert extraction.resolved_record_id == record.id


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
def test_a_failed_extraction_is_recorded_with_its_reader_message(monkeypatch, record, extraction, error, message):
    """IR-839 replaced the one message, and the retry of a rejection."""
    result = _run(InMemoryExtractor(error), record.id)

    extraction.refresh_from_db()
    assert extraction.status == "failed"
    assert extraction.error == message
    assert str(error) not in extraction.error
    assert result.failed()


def test_a_deleted_extraction_row_is_not_an_error(monkeypatch, record):
    """The manuscript can be removed between the task being queued and running."""
    extractor = InMemoryExtractor(DOCUMENT)

    _run(extractor, record.id)

    assert extractor.calls == []


def test_a_successful_extraction_queues_chunking(
    monkeypatch, record, extraction, queued_chunkings
):
    """The manuscript is exactly what ADR-013's 2026-09-08 amendment says
    belongs in the RAG corpus. Queued by extraction id (IR-239), since that
    is the row the chunker reads."""
    _run(InMemoryExtractor(DOCUMENT), record.id)

    assert queued_chunkings == [extraction.id]


def test_a_failed_extraction_does_not_queue_chunking(
    monkeypatch, record, extraction, queued_chunkings
):
    _run(InMemoryExtractor(ExtractionError("boom")), record.id)

    assert queued_chunkings == []
