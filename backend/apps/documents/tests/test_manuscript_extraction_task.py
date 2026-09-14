"""The manuscript extraction task end to end, against a fake extractor (IR-195).

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
    ExtractedDocument,
    ExtractionError,
    ExtractorUnavailable,
    extraction_hash,
)
from apps.documents import tasks
from apps.documents.models import PdfExtraction
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

    def extract(self, pdf_bytes, *, filename):
        raise self._error


@pytest.fixture(autouse=True)
def queued_manuscript_chunkings(monkeypatch):
    calls = []
    monkeypatch.setattr(tasks, "_queue_manuscript_chunking", calls.append)
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
    return PdfExtraction.objects.create(record=record)


def _run(monkeypatch, extractor, record_id):
    monkeypatch.setattr(tasks, "_build_extractor", lambda: extractor)
    return tasks.extract_manuscript_text.apply(args=[record_id])


def test_a_successful_extraction_reaches_done(monkeypatch, record, extraction):
    _run(monkeypatch, FakeExtractor(), record.id)

    extraction.refresh_from_db()
    assert extraction.status == "done"
    assert extraction.completed_at is not None
    assert extraction.error == ""


def test_the_structure_is_persisted(monkeypatch, record, extraction):
    _run(monkeypatch, FakeExtractor(), record.id)

    extraction.refresh_from_db()
    assert extraction.structure
    assert extraction.as_normalized_document() == DOCUMENT


def test_the_extraction_hash_ties_a_chunk_set_to_this_extraction(monkeypatch, record, extraction):
    _run(monkeypatch, FakeExtractor(), record.id)

    extraction.refresh_from_db()
    assert extraction.content_hash == extraction_hash(DOCUMENT)


def test_resolved_record_id_reads_through_the_record_fk(record, extraction):
    """The chunker's one entry point into 'which record is this' -- must
    resolve for a manuscript-keyed row exactly as it does for an upload-keyed
    one."""
    assert extraction.resolved_record_id == record.id


@pytest.mark.parametrize(
    "error",
    [
        ExtractorUnavailable("Docling-serve unreachable at http://docling:5001"),
        ExtractionError("Docling-serve rejected the document (413)"),
    ],
    ids=["unavailable", "rejected"],
)
def test_a_failed_extraction_is_recorded_and_retried(monkeypatch, record, extraction, error):
    result = _run(monkeypatch, FailingExtractor(error), record.id)

    extraction.refresh_from_db()
    assert extraction.status == "failed"
    assert str(error) in extraction.error
    assert result.failed()


def test_a_deleted_extraction_row_is_not_an_error(monkeypatch, record):
    """The manuscript can be removed between the task being queued and running."""
    extractor = FakeExtractor()

    _run(monkeypatch, extractor, record.id)

    assert extractor.calls == []


def test_a_successful_extraction_queues_chunking(
    monkeypatch, record, extraction, queued_manuscript_chunkings
):
    """IR-195: unlike a supplementary upload, the manuscript is exactly what
    ADR-013's 2026-09-08 amendment says belongs in the RAG corpus."""
    _run(monkeypatch, FakeExtractor(), record.id)

    assert queued_manuscript_chunkings == [record.id]


def test_a_failed_extraction_does_not_queue_chunking(
    monkeypatch, record, extraction, queued_manuscript_chunkings
):
    _run(monkeypatch, FailingExtractor(ExtractionError("boom")), record.id)

    assert queued_manuscript_chunkings == []
