from celery import shared_task
from django.utils import timezone


def _claim_job(task, record_id: int):
    """Mark this record's newest ``EmbeddingJob`` running, if it has one.

    Optional by design: a job row exists when a person asked for indexing
    through the API, and does not when a backfill or a chunking run queued
    the work itself. The task must do the same thing either way.
    """
    from apps.ai.models import EmbeddingJob

    job = (
        EmbeddingJob.objects.filter(record_id=record_id)
        .order_by("-created_at")
        .first()
    )
    if job:
        job.status = "running"
        job.celery_task_id = task.request.id
        job.save(update_fields=["status", "celery_task_id"])
    return job


def _finish_job(job, outcome) -> None:
    """Close a job out, recording a policy refusal as a refusal.

    A refused record is not a failure to retry — the gate will say the same
    thing in sixty seconds — but it is not a success either, and a job that
    reported ``done`` on it would leave an unindexed record looking indexed.
    """
    if not job:
        return
    if outcome.refused:
        job.status = "failed"
        job.error = outcome.reason
        job.save(update_fields=["status", "error"])
        return
    job.status = "done"
    job.completed_at = timezone.now()
    job.save(update_fields=["status", "completed_at"])


def _fail_job(job, exc: Exception) -> None:
    if not job:
        return
    job.status = "failed"
    job.error = str(exc)
    job.save(update_fields=["status", "error"])


@shared_task(bind=True, max_retries=3)
def embed_record(self, record_id: int, *, skip_existing: bool = False):
    """Embed a record's title and abstract in-process (ADR-024).

    The gateway hop this used to make is gone: it posted to a route the
    gateway never registered, at an endpoint that returns no vector field, so
    it had never once produced a vector. ``apps.ai.indexing`` owns the work
    now and this task owns only the bookkeeping around it.
    """
    from apps.ai.indexing import embed_record_summary

    job = _claim_job(self, record_id)
    try:
        outcome = embed_record_summary(record_id, skip_existing=skip_existing)
    except Exception as exc:
        _fail_job(job, exc)
        raise self.retry(exc=exc, countdown=60)

    _finish_job(job, outcome)
    return {
        "record_id": outcome.record_id,
        "space_id": outcome.space_id,
        "embedded": outcome.embedded,
        "skipped": outcome.skipped,
        "refused": outcome.refused,
        "reason": outcome.reason,
    }


@shared_task(bind=True, max_retries=3)
def embed_chunk_set(self, record_id: int, *, force: bool = False):
    """Embed the chunks of a record's active chunk set (IR-281).

    Separate from ``embed_record`` rather than folded into it: they write
    different tables, serve different stages of ADR-013's two-stage
    retrieval, and fail for different reasons. A record whose summary
    embedded fine and whose chunks did not is a state an operator needs to be
    able to see, and one task reporting one status cannot show it.
    """
    from apps.ai.indexing import embed_active_chunk_set

    try:
        outcome = embed_active_chunk_set(record_id, force=force)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)

    return {
        "record_id": outcome.record_id,
        "space_id": outcome.space_id,
        "embedded": outcome.embedded,
        "skipped": outcome.skipped,
        "refused": outcome.refused,
        "reason": outcome.reason,
    }


def _run_ingestion(self, extraction, force: bool) -> dict:
    """Chunk ``extraction`` and make the result the record's active chunk set.

    ``IngestionError`` is not retried: it means the extraction has no
    structure to chunk, which four more attempts will not change.
    """
    from apps.ai.ingestion.pipeline import IngestionError, ingest_extraction
    from apps.ai.repositories import DjangoChunkRepository

    try:
        outcome = ingest_extraction(
            extraction, repository=DjangoChunkRepository(), force=force
        )
    except IngestionError:
        raise
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)

    # A chunking run that wrote a new active chunk set leaves vectors owing,
    # and IR-281's whole point is that an upload reaches them with no manual
    # step. Queued rather than computed here: chunking runs on the `default`
    # queue and embedding is metered, so they belong on separate queues with
    # separate budgets. `embed_chunk_set` re-reads what is pending, so a
    # queued message that arrives after another worker has already embedded
    # the record costs one query and no vendor call.
    if outcome.wrote_anything:
        embed_chunk_set.delay(outcome.record_id)

    return {
        "record_id": outcome.record_id,
        "chunk_set_id": outcome.chunk_set_id,
        "chunk_count": outcome.chunk_count,
        "duplicate": outcome.duplicate,
        "unchanged": outcome.unchanged,
        "to_embed": outcome.to_embed,
        "reused": outcome.reused,
        "soft_deleted": outcome.soft_deleted,
    }


@shared_task(bind=True, max_retries=3)
def chunk_extraction(self, extraction_id: int, *, force: bool = False):
    """Chunk one extraction and make the result its record's active chunk set.

    Keyed on the extraction, not on the record or the upload it hangs off
    (IR-239). IR-195's two tasks were keyed on those, which made the
    manuscript/supplementary split a property of *which task you called* --
    and left a manuscript attached to an ``UploadSlot`` unreachable, since
    that row's ``record`` column is null. The caller decides what belongs in
    the corpus by reading ``PdfExtraction.kind``; this task's only job is to
    chunk what it is handed.
    """
    from apps.documents.models import PdfExtraction

    extraction = PdfExtraction.objects.filter(pk=extraction_id).first()
    if not extraction:
        return None  # deleted between the task being queued and running

    return _run_ingestion(self, extraction, force)


@shared_task
def metadata_extraction_task(document_id):
    pass

@shared_task
def embedding_generation_task(document_id):
    pass
