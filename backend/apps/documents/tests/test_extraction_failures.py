"""What the extraction task does with a failure (IR-839).

Transient trouble is retried after 1, 3 and 9 minutes; anything else fails
once with a reader message that names no internals.
"""

import logging

import pytest
from celery.exceptions import Retry
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.ai.chunking.document import PARAGRAPH, DocumentElement, NormalizedDocument
from apps.ai.extraction import (
    DocumentRejected,
    ExtractionError,
    ExtractorUnavailable,
    InMemoryExtractor,
    use_extractor,
)
from apps.documents import tasks
from apps.documents.models import DocumentKind, PdfExtraction
from apps.records.models import Record, RecordType

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

PERMANENT = "This PDF can't be read automatically. Enter the details manually."
TRANSIENT = "Reading is temporarily unavailable. Try again later."

DOCUMENT = NormalizedDocument(
    title="Optimization of Tilapia Feed Conversion",
    elements=(DocumentElement(kind=PARAGRAPH, text="Samples were collected weekly.", page=1),),
    page_sizes={1: (612.0, 792.0), 2: (612.0, 792.0), 3: (612.0, 792.0)},
)


@pytest.fixture(autouse=True)
def no_chunking(monkeypatch):
    monkeypatch.setattr(tasks, "_queue_chunk_extraction", lambda *args: None)


@pytest.fixture
def extraction(db):
    record = Record.objects.create(
        title="A thesis",
        record_type=RecordType.objects.create(name="Thesis"),
        abstract_file=SimpleUploadedFile("thesis.pdf", b"%PDF-1.7 fake bytes"),
    )
    return PdfExtraction.objects.create(record=record, kind=DocumentKind.MANUSCRIPT)


@pytest.fixture
def task_log(monkeypatch, caplog):
    """The "apps" logger does not propagate, so caplog would see nothing."""
    monkeypatch.setattr(logging.getLogger("apps"), "propagate", True)
    caplog.set_level(logging.ERROR, logger="apps.documents.tasks")
    return lambda: [r for r in caplog.records if r.name == "apps.documents.tasks" and r.exc_info]


@pytest.fixture
def countdowns(monkeypatch):
    """Every retry's countdown, while the retry itself still runs eagerly."""
    task = tasks.extract_manuscript_text
    original = task.retry
    seen = []

    def retry(*args, **kwargs):
        seen.append(kwargs.get("countdown"))
        return original(*args, **kwargs)

    monkeypatch.setattr(task, "retry", retry)
    return seen


def _run(extractor, extraction):
    with use_extractor(extractor):
        return tasks.extract_manuscript_text.apply(args=[extraction.record_id])


@pytest.mark.parametrize("error", [
    DocumentRejected("LlamaParse refused /srv/media/thesis.pdf"),
    ExtractionError("Docling-serve returned a non-JSON body"),
    RuntimeError("KeyError in the mapper at /srv/app/mapping.py"),
], ids=["rejected", "other", "unexpected"])
def test_a_permanent_failure_fails_once_with_the_permanent_message(extraction, countdowns, error):
    extractor = InMemoryExtractor(error)

    result = _run(extractor, extraction)

    extraction.refresh_from_db()
    assert len(extractor.calls) == 1
    assert countdowns == []
    assert (extraction.status, extraction.phase) == ("failed", "failed")
    assert extraction.error == PERMANENT
    assert result.failed()
    assert str(error) not in str(result.result)


def test_an_empty_extraction_is_permanent(extraction, countdowns):
    extractor = InMemoryExtractor(NormalizedDocument(title="", elements=()))

    _run(extractor, extraction)

    extraction.refresh_from_db()
    assert len(extractor.calls) == 1
    assert extraction.error == PERMANENT


def test_an_unexpected_exception_is_logged_with_its_traceback(extraction, task_log):
    _run(InMemoryExtractor(RuntimeError("mapper bug")), extraction)

    logged = task_log()
    assert logged and "mapper bug" in str(logged[0].exc_info[1])
    extraction.refresh_from_db()
    assert "mapper bug" not in extraction.error


def test_an_expected_rejection_is_not_logged_as_a_crash(extraction, task_log):
    _run(InMemoryExtractor(DocumentRejected("encrypted")), extraction)

    assert not task_log()


def test_a_transient_failure_retries_after_one_three_and_nine_minutes(extraction, countdowns):
    extractor = InMemoryExtractor(ExtractorUnavailable("connection refused at http://llamaparse"))

    result = _run(extractor, extraction)

    extraction.refresh_from_db()
    assert len(extractor.calls) == 4
    assert countdowns == [60, 180, 540]
    assert (extraction.status, extraction.phase) == ("failed", "failed")
    assert extraction.error == TRANSIENT
    assert result.failed()


