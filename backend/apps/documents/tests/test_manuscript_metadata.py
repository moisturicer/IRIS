"""LlamaExtract reads a parsed Manuscript, gated, admitted and fenced (IR-846).

The parse is IR-849's recorded ``two_columns`` result, served by the in-memory
Extractor as LlamaParse; LlamaExtract is a fake reader answering with an
authored reading. Admission writes through its own connection, so these run
against real Postgres with committed transactions.
"""

import uuid
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.ai.admission.tests.support import enforce
from apps.ai.chunking.document import PARAGRAPH, DocumentElement, NormalizedDocument
from apps.ai.extraction import InMemoryExtractor, Provenance, Usage, use_extractor
from apps.ai.extraction.llamaextract_client import MetadataReading
from apps.ai.extraction.selection import use_metadata_reader
from apps.ai.extraction.tests.fixtures import FIXTURES, pdf_bytes
from apps.ai.extraction.tests.llamaextract_vendor import PARSE_JOB_ID, two_columns_reading
from apps.ai.extraction.tests.llamaparse_fixtures import recorded
from apps.ai.models import ProviderCampaign, ProviderReservation
from apps.ai.models.admission import RELEASED, SETTLED
from apps.documents import tasks
from apps.documents.models import DocumentKind, ManuscriptMetadata, PdfExtraction
from apps.records.models import Record, RecordType

pytestmark = [
    pytest.mark.db_required,
    pytest.mark.django_db(transaction=True, databases=["default", "admission"]),
]

DOCUMENT = NormalizedDocument(
    title="Two column study",
    elements=(DocumentElement(kind=PARAGRAPH, text="Left column one opens.", page=1),),
    page_sizes={1: (612.0, 792.0)},
)
PDF = pdf_bytes(FIXTURES["two_columns"])

#: Placeholders for tests only: nothing here is an approved price.
PRICES = {
    "AI_ADMISSION_LANE_CONCURRENCY": '{"extraction": 2}',
    "AI_ADMISSION_EXTRACTION_CREDIT_USD": "0.00125",
    "AI_ADMISSION_EXTRACTION_CREDITS_PER_PAGE": "10",
    "AI_ADMISSION_EXTRACTION_ADDON_CREDITS_PER_PAGE": "2",
    "AI_ADMISSION_METADATA_CREDITS_PER_PAGE": "15",
}


class FakeReader:
    """Stands in for LlamaExtract where admission and the task look."""

    model = "llamaextract-agentic"
    account = "memory-account"
    timeout_seconds = 60.0

    def __init__(self, answer=None, *, during=None):
        self._answer = answer
        self._during = during
        self.calls: list[str] = []

    def read(self, parse_job_id: str) -> MetadataReading:
        self.calls.append(parse_job_id)
        if self._during:
            self._during()
        if isinstance(self._answer, BaseException):
            raise self._answer
        vendor = two_columns_reading()
        return MetadataReading(
            values=vendor["extract_result"],
            field_metadata=vendor["extract_metadata"]["field_metadata"]["document_metadata"],
            credits=Decimal("15"),
        )


@pytest.fixture(autouse=True)
def queued(monkeypatch):
    """Celery calls the code under test would make, recorded, not run."""
    calls = []
    monkeypatch.setattr(tasks, "_queue_chunk_extraction", lambda *args: calls.append(("chunk", args)))
    monkeypatch.setattr(tasks.read_manuscript_metadata, "delay", lambda *args: calls.append(("metadata", args)))
    return calls


@pytest.fixture
def enforced(settings):
    enforce(settings, **PRICES)


def _record(*, consent=True):
    record = Record.objects.create(
        title="two_columns.pdf",
        record_type=RecordType.objects.get_or_create(name="Thesis")[0],
        abstract_file=SimpleUploadedFile("two_columns.pdf", PDF),
        embargo_answered_at=timezone.now(),
        dpa_accepted_at=timezone.now() if consent else None,
        manuscript_revision=uuid.uuid4(),
    )
    PdfExtraction.objects.create(
        record=record, kind=DocumentKind.MANUSCRIPT, source_revision=record.manuscript_revision,
    )
    return record


def _llamaparse():
    return InMemoryExtractor(
        DOCUMENT, leaves_campus=True, provenance=Provenance(name="llamaparse", version="2026-09-28"),
        usage=Usage(pages=1, credits=Decimal("15")), raw=recorded("two_columns"),
    )


