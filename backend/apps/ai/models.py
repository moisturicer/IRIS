from django.db import models


class RecordEmbedding(models.Model):
    """
    Stores the vector embedding for a Record.

    TODO (AI engineer — FR-M3-03 architecture change):
      Replace BinaryField with pgvector VectorField.

      Steps:
        1. pip install pgvector  (add to requirements/base.txt)
        2. Add 'pgvector' to INSTALLED_APPS in settings/base.py
        3. Replace the BinaryField below with:
             from pgvector.django import VectorField
             embedding = VectorField(dimensions=1536)   # match your provider's output dims
           (1536 = OpenAI text-embedding-3-small; adjust if using a different provider)
        4. Add HNSW index in a migration:
             from pgvector.django import HnswIndex
             class Meta:
                 indexes = [HnswIndex(fields=["embedding"], m=16, ef_construction=64,
                                      opclasses=["vector_cosine_ops"])]
        5. Remove the BinaryField migration and create a new one.
        6. Update embed_record task in tasks.py (see TODO there).
    """
    record     = models.OneToOneField("records.Record", on_delete=models.CASCADE, related_name="embedding")
    embedding  = models.BinaryField()          # TODO: replace with pgvector VectorField (see above)
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
