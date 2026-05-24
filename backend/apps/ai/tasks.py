from celery import shared_task
from django.utils import timezone

from apps.ai.extractor import extract_text_from_pdf


@shared_task(bind=True, max_retries=3)
def extract_pdf_text(self, upload_id: int) -> str:
    """
    Background task: extract and clean text from an uploaded PDF file.

    Called automatically after a RecordUpload is saved.
    Stores the extracted text back on the RecordUpload instance so it
    can later be fed into the embedding pipeline.

    Args:
        upload_id: Primary key of the RecordUpload whose file should be parsed.

    Returns:
        The cleaned text string (also persisted to the DB).
    """
    from apps.documents.models import RecordUpload

    upload = RecordUpload.objects.get(pk=upload_id)
    file_path = upload.file.path  # absolute path on disk

    try:
        text = extract_text_from_pdf(file_path)

        # Persist extracted text if the model has an extracted_text field,
        # otherwise just return it for the caller / chained tasks to use.
        if hasattr(upload, "extracted_text"):
            upload.extracted_text = text
            upload.save(update_fields=["extracted_text"])

        return text

    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)



@shared_task(bind=True, max_retries=3)
def embed_record(self, record_id: int):
    """
    Generate and store the sentence-transformer embedding for one record.
    Updates EmbeddingJob status throughout.
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

        from sentence_transformers import SentenceTransformer
        model     = SentenceTransformer(settings.AI_EMBEDDING_MODEL)
        embedding = model.encode(text)

        RecordEmbedding.objects.update_or_create(
            record=record,
            defaults={
                "embedding":  pickle.dumps(embedding),
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
def embed_all_records():
    """Queue an embed_record task for every record that has no embedding yet."""
    from apps.records.models import Record
    from apps.ai.models import RecordEmbedding, EmbeddingJob

    missing_ids = Record.objects.exclude(
        pk__in=RecordEmbedding.objects.values_list("record_id", flat=True)
    ).values_list("pk", flat=True)

    for record_id in missing_ids:
        job = EmbeddingJob.objects.create(record_id=record_id)
        embed_record.delay(record_id)
