"""Chunk persistence (IR-89 F): the chunk set, the chunk, and its vectors.

Three tables, mirroring the pure domain in ``apps.ai.chunking`` exactly —
this module has no logic of its own beyond schema. ``apps.ai.repositories``
is what translates between these rows and the frozen ``Chunk``/``ChunkSet``
value objects; a model here is a column layout, not a place to put behavior.

``DocumentChunk`` replaces a field-less placeholder from migration 0001 that
no code path ever wrote to (verified: nothing in the tree queries or creates
it). Its migration deletes and recreates the model outright rather than
adding fields to it — safe specifically because that placeholder never held
real data, and it avoids inventing meaningless defaults for columns (a
required foreign key among them) that only make sense given a real row to
have created it from.
"""

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from pgvector.django import HnswIndex, VectorField


class ChunkSet(models.Model):
    """One chunking of one record's extraction. The aggregate root.

    Chunks are never inserted or deleted individually — a chunk set is
    written whole, and ``ChunkRepository.save`` replaces any existing one
    for the record atomically. ``is_active`` exists for the schema to say
    so directly, enforced below by a database constraint rather than by
    application code that could be bypassed.
    """

    record = models.ForeignKey(
        "records.Record", on_delete=models.CASCADE, related_name="chunk_sets"
    )
    extraction_hash = models.CharField(max_length=64)
    strategy_id = models.CharField(max_length=100)
    options = models.JSONField()
    content_hash = models.CharField(max_length=64)
    page_sizes = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["record"],
                condition=models.Q(is_active=True),
                name="one_active_chunk_set_per_record",
            ),
        ]

    def __str__(self) -> str:
        return f"ChunkSet(record={self.record_id}, strategy={self.strategy_id!r}, active={self.is_active})"


class DocumentChunk(models.Model):
    """One retrievable unit of a document — the persisted form of
    ``apps.ai.chunking.Chunk``.

    ``text`` and ``content`` are both stored, deliberately duplicated: the
    first is exactly what a vector was computed from and must never change;
    the second is what a citation shows a reader. ``record`` is denormalized
    from ``chunk_set`` so stage-2 retrieval can filter chunks by record
    without a join back through ``ChunkSet``. ``max_sequence`` is
    denormalized onto every row so "chunk 12 of 47" is a read, not a second
    query — safe because a chunk set is immutable once written.
    """

    chunk_set = models.ForeignKey(ChunkSet, on_delete=models.CASCADE, related_name="chunks")
    record = models.ForeignKey(
        "records.Record", on_delete=models.CASCADE, related_name="document_chunks"
    )
    sequence = models.PositiveIntegerField()
    max_sequence = models.PositiveIntegerField()
    text = models.TextField()
    content = models.TextField()
    context_path = ArrayField(models.CharField(max_length=500), default=list, blank=True)
    text_hash = models.CharField(max_length=64, db_index=True)
    token_count = models.PositiveIntegerField()
    source_page = models.PositiveIntegerField(null=True, blank=True)
    element_kinds = ArrayField(models.CharField(max_length=30), default=list, blank=True)
    bboxes = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["chunk_set", "sequence"], name="unique_sequence_per_chunk_set"
            ),
        ]
        indexes = [
            # Stage 2 of retrieval filters candidate chunks by record, then
            # orders by sequence for neighbour expansion.
            models.Index(fields=["record", "sequence"], name="ai_chunk_record_seq_idx"),
        ]

    def __str__(self) -> str:
        return f"DocumentChunk(chunk_set={self.chunk_set_id}, sequence={self.sequence})"


class ChunkEmbedding(models.Model):
    """A chunk's vector under one embedding space.

    Keyed by chunk **and** space together — neither half alone is
    sufficient. Re-chunking invalidates vectors even when the model has not
    changed, and changing the model invalidates them even when the chunks
    have not.
    """

    chunk = models.ForeignKey(DocumentChunk, on_delete=models.CASCADE, related_name="embeddings")
    space = models.ForeignKey(
        "ai.EmbeddingSpace", on_delete=models.CASCADE, related_name="chunk_embeddings"
    )
    embedding = VectorField(dimensions=settings.AI_EMBEDDING_DIMENSIONS)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["chunk", "space"], name="unique_chunk_embedding_per_space"
            ),
        ]
        indexes = [
            HnswIndex(
                name="chunk_embedding_hnsw_idx",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self) -> str:
        return f"ChunkEmbedding(chunk={self.chunk_id}, space={self.space_id})"
