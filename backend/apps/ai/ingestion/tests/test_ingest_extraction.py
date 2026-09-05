"""Upload to active chunk set, with nothing done by hand (IR-116 H).

The first test here is the ticket's headline acceptance criterion, and it is
the first time in the IR-89 split that extraction, normalization, chunking,
the repository, the idempotency key and the lifecycle table are all exercised
by one call. The rest cover what happens when that call is repeated (nothing)
and when a stage fails (the job records it, and no half-written chunk set is
left behind).

Needs a database: the swap, the partial unique index and the job key are all
things only Postgres actually enforces.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.ai.chunking import ChunkingOptions
from apps.ai.extraction import document_to_json, extraction_hash
from apps.ai.ingestion import IngestionState, pipeline
from apps.ai.ingestion.pipeline import IngestionError, ingest_extraction
from apps.ai.models import IngestionJob, get_active_embedding_space
from apps.ai.models.chunk import ChunkSet as ChunkSetModel
from apps.ai.models.chunk import DocumentChunk
from apps.ai.repositories import DjangoChunkRepository
from apps.ai.tasks import chunk_record_document
from apps.documents.models import PdfExtraction, RecordUpload, UploadSlot
from apps.records.models import Record, RecordType

from .thesis_fixtures import ALL_FIXTURES, TEXT_LAYER_THESIS

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

OPTIONS = ChunkingOptions(max_tokens=512, exclude_sections=("References",))


@pytest.fixture
def space(db):
    """The one migration 0003 seeds. Ingestion keys its job on the active
    space, so using the seeded row rather than a purpose-built one keeps
    these tests on the path a deployment actually takes."""
    return get_active_embedding_space()


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
    return PdfExtraction.objects.create(
        upload=upload,
        status="done",
        structure=document_to_json(TEXT_LAYER_THESIS),
        content_hash=extraction_hash(TEXT_LAYER_THESIS),
        extractor="docling",
    )


def _ingest(extraction, **kwargs):
    kwargs.setdefault("options", OPTIONS)
    return ingest_extraction(extraction, repository=DjangoChunkRepository(), **kwargs)


# ---------------------------------------------------------------------------
# The pipeline, end to end
# ---------------------------------------------------------------------------


def test_ingesting_an_extraction_produces_an_active_chunk_set(space, upload, extraction):
    outcome = _ingest(extraction)

    active = ChunkSetModel.objects.get(record_id=upload.record_id, is_active=True)
    assert active.id == outcome.chunk_set_id
    assert active.chunks.count() == outcome.chunk_count > 0


def test_the_chunk_set_records_the_extraction_it_came_from(space, upload, extraction):
    _ingest(extraction)

    active = ChunkSetModel.objects.get(record_id=upload.record_id, is_active=True)
    assert active.extraction_hash == extraction.content_hash
    assert active.strategy_id == OPTIONS.strategy


def test_every_persisted_chunk_maps_back_to_a_page_and_a_record(space, upload, extraction):
    _ingest(extraction)

    chunks = DocumentChunk.objects.filter(record_id=upload.record_id)
    assert chunks.exists()
    for chunk in chunks:
        assert chunk.record_id == upload.record_id
        assert chunk.source_page is not None
        assert chunk.content.strip()
        assert chunk.bboxes


def test_the_context_path_survives_persistence(space, upload, extraction):
    """It is stored as an array column, so this is where a round trip through
    the database could quietly drop it."""
    _ingest(extraction)

    paths = [c.context_path for c in DocumentChunk.objects.all()]
    assert all(path for path in paths)
    assert any("3.2 Sampling Procedure" in path for path in paths)


def test_the_job_reaches_indexed_and_stores_the_chunk_set_hash(space, upload, extraction):
    outcome = _ingest(extraction)

    job = IngestionJob.objects.get(record_id=upload.record_id)
    active = ChunkSetModel.objects.get(pk=outcome.chunk_set_id)
    assert job.state == IngestionState.INDEXED.value
    assert job.content_hash == active.content_hash
    assert job.completed_at is not None


def test_the_run_reports_what_is_left_to_embed(space, upload, extraction):
    """Embedding is IR-108, so this pipeline's output is a work order rather
    than a vector — the count is what a later stage will pay for."""
    outcome = _ingest(extraction)

    assert outcome.to_embed == outcome.chunk_count
    assert outcome.wrote_anything


@pytest.mark.parametrize("fixture_name", sorted(ALL_FIXTURES))
def test_every_fixture_shape_persists_chunks_tied_to_its_record(
    space, upload, fixture_name
):
    """The five shapes IR-116 names, through the persistence half too. The
    pure suite asserts their page mapping; only here can "maps back to a
    record" mean anything, and only here does the sequence uniqueness
    constraint get exercised on each shape."""
    document = ALL_FIXTURES[fixture_name]
    extraction = PdfExtraction.objects.create(
        upload=upload,
        status="done",
        structure=document_to_json(document),
        content_hash=extraction_hash(document),
        extractor="docling",
    )

    outcome = _ingest(extraction)

    chunks = DocumentChunk.objects.filter(chunk_set_id=outcome.chunk_set_id)
    assert chunks.count() == outcome.chunk_count > 0
    for chunk in chunks:
        assert chunk.record_id == upload.record_id
        assert chunk.source_page in document.page_sizes
        assert chunk.content.strip()


# ---------------------------------------------------------------------------
# Re-running
# ---------------------------------------------------------------------------


def test_re_running_on_an_unchanged_upload_performs_zero_writes(space, upload, extraction):
    first = _ingest(extraction)

    with CaptureQueriesContext(connection) as captured:
        second = _ingest(extraction)

    writes = [
        q["sql"]
        for q in captured.captured_queries
        if q["sql"].strip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
    ]
    assert writes == []
    assert second.duplicate is True
    assert second.chunk_set_id == first.chunk_set_id


def test_re_running_leaves_exactly_one_active_chunk_set(space, upload, extraction):
    _ingest(extraction)
    _ingest(extraction)

    assert ChunkSetModel.objects.filter(record_id=upload.record_id).count() == 1


def test_forcing_a_re_chunk_swaps_the_active_set(space, upload, extraction):
    """The idempotency key does not include ChunkingOptions, so comparing one
    token ceiling against another needs a way past the duplicate check. This
    is the one the manual inspection uses."""
    first = _ingest(extraction)

    second = _ingest(
        extraction, options=ChunkingOptions(max_tokens=30), force=True
    )

    assert second.chunk_set_id != first.chunk_set_id
    assert second.chunk_count > first.chunk_count
    active = ChunkSetModel.objects.filter(record_id=upload.record_id, is_active=True)
    assert active.count() == 1
    assert active.first().id == second.chunk_set_id


# ---------------------------------------------------------------------------
# Failure
# ---------------------------------------------------------------------------


def test_a_failure_while_chunking_is_recorded_against_the_job(
    monkeypatch, space, upload, extraction
):
    monkeypatch.setattr(
        pipeline, "build_chunk_set", _raise(RuntimeError("cascade blew up"))
    )

    with pytest.raises(RuntimeError):
        _ingest(extraction)

    job = IngestionJob.objects.get(record_id=upload.record_id)
    assert job.state == IngestionState.FAILED.value
    assert "cascade blew up" in job.error


def test_a_failure_leaves_no_partially_written_chunk_set(
    monkeypatch, space, upload, extraction
):
    monkeypatch.setattr(
        pipeline, "build_chunk_set", _raise(RuntimeError("cascade blew up"))
    )

    with pytest.raises(RuntimeError):
        _ingest(extraction)

    assert not ChunkSetModel.objects.exists()
    assert not DocumentChunk.objects.exists()


def test_a_failed_job_is_retried_rather_than_skipped_as_a_duplicate(
    monkeypatch, space, upload, extraction
):
    monkeypatch.setattr(
        pipeline, "build_chunk_set", _raise(RuntimeError("transient"))
    )
    with pytest.raises(RuntimeError):
        _ingest(extraction)
    monkeypatch.undo()

    outcome = _ingest(extraction)

    assert outcome.wrote_anything
    job = IngestionJob.objects.get(record_id=upload.record_id)
    assert job.state == IngestionState.INDEXED.value
    assert job.error == ""


def test_the_failure_is_recorded_against_the_extraction_too(
    monkeypatch, space, upload, extraction
):
    """A job row carries it as well, but only once one exists — and the two
    input checks run before a job can be keyed. Without this, a record could
    go unindexed with no durable trace anywhere."""
    monkeypatch.setattr(pipeline, "build_chunk_set", _raise(RuntimeError("boom")))

    with pytest.raises(RuntimeError):
        _ingest(extraction)

    extraction.refresh_from_db()
    assert "boom" in extraction.error
    # Extraction itself succeeded; a chunking failure must not rewrite that
    # verdict, or a document with perfectly good text looks unextracted.
    assert extraction.status == "done"


def test_an_extraction_with_no_structure_is_a_stated_failure(space, upload):
    extraction = PdfExtraction.objects.create(upload=upload, status="failed")

    with pytest.raises(IngestionError):
        _ingest(extraction)

    assert not ChunkSetModel.objects.exists()
    assert not IngestionJob.objects.exists()
    extraction.refresh_from_db()
    assert "no stored structure" in extraction.error


def test_an_extraction_with_no_content_hash_cannot_be_keyed(space, upload):
    extraction = PdfExtraction.objects.create(
        upload=upload, status="done", structure=document_to_json(TEXT_LAYER_THESIS)
    )

    with pytest.raises(IngestionError):
        _ingest(extraction)

    assert not IngestionJob.objects.exists()


# ---------------------------------------------------------------------------
# The task around it
# ---------------------------------------------------------------------------


def test_the_task_produces_an_active_chunk_set(space, upload, extraction):
    result = chunk_record_document.apply(args=[upload.id])

    assert result.successful()
    active = ChunkSetModel.objects.get(record_id=upload.record_id, is_active=True)
    assert result.result["chunk_set_id"] == active.id
    assert result.result["chunk_count"] == active.chunks.count()


def test_the_task_uses_the_configured_defaults(settings, space, upload, extraction):
    """The token ceiling is a deployment decision, per IR-116's exit
    criterion — so it has to reach the pipeline from settings."""
    settings.AI_CHUNK_MAX_TOKENS = 30

    chunk_record_document.apply(args=[upload.id])

    active = ChunkSetModel.objects.get(record_id=upload.record_id, is_active=True)
    assert active.options["max_tokens"] == 30
    assert all(chunk.token_count <= 30 for chunk in active.chunks.all())


def test_the_task_does_not_retry_an_extraction_with_nothing_to_chunk(space, upload):
    """Four more attempts will not conjure a structure. The failure is
    reported rather than queued again."""
    PdfExtraction.objects.create(upload=upload, status="failed")

    result = chunk_record_document.apply(args=[upload.id])

    assert result.failed()
    assert isinstance(result.result, IngestionError)


def test_a_deleted_extraction_row_is_not_an_error(space, upload):
    result = chunk_record_document.apply(args=[upload.id])

    assert result.successful()
    assert result.result is None


def _raise(error):
    def _fail(*args, **kwargs):
        raise error

    return _fail
