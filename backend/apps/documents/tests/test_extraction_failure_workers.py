"""IR-839's failure policy across independent workers on real PostgreSQL.

A superseded attempt's failure, permanent or transient, must neither fail
the row nor schedule a retry: IR-831's attempt fence decides, not the error.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connections

from apps.ai.chunking.document import PARAGRAPH, DocumentElement, NormalizedDocument
from apps.ai.extraction import DocumentRejected, ExtractorUnavailable, InMemoryExtractor, use_extractor
from apps.documents import tasks
from apps.documents.models import DocumentKind, PdfExtraction
from apps.records.models import Record, RecordType

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

DOCUMENT = NormalizedDocument(
    title="Current manuscript",
    elements=(DocumentElement(kind=PARAGRAPH, text="A complete research passage.", page=1),),
    page_sizes={1: (612.0, 792.0), 2: (612.0, 792.0)},
)


@pytest.fixture
def pinned(tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)
    monkeypatch.setattr(tasks, "_queue_chunk_extraction", lambda *args: None)
    revision = uuid.uuid4()
    record = Record.objects.create(
        title="A thesis", record_type=RecordType.objects.create(name="Thesis"),
        abstract_file=SimpleUploadedFile("thesis.pdf", b"%PDF-1.7 fake bytes"),
        manuscript_revision=revision,
    )
    PdfExtraction.objects.create(
        record=record, kind=DocumentKind.MANUSCRIPT,
        source_revision=revision, source_file=record.abstract_file.name,
    )
    return record.pk, str(revision)


@pytest.mark.parametrize("stale_error", [
    DocumentRejected("refused"), ExtractorUnavailable("down"), RuntimeError("bug"),
], ids=["permanent", "transient", "unexpected"])
def test_a_superseded_attempt_cannot_fail_or_retry_the_current_one(pinned, monkeypatch, stale_error):
    record_id, revision = pinned
    retries = []
    monkeypatch.setattr(tasks.extract_manuscript_text, "retry",
                        lambda **kwargs: retries.append(kwargs))
    started, release = Event(), Event()

    def respond(content, filename):
        if not started.is_set():
            started.set()
            assert release.wait(20)
            return stale_error
        return DOCUMENT

    def worker():
        connections.close_all()
        try:
            return tasks.extract_manuscript_text.apply(args=[record_id, revision])
        finally:
            connections.close_all()

    extractor = InMemoryExtractor(respond, failed_pages=(2,))
    with use_extractor(extractor), ThreadPoolExecutor(max_workers=1) as workers:
        stale = workers.submit(worker)
        try:
            assert started.wait(20)
            # A redelivered message in another worker takes the row over.
            assert tasks.extract_manuscript_text.apply(args=[record_id, revision]).successful()
        finally:
            release.set()
        assert stale.result(timeout=20).successful()

    extraction = PdfExtraction.objects.get(record_id=record_id)
    assert (extraction.status, extraction.error) == ("done", "")
    assert extraction.warnings == [{"kind": "page_failed", "page": 2}]
    assert retries == []
    assert len(extractor.calls) == 2