def test_a_retrying_extraction_shows_no_failure_message(extraction, monkeypatch):
    monkeypatch.setattr(tasks.extract_manuscript_text, "retry",
                        lambda **kwargs: (_ for _ in ()).throw(Retry()))

    _run(InMemoryExtractor(ExtractorUnavailable("down")), extraction)

    extraction.refresh_from_db()
    assert (extraction.status, extraction.phase, extraction.error) == ("retrying", "retrying", "")


def test_transient_trouble_that_clears_reaches_done(extraction, countdowns):
    answers = iter([ExtractorUnavailable("down"), ExtractorUnavailable("down"), DOCUMENT])

    _run(InMemoryExtractor(lambda content, filename: next(answers)), extraction)

    extraction.refresh_from_db()
    assert countdowns == [60, 180]
    assert (extraction.status, extraction.error) == ("done", "")


def test_failed_pages_are_warnings_and_the_rest_is_used(extraction):
    _run(InMemoryExtractor(DOCUMENT, failed_pages=(2, 3)), extraction)

    extraction.refresh_from_db()
    assert extraction.status == "done"
    assert extraction.extracted_text
    assert extraction.warnings == [{"kind": "page_failed", "page": 2}, {"kind": "page_failed", "page": 3}]


def test_a_clean_extraction_has_no_warnings(extraction):
    _run(InMemoryExtractor(DOCUMENT), extraction)

    extraction.refresh_from_db()
    assert extraction.warnings == []


@pytest.mark.parametrize("evidence_wall, limit", [(None, 960), (120, 1080)])
def test_each_attempt_is_limited_to_the_declared_timeout_plus_evidence_plus_a_minute(
        extraction, monkeypatch, settings, evidence_wall, limit):
    # IR-1053: the PDF evidence read runs inside the same attempt.
    from celery.app.task import Task

    settings.PDF_EVIDENCE_WALL_SECONDS = evidence_wall
    sent = []
    monkeypatch.setattr(Task, "apply_async", lambda self, args=None, kwargs=None, **options: sent.append(options))

    with use_extractor(InMemoryExtractor(DOCUMENT, timeout_seconds=900)):
        tasks.extract_manuscript_text.delay(extraction.record_id, None)
        tasks.extract_pdf_text.delay(1)

    assert [options["time_limit"] for options in sent] == [limit, limit]
    assert all(options["soft_time_limit"] < options["time_limit"] for options in sent)


def test_a_soft_time_limit_is_transient(extraction, countdowns):
    from celery.exceptions import SoftTimeLimitExceeded

    extractor = InMemoryExtractor(SoftTimeLimitExceeded())

    _run(extractor, extraction)

    extraction.refresh_from_db()
    assert len(extractor.calls) == 4
    assert extraction.error == TRANSIENT


@pytest.fixture
def owned(extraction):
    import uuid

    from rest_framework.test import APIClient

    from apps.records.models import RecordOwner
    from apps.records.tests import make_user

    record = extraction.record
    owner = make_user("failure-owner@cit.edu", "Student")
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    record.manuscript_revision = uuid.uuid4()
    record.save(update_fields=["manuscript_revision"])
    extraction.source_revision = record.manuscript_revision
    extraction.source_file = record.abstract_file.name
    extraction.save(update_fields=["source_revision", "source_file"])
    client = APIClient()
    client.force_authenticate(owner)
    return client, record


def _status(client, record):
    from django.urls import reverse

    return client.get(reverse("record-metadata-suggestions", args=[record.pk])).json()


@pytest.mark.parametrize("error, message", [
    (DocumentRejected("password-protected /srv/media/thesis.pdf"), PERMANENT),
    (ExtractorUnavailable("503 from http://llamaparse"), TRANSIENT),
], ids=["permanent", "transient"])
def test_the_reader_sees_one_of_two_messages_and_may_retry(
    owned, monkeypatch, django_capture_on_commit_callbacks, error, message
):
    from django.urls import reverse

    client, record = owned
    queued = []
    monkeypatch.setattr(tasks.extract_manuscript_text, "delay", lambda *args: queued.append(args))
    revision = str(record.manuscript_revision)

    with use_extractor(InMemoryExtractor(error)):
        tasks.extract_manuscript_text.apply(args=[record.pk, revision])

    payload = _status(client, record)
    assert (payload["state"], payload["retryable"], payload["message"]) == ("failed", True, message)
    assert "srv" not in str(payload) and "llamaparse" not in str(payload)
    url = reverse("record-retry-extraction", args=[record.pk])
    with django_capture_on_commit_callbacks(execute=True):
        assert client.post(url, {"manuscript_revision": revision}).status_code == 202
    assert queued == [(record.pk, revision)]
    assert _status(client, record)["message"] is None


def test_a_failed_page_is_not_shown_to_the_reader(owned):
    client, record = owned

    with use_extractor(InMemoryExtractor(DOCUMENT, failed_pages=(2,))):
        tasks.extract_manuscript_text.apply(args=[record.pk, str(record.manuscript_revision)])

    payload = _status(client, record)
    assert payload["state"] == "ready" and payload["message"] is None
    assert "warning" not in str(payload) and "page_failed" not in str(payload)