def _parse(record):
    with use_extractor(_llamaparse()):
        tasks.extract_manuscript_text.apply(args=[record.pk, str(record.manuscript_revision)])


def _read(record, reader):
    reading = ManuscriptMetadata.objects.get(extraction__record=record)
    with use_metadata_reader(reader):
        tasks.read_manuscript_metadata.apply(args=[reading.pk])
    reading.refresh_from_db()
    return reading


def _reservations():
    return list(ProviderReservation.objects.using("admission").order_by("pk"))


def test_a_llamaparse_read_queues_one_reading_of_that_parse(enforced, queued, settings):
    settings.LLAMAEXTRACT_VERSION = "2.5"
    record = _record()

    _parse(record)

    reading = ManuscriptMetadata.objects.get(extraction__record=record)
    assert reading.status == ManuscriptMetadata.QUEUED
    assert str(reading.source_revision) == str(record.manuscript_revision)
    assert ("metadata", (reading.pk,)) in queued


def test_no_reading_is_queued_when_llamaextract_is_not_set_up(enforced, queued, settings):
    settings.LLAMAEXTRACT_VERSION = ""
    record = _record()

    _parse(record)

    assert not ManuscriptMetadata.objects.exists()


def test_a_local_read_queues_no_reading(enforced, queued, settings):
    settings.LLAMAEXTRACT_VERSION = "2.5"
    record = _record()

    with use_extractor(InMemoryExtractor(DOCUMENT)):
        tasks.extract_manuscript_text.apply(args=[record.pk, str(record.manuscript_revision)])

    assert not ManuscriptMetadata.objects.exists()


def test_the_reading_names_the_parse_job_and_is_admitted_and_settled(enforced, settings):
    settings.LLAMAEXTRACT_VERSION = "2.5"
    record = _record()
    _parse(record)
    reader = FakeReader()

    reading = _read(record, reader)

    assert reader.calls == [PARSE_JOB_ID]
    assert reading.status == ManuscriptMetadata.DONE
    assert reading.started_at is not None
    assert reading.result["values"]["title"] == "Two column study"
    assert reading.credits == Decimal("15")
    metadata = [r for r in _reservations() if r.operation == "metadata"]
    assert [r.state for r in metadata] == [SETTLED]
    # 15 credits at US$0.00125.
    assert metadata[0].charge_cost_micros == 18_750


def test_a_paper_whose_consent_is_withdrawn_before_sending_is_not_sent(enforced, settings):
    settings.LLAMAEXTRACT_VERSION = "2.5"
    record = _record()
    _parse(record)
    Record.objects.filter(pk=record.pk).update(dpa_accepted_at=None)
    reader = FakeReader()

    reading = _read(record, reader)

    assert reader.calls == []
    assert reading.status == ManuscriptMetadata.REFUSED
    assert [r.state for r in _reservations() if r.operation == "metadata"] == [RELEASED]


def test_an_unpriced_reading_is_refused_and_falls_back(enforced, settings):
    settings.LLAMAEXTRACT_VERSION = "2.5"
    settings.AI_ADMISSION_METADATA_CREDITS_PER_PAGE = ""
    record = _record()
    _parse(record)
    reader = FakeReader()

    reading = _read(record, reader)

    assert reader.calls == []
    assert reading.status == ManuscriptMetadata.FAILED


def test_a_vendor_failure_is_recorded_without_its_message(enforced, settings):
    from apps.ai.extraction import ExtractorUnavailable

    settings.LLAMAEXTRACT_VERSION = "2.5"
    record = _record()
    _parse(record)

    reading = _read(record, FakeReader(ExtractorUnavailable("LlamaExtract create job returned 503")))

    assert reading.status == ManuscriptMetadata.FAILED
    assert reading.result == {}


def test_a_replacement_while_reading_keeps_the_late_result_out(enforced, settings):
    settings.LLAMAEXTRACT_VERSION = "2.5"
    record = _record()
    _parse(record)

    def replace_manuscript():
        Record.objects.filter(pk=record.pk).update(manuscript_revision=uuid.uuid4())

    reading = _read(record, FakeReader(during=replace_manuscript))

    assert reading.status == ManuscriptMetadata.RUNNING
    assert reading.result == {}
