"""Django-specific ChunkRepository behaviour that has no in-memory analogue
(IR-89 F): cascade deletion is a database-level guarantee, not something a
dict-backed fake can meaningfully demonstrate.

Needs a live Postgres — ``db_required`` skips these cleanly wherever one is
not reachable.
"""

import pytest
from django.conf import settings

from apps.ai.chunking import Chunk, ChunkingOptions, ChunkSet, chunkset_hash
from apps.ai.models import EmbeddingSpace, EmbeddingSpaceState
from apps.ai.models.chunk import ChunkEmbedding, ChunkSet as ChunkSetModel, DocumentChunk
from apps.ai.repositories import DjangoChunkRepository
from apps.records.models import Record

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def _no_seeded_active_space():
    """Migration 0003 seeds one active EmbeddingSpace on every fresh test
    database; the tests below that create their own active row would
    otherwise collide with it on the partial unique constraint."""
    EmbeddingSpace.objects.all().delete()


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
        model_id="voyage-context-4",
        dimensions=settings.AI_EMBEDDING_DIMENSIONS,
        state=EmbeddingSpaceState.ACTIVE,
    )
    chunk = DocumentChunk.objects.get(chunk_set_id=persisted.id)
    embedding = ChunkEmbedding.objects.create(
        chunk=chunk, space=space, embedding=[0.0] * settings.AI_EMBEDDING_DIMENSIONS
    )

    record.delete()

    assert not ChunkEmbedding.objects.filter(pk=embedding.pk).exists()


def test_superseding_a_chunk_set_retains_it_and_its_embeddings():
    """IR-89 F deleted the previous chunk set outright, and this test used
    to assert that. IR-115 replaces the behaviour deliberately: those
    vectors are exactly what makes the *next* re-chunk incremental, so a
    swap deactivates the old set instead of dropping it. Cascade deletion
    is still a real guarantee -- the two tests above are what cover it now.
    """
    record = Record.objects.create(title="Supersession test")
    repo = DjangoChunkRepository()
    first = repo.save(record_id=record.id, extraction_hash="h1", chunk_set=_sample_chunk_set())

    space = EmbeddingSpace.objects.create(
        model_id="voyage-context-4",
        dimensions=settings.AI_EMBEDDING_DIMENSIONS,
        state=EmbeddingSpaceState.ACTIVE,
    )
    old_chunk = DocumentChunk.objects.get(chunk_set_id=first.id)
    old_embedding = ChunkEmbedding.objects.create(
        chunk=old_chunk, space=space, embedding=[0.0] * settings.AI_EMBEDDING_DIMENSIONS
    )

    other_chunks = (Chunk(text="y", content="y", context_path=(), sequence=0, token_count=1),)
    repo.save(
        record_id=record.id,
        extraction_hash="h2",
        chunk_set=ChunkSet(
            chunks=other_chunks,
            strategy_id="fixed-window",
            options=ChunkingOptions(),
            content_hash=chunkset_hash(other_chunks),
        ),
    )

    assert ChunkSetModel.objects.get(pk=first.id).is_active is False
    assert ChunkEmbedding.objects.filter(pk=old_embedding.pk).exists()
