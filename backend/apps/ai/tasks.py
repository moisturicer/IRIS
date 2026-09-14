from celery import shared_task
from django.utils import timezone


@shared_task(bind=True, max_retries=3)
def embed_record(self, record_id: int):
    from apps.ai.models import EmbeddingJob, RecordEmbedding, assert_embedding_space_consistent
    from apps.records.models import Record
    from django.conf import settings

    job = EmbeddingJob.objects.filter(record_id=record_id).order_by("-created_at").first()
    if job:
        job.status = "running"
        job.celery_task_id = self.request.id
        job.save(update_fields=["status", "celery_task_id"])

    try:
        # Fail loudly, before spending a vendor call, if this path's own
        # dimension has drifted from the active EmbeddingSpace (ADR-015).
        assert_embedding_space_consistent(
            settings.AI_EMBEDDING_DIMENSIONS, context="indexing"
        )

        record = Record.objects.get(pk=record_id)
        text   = f"{record.title}. {record.abstract}"

        # Phase 5: celery-embedding -> ai-gateway internal API
        import httpx
        url = f"{settings.AI_GATEWAY_URL}/api/v1/ai/internal/embed/"
        
        response = httpx.post(url, json={"text": text}, timeout=60.0)
        response.raise_for_status()
        vector = response.json().get("embedding")

        RecordEmbedding.objects.update_or_create(
            record=record,
            defaults={
                "embedding": vector,
                "model_name": settings.AI_EMBEDDING_MODEL,
            },
        )

        if job:
            job.status       = "done"
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "completed_at"])

    except Exception as exc:
        if job:
            job.status = "failed"
            job.error  = str(exc)
            job.save(update_fields=["status", "error"])
        raise self.retry(exc=exc, countdown=60)


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
