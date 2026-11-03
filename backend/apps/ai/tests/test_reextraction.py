"""The LlamaParse cutover plans, prices and refuses before it reads (IR-842)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.ai.extraction.tests.fixtures import FIXTURES, pdf_bytes
from apps.ai.reextraction import plan_cutover
from apps.documents.models import DocumentKind, PdfExtraction
from apps.records.models import Record, RecordType

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

FIXTURE = next(f for f in FIXTURES.values() if len(f.pages) > 1)
PDF = pdf_bytes(FIXTURE)
PAGES = len(FIXTURE.pages)

PRICE = {
    "AI_ADMISSION_EXTRACTION_CREDIT_USD": "0.00125",
    "AI_ADMISSION_EXTRACTION_CREDITS_PER_PAGE": "10",
    "AI_ADMISSION_EXTRACTION_ADDON_CREDITS_PER_PAGE": "2",
}


@pytest.fixture
def priced(settings):
    for name, value in PRICE.items():
        setattr(settings, name, value)


def _record(title="A thesis", *, consent=True, embargo=None, answered=True, extractor="docling"):
    record = Record.objects.create(
        title=title,
        record_type=RecordType.objects.get_or_create(name="Thesis")[0],
        abstract_file=SimpleUploadedFile("thesis.pdf", PDF),
        embargo_answered_at=timezone.now() if answered else None,
        embargoed_until=embargo,
        dpa_accepted_at=timezone.now() if consent else None,
        manuscript_revision=uuid.uuid4(),
    )
    PdfExtraction.objects.create(
        record=record, kind=DocumentKind.MANUSCRIPT, status="done", extractor=extractor,
        source_revision=record.manuscript_revision, source_file=record.abstract_file.name,
    )
    return record


def test_the_plan_prices_permitted_papers_and_names_why_the_rest_are_skipped(priced):
    permitted = _record("Permitted")
    _record("No consent", consent=False)
    _record("Embargoed", embargo=date(2030, 1, 1))
    _record("Unanswered", answered=False)
    _record("Already read", extractor="llamaparse")

    plan = plan_cutover()

    assert [item.record_id for item in plan.to_read] == [permitted.pk]
    assert plan.pages == PAGES
    assert plan.credits == Decimal(PAGES * 12)
    assert plan.usd == Decimal(PAGES * 12) * Decimal("0.00125")
    assert sorted(item.reason for item in plan.skipped) == [
        "already read by LlamaParse",
        "awaiting consent or release",
        "awaiting consent or release",
        "awaiting consent or release",
    ]


# -- the command ---------------------------------------------------------

from io import StringIO

from django.core.management import CommandError, call_command

from apps.ai.extraction import InMemoryExtractor, use_extractor
from apps.ai.models import ChunkSet, DocumentChunk
from apps.documents import tasks
from apps.documents.phases import ExtractionPhase


@pytest.fixture
def queued(monkeypatch, settings):
    calls = []
    monkeypatch.setattr(tasks.extract_manuscript_text, "delay", lambda *args: calls.append(args))
    settings.EXTRACTION_BACKEND = "llamaparse"
    with use_extractor(InMemoryExtractor(None, leaves_campus=True)):
        yield calls


def _run(*args):
    out = StringIO()
    call_command("reextract_manuscripts", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db(transaction=True)
def test_a_dry_run_prints_the_bill_and_queues_nothing(priced, queued):
    _record()

    output = _run("--dry-run")

    assert queued == []
    assert f"pages                {PAGES}" in output
    assert "Dry run" in output


@pytest.mark.django_db(transaction=True)
def test_a_real_run_needs_a_stated_ceiling(priced, queued):
    _record()
    with pytest.raises(CommandError, match="--credit-ceiling"):
        _run()
    assert queued == []


@pytest.mark.django_db(transaction=True)
def test_a_run_over_the_ceiling_sends_nothing(priced, queued):
    _record()
    with pytest.raises(CommandError, match="over the ceiling"):
        _run("--credit-ceiling", str(PAGES * 12 - 1))
    assert queued == []


@pytest.mark.django_db(transaction=True)
def test_a_run_refuses_while_the_backend_is_still_docling(priced, queued, settings):
    _record()
    settings.EXTRACTION_BACKEND = "docling"
    with pytest.raises(CommandError, match="EXTRACTION_BACKEND"):
        _run("--credit-ceiling", "1000")
    assert queued == []


@pytest.mark.django_db(transaction=True)
def test_a_run_queues_each_permitted_paper_once_and_keeps_the_old_chunks_live(priced, queued):
    record = _record()
    _record("Gated", consent=False)
    old = ChunkSet.objects.create(
        record=record, extraction_hash="d", strategy_id="s", options={}, content_hash="d",
        source_revision=record.manuscript_revision, is_active=True,
    )

    _run("--credit-ceiling", "1000")
    _run("--credit-ceiling", "1000")

    assert queued == [(record.pk, str(record.manuscript_revision))]
    extraction = PdfExtraction.objects.get(record=record)
    assert extraction.phase == ExtractionPhase.QUEUED
    old.refresh_from_db()
    assert old.is_active


@pytest.mark.django_db(transaction=True)
def test_rollback_restores_the_previous_chunk_set_and_its_tombstoned_chunks(priced, queued):
    record = _record(extractor="llamaparse")
    previous = ChunkSet.objects.create(
        record=record, extraction_hash="d", strategy_id="s", options={}, content_hash="d",
    )
    chunk = DocumentChunk.objects.create(
        chunk_set=previous, record=record, sequence=0, max_sequence=0, text="t", content="t",
        text_hash="h", token_count=1, deleted_at=timezone.now(),
    )
    current = ChunkSet.objects.create(
        record=record, extraction_hash="l", strategy_id="s", options={}, content_hash="l",
        is_active=True,
    )

    _run("--rollback", "--record", str(record.pk))

    previous.refresh_from_db()
    current.refresh_from_db()
    chunk.refresh_from_db()
    assert previous.is_active and not current.is_active
    assert chunk.deleted_at is None
