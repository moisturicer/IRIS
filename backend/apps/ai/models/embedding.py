from django.db import models
from pgvector.django import VectorField, HnswIndex

from .embedding_space import VECTOR_COLUMN_DIMENSIONS

class RecordEmbedding(models.Model):
    record     = models.OneToOneField("records.Record", on_delete=models.CASCADE, related_name="embedding")
    embedding  = VectorField(dimensions=VECTOR_COLUMN_DIMENSIONS)
    model_name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            HnswIndex(
                name="embedding_hnsw_idx",
                fields=["embedding"], 
                m=16, 
                ef_construction=64,
                opclasses=["vector_cosine_ops"]
            )
        ]

    def __str__(self):
        return f"Embedding for record {self.record_id} ({self.model_name})"


class RecordSpaceEmbedding(models.Model):
    """A Record's title-and-abstract vector under one Embedding Space (IR-752).

    ``RecordEmbedding`` holds one row per record with no space key, so a second
    space could not hold a summary vector without overwriting the live one.
    This is the expand half of ADR-049 §23's expand-and-contract: it sits
    beside the legacy table, ``ChunkEmbedding``'s ``(chunk, space)`` identity
    mirrored at record level, and nothing reads it yet. The readers still use
    ``RecordEmbedding``; IR-739 moves them, each naming the active space.

    ``source_hash`` is the SHA-256 of the exact text that was embedded, so a
    changed title or abstract is visible as a stale vector. Rows copied from
    the legacy table carry ``""``: the text they were computed from is not
    recorded anywhere, and claiming the current text's hash would be a
    freshness the table cannot give.
    """

    record = models.ForeignKey(
        "records.Record", on_delete=models.CASCADE, related_name="space_embeddings"
    )
    space = models.ForeignKey(
        "ai.EmbeddingSpace", on_delete=models.CASCADE, related_name="record_embeddings"
    )
    embedding = VectorField(dimensions=VECTOR_COLUMN_DIMENSIONS)
    source_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["record", "space"], name="unique_record_embedding_per_space"
            ),
        ]
        indexes = [
            HnswIndex(
                name="record_space_embedding_hnsw_idx",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self):
        return f"RecordSpaceEmbedding(record={self.record_id}, space={self.space_id})"


class EmbeddingJob(models.Model):
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
