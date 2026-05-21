from django.db import models


class RecordEmbedding(models.Model):
    """Stores the sentence-transformer embedding for a Record."""
    record     = models.OneToOneField("records.Record", on_delete=models.CASCADE, related_name="embedding")
    embedding  = models.BinaryField()          # pickled numpy array
    model_name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Embedding for record {self.record_id} ({self.model_name})"


class EmbeddingJob(models.Model):
    """
    Tracks the Celery embedding task status per record.
    Lets admins see which records have stale or missing embeddings.
    """
    STATUS = [
        ("queued",  "Queued"),
        ("running", "Running"),
        ("done",    "Done"),
        ("failed",  "Failed"),
    ]
    record       = models.ForeignKey("records.Record", on_delete=models.CASCADE, related_name="embedding_jobs")
    status       = models.CharField(max_length=10, choices=STATUS, default="queued", db_index=True)
    celery_task_id = models.CharField(max_length=200, blank=True)
    error        = models.TextField(blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"EmbeddingJob record={self.record_id} status={self.status}"
