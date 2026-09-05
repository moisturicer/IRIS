"""Job idempotency and the lifecycle in the database (IR-115 G).

A duplicate delivery from Celery must cost nothing. These tests are what
say so at the level where it matters — the row, the unique key, and the
transition table applied to a stored state.
"""

import pytest
from django.conf import settings
from django.db import IntegrityError

from apps.ai.ingestion import IllegalTransition, IngestionState, ingestion_job_key
from apps.ai.ingestion.jobs import claim_ingestion_job, complete_ingestion_job
from apps.ai.models import EmbeddingSpace, EmbeddingSpaceState, IngestionJob
from apps.records.models import Record

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def _no_seeded_active_space():
    EmbeddingSpace.objects.all().delete()


@pytest.fixture
def space():
    return EmbeddingSpace.objects.create(
        model_id="voyage-context-4",
        dimensions=settings.AI_EMBEDDING_DIMENSIONS,
        state=EmbeddingSpaceState.ACTIVE,
    )


@pytest.fixture
def record():
    return Record.objects.create(title="A thesis")


def _claim(record, space, **overrides):
    return claim_ingestion_job(
        record_id=record.id,
        extraction_hash=overrides.get("extraction_hash", "e1"),
        strategy_id=overrides.get("strategy_id", "structural-markdown-v1"),
        space_id=space.id,
    )


class TestIdempotency:
    def test_a_job_is_keyed_on_all_four_identifying_parts(self, record, space):
        claim = _claim(record, space)

        assert claim.job.idempotency_key == ingestion_job_key(
            record_id=record.id,
            extraction_hash="e1",
            strategy_id="structural-markdown-v1",
            space_id=space.id,
        )

    def test_claiming_twice_returns_the_same_row(self, record, space):
        first = _claim(record, space)
        second = _claim(record, space)

        assert second.job.pk == first.job.pk
        assert IngestionJob.objects.count() == 1

    def test_a_duplicate_delivery_of_completed_work_is_a_no_op(self, record, space):
        claim = _claim(record, space)
        complete_ingestion_job(claim.job, content_hash="c1")

        redelivered = _claim(record, space)

        assert redelivered.is_duplicate is True
        assert redelivered.job.state == IngestionState.INDEXED

    def test_a_first_claim_is_not_a_duplicate(self, record, space):
        assert _claim(record, space).is_duplicate is False

    def test_an_incomplete_claim_is_not_a_duplicate(self, record, space):
        _claim(record, space)

        assert _claim(record, space).is_duplicate is False

    def test_a_failed_job_is_retried_rather_than_skipped(self, record, space):
        claim = _claim(record, space)
        claim.job.transition_to(IngestionState.FAILED, error="provider timeout")
        claim.job.save()

        retried = _claim(record, space)

        assert retried.is_duplicate is False
        assert retried.job.state == IngestionState.EXTRACTED
        assert retried.job.error == ""

    def test_a_different_strategy_is_a_different_job(self, record, space):
        _claim(record, space)

        other = _claim(record, space, strategy_id="fixed-window")

        assert other.is_duplicate is False
        assert IngestionJob.objects.count() == 2

    def test_a_re_extraction_is_a_different_job(self, record, space):
        claim = _claim(record, space)
        complete_ingestion_job(claim.job, content_hash="c1")

        other = _claim(record, space, extraction_hash="e2")

        assert other.is_duplicate is False

    def test_the_key_is_unique_at_the_database_level(self, record, space):
        claim = _claim(record, space)

        with pytest.raises(IntegrityError):
            IngestionJob.objects.create(
                record=record,
                extraction_hash="e1",
                strategy_id="structural-markdown-v1",
                space=space,
                idempotency_key=claim.job.idempotency_key,
            )


class TestLifecycleOnTheRow:
    def test_a_job_starts_from_extracted(self, record, space):
        """There is no key without an extraction hash, so a claimed job is
        by construction past the Uploaded state."""
        assert _claim(record, space).job.state == IngestionState.EXTRACTED

    def test_the_pipeline_runs_to_indexed(self, record, space):
        job = _claim(record, space).job

        job.transition_to(IngestionState.CHUNKED)
        job.transition_to(IngestionState.INDEXED)
        job.save()

        job.refresh_from_db()
        assert job.state == IngestionState.INDEXED

    def test_a_disallowed_transition_is_rejected(self, record, space):
        job = _claim(record, space).job

        with pytest.raises(IllegalTransition):
            job.transition_to(IngestionState.INDEXED)

        assert job.state == IngestionState.EXTRACTED

    def test_completion_records_the_content_hash(self, record, space):
        job = _claim(record, space).job

        complete_ingestion_job(job, content_hash="c1")

        job.refresh_from_db()
        assert job.content_hash == "c1"
        assert job.completed_at is not None


class TestStaleness:
    def test_a_changed_content_hash_marks_an_indexed_job_stale(self, record, space):
        job = _claim(record, space).job
        complete_ingestion_job(job, content_hash="c1")

        job.refresh_staleness(current_hash="c2")
        job.save()

        job.refresh_from_db()
        assert job.state == IngestionState.STALE

    def test_an_unchanged_content_hash_leaves_the_job_indexed(self, record, space):
        job = _claim(record, space).job
        complete_ingestion_job(job, content_hash="c1")

        job.refresh_staleness(current_hash="c1")

        assert job.state == IngestionState.INDEXED

    def test_nothing_outside_the_hash_comparison_can_set_stale(self, record, space):
        """Stale is derived, never asked for. The transition table is the
        enforcement: no state other than Indexed reaches it, and
        refresh_staleness is the only caller in the tree."""
        job = _claim(record, space).job

        with pytest.raises(IllegalTransition):
            job.transition_to(IngestionState.STALE)
