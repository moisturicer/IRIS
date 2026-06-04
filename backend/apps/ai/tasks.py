from celery import shared_task
from django.utils import timezone


@shared_task(bind=True, max_retries=3)
def embed_record(self, record_id: int):
    """
    Generate and store the vector embedding for one record.
    Updates EmbeddingJob status throughout.

    TODO (AI engineer — FR-M3-03 architecture change):
      Replace SentenceTransformer + pickle with a third-party embedding API call.

      Example using OpenAI (recommended — already a dependency):
        import openai
        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.embeddings.create(
            model=settings.AI_EMBEDDING_MODEL,   # e.g. "text-embedding-3-small"
            input=text,
        )
        vector = response.data[0].embedding      # list[float]

      Then store using pgvector VectorField (after updating RecordEmbedding model):
        RecordEmbedding.objects.update_or_create(
            record=record,
            defaults={"embedding": vector, "model_name": settings.AI_EMBEDDING_MODEL},
        )

      Remove when done:
        - sentence_transformers import and SentenceTransformer usage
        - pickle import and pickle.dumps()
        - numpy import (used in views.py too — remove from there as well)
    """
    from apps.ai.models import EmbeddingJob, RecordEmbedding
    from apps.records.models import Record
    from django.conf import settings
    import pickle

    job = EmbeddingJob.objects.filter(record_id=record_id).order_by("-created_at").first()
    if job:
        job.status = "running"
        job.celery_task_id = self.request.id
        job.save(update_fields=["status", "celery_task_id"])

    try:
        record = Record.objects.get(pk=record_id)
        text   = f"{record.title}. {record.abstract}"

        # TODO: replace the block below with third-party embedding API call (see docstring above)
        from sentence_transformers import SentenceTransformer
        model     = SentenceTransformer(settings.AI_EMBEDDING_MODEL)
        embedding = model.encode(text)

        RecordEmbedding.objects.update_or_create(
            record=record,
            defaults={
                "embedding":  pickle.dumps(embedding),   # TODO: replace with vector after pgvector migration
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
