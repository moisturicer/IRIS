"""A task queue that is down never fails the write that queued a read (IR-1049).

A read is sent to Celery after the write commits. If the send raises (Redis
unreachable, say), the write is already saved, so raising would report a saved
upload or version as failed: the owner of IR-1049's v2 saw exactly that. The
send is logged instead, and the extraction row is marked failed, so a retry
sends it again; left ``queued`` it would pass for a read still on its way.

``django_capture_on_commit_callbacks(execute=True)`` runs the callbacks as a
real commit does, robust ones included.
"""

from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from kombu.exceptions import OperationalError

from apps.ai.chunking.document import PARAGRAPH, DocumentElement, NormalizedDocument
from apps.ai.extraction import InMemoryExtractor, use_extractor
from apps.documents.models import PdfExtraction, RecordUpload, UploadSlot
from apps.documents.sources import COULD_NOT_QUEUE, queue_upload_read
from apps.records.models import Record, RecordType
from apps.records.services import queue_manuscript_extraction
from apps.records.testing import released_embargo

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

DOWN = OperationalError("Error 111 connecting to redis:6379. Connection refused.")


@pytest.fixture(autouse=True)
def on_campus_extractor():
    """An Extractor that stays on campus, so the disclosure gate holds nothing back."""
    document = NormalizedDocument(
        title="A thesis",
        elements=(DocumentElement(kind=PARAGRAPH, text="Samples were collected weekly.", page=1),),
        page_sizes={1: (612.0, 792.0)},
    )
    with use_extractor(InMemoryExtractor(document)):
        yield


@pytest.fixture
def record(db):
    record = Record.objects.create(
        title="A thesis",
        record_type=RecordType.objects.create(name="Thesis"),
        abstract_file=SimpleUploadedFile("thesis.pdf", b"%PDF-1.7 fake bytes"),
    )
    released_embargo(record.pk)
    record.refresh_from_db()
    return record


@pytest.fixture
def upload(record):
    slot = UploadSlot.objects.create(name="Ethics Clearance", record_type=record.record_type)
    return RecordUpload.objects.create(
        record=record, slot=slot, file=SimpleUploadedFile("clearance.pdf", b"%PDF-1.7 fake bytes"),
    )


def test_a_manuscript_read_is_marked_failed_when_the_queue_is_down(
    record, django_capture_on_commit_callbacks, caplog,
):
    with mock.patch("apps.documents.tasks.extract_manuscript_text.delay", side_effect=DOWN) as send, \
            django_capture_on_commit_callbacks(execute=True):
        queue_manuscript_extraction(record)

    send.assert_called_once()
    extraction = PdfExtraction.objects.get(record=record)
    assert (extraction.status, extraction.error) == ("failed", COULD_NOT_QUEUE)
    assert "Connection refused" in caplog.text


def test_a_supporting_document_read_is_marked_failed_when_the_queue_is_down(
    upload, django_capture_on_commit_callbacks, caplog,
):
    with mock.patch("apps.documents.tasks.extract_pdf_text.delay", side_effect=DOWN) as send, \
            django_capture_on_commit_callbacks(execute=True):
        extraction = queue_upload_read(upload)

    send.assert_called_once_with(upload.pk)
    extraction.refresh_from_db()
    assert (extraction.status, extraction.error) == ("failed", COULD_NOT_QUEUE)
    assert "Connection refused" in caplog.text
