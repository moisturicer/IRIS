from celery import shared_task
from django.utils import timezone


@shared_task(bind=True, max_retries=3)
def embed_record(self, record_id: int):
    from apps.ai.models import EmbeddingJob, RecordEmbedding
    from apps.records.models import Record
    from django.conf import settings

    job = EmbeddingJob.objects.filter(record_id=record_id).order_by("-created_at").first()
    if job:
        job.status = "running"
        job.celery_task_id = self.request.id
        job.save(update_fields=["status", "celery_task_id"])

    try:
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


@shared_task
def metadata_extraction_task(document_id):
    pass

@shared_task
def embedding_generation_task(document_id):
    pass
