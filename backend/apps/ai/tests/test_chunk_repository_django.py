"""Django-specific ChunkRepository behaviour that has no in-memory analogue
(IR-89 F): cascade deletion is a database-level guarantee, not something a
dict-backed fake can meaningfully demonstrate.

Needs a live Postgres — ``db_required`` skips these cleanly wherever one is
not reachable.
"""

import pytest

from apps.ai.chunking import Chunk, ChunkingOptions, ChunkSet, chunkset_hash
from apps.ai.models import EmbeddingSpace, EmbeddingSpaceState
from apps.ai.models.chunk import ChunkEmbedding, ChunkSet as ChunkSetModel, DocumentChunk
from apps.ai.repositories import DjangoChunkRepository
from apps.records.models import Record

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def _sample_chunk_set() -> ChunkSet:
    chunks = (Chunk(text="x", content="x", context_path=(), sequence=0, token_count=1),)
    return ChunkSet(
        chunks=chunks,
        strategy_id="fixed-window",
        options=ChunkingOptions(),
        content_hash=chunkset_hash(chunks),
    )


def test_deleting_a_record_cascades_to_its_chunk_sets_and_chunks():
    record = Record.objects.create(title="Cascade test")

    persisted = DjangoChunkRepository().save(
        record_id=record.id, extraction_hash="h", chunk_set=_sample_chunk_set()
    )
    assert ChunkSetModel.objects.filter(pk=persisted.id).exists()
    assert DocumentChunk.objects.filter(chunk_set_id=persisted.id).exists()

    record.delete()

    assert not ChunkSetModel.objects.filter(pk=persisted.id).exists()
    assert not DocumentChunk.objects.filter(chunk_set_id=persisted.id).exists()


def test_deleting_a_record_cascades_to_chunk_embeddings():
    record = Record.objects.create(title="Cascade test with a vector")
    persisted = DjangoChunkRepository().save(
        record_id=record.id, extraction_hash="h", chunk_set=_sample_chunk_set()
    )
    space = EmbeddingSpace.objects.create(
        model_id="voyage-context-4", dimensions=1024, state=EmbeddingSpaceState.ACTIVE
    )
    chunk = DocumentChunk.objects.get(chunk_set_id=persisted.id)
    embedding = ChunkEmbedding.objects.create(chunk=chunk, space=space, embedding=[0.0] * 1024)

    record.delete()

    assert not ChunkEmbedding.objects.filter(pk=embedding.pk).exists()


def test_replacing_a_chunk_set_also_removes_its_old_embeddings():
    """save() deletes the previous chunk set for a record before writing the
    new one — confirms that deletion actually reaches embeddings two joins
    away, not just the chunk_set/document_chunk tables directly."""
    record = Record.objects.create(title="Replacement test")
    repo = DjangoChunkRepository()
    first = repo.save(record_id=record.id, extraction_hash="h1", chunk_set=_sample_chunk_set())

    space = EmbeddingSpace.objects.create(
        model_id="voyage-context-4", dimensions=1024, state=EmbeddingSpaceState.ACTIVE
    )
    old_chunk = DocumentChunk.objects.get(chunk_set_id=first.id)
    old_embedding = ChunkEmbedding.objects.create(chunk=old_chunk, space=space, embedding=[0.0] * 1024)

    repo.save(record_id=record.id, extraction_hash="h2", chunk_set=_sample_chunk_set())

    assert not ChunkSetModel.objects.filter(pk=first.id).exists()
    assert not ChunkEmbedding.objects.filter(pk=old_embedding.pk).exists()
