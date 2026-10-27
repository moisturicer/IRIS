import pytest
from django.db import connection

from apps.ai.models import VECTOR_COLUMN_DIMENSIONS
from apps.ai.models.chunk import ChunkEmbedding
from apps.ai.models.embedding import RecordEmbedding
from apps.ai.models.embedding_space import EmbeddingSpace
from apps.ai.providers.fakes import DeterministicEmbeddingProvider
from apps.ai.tests.corpus import FLOOD_TEXT, POND_TEXT, make_record, make_user
from apps.records.models import Classification
from core.enums import PipelineStatus


def fresh_vector_indexes():
    # Rolled back with the test, so its vectors leave no dead HNSW entries.
    with connection.cursor() as cursor:
        cursor.execute(f"TRUNCATE {RecordEmbedding._meta.db_table}, {ChunkEmbedding._meta.db_table}")


@pytest.fixture
def space(db):
    fresh_vector_indexes()
    existing = EmbeddingSpace.objects.filter(state="active").first()
    if existing is not None:
        return existing
    return EmbeddingSpace.objects.create(
        model_id="fake-test", dimensions=VECTOR_COLUMN_DIMENSIONS,
        metric="cosine", state="active",
    )


@pytest.fixture
def embedder():
    return DeterministicEmbeddingProvider(dimensions=VECTOR_COLUMN_DIMENSIONS)


@pytest.fixture
def corpus(space, embedder):
    """Two public papers a student can read, and another user's draft."""
    area = Classification.objects.create(name="Engineering")
    student = make_user("student@cit.edu")
    other = make_user("other@cit.edu")
    public = make_record(title="Flood forecasting", text=FLOOD_TEXT,
                         embedder=embedder, space=space)
    public.classification = area
    public.year_completed = 2021
    public.save()
    draft = make_record(title="Secret flood draft", text=FLOOD_TEXT, embedder=embedder,
                        space=space, status=PipelineStatus.DRAFT, owner=other)
    draft.classification = area
    draft.save()
    pond = make_record(title="Tilapia ponds", text=POND_TEXT, embedder=embedder, space=space)
    return {"student": student, "other": other, "public": public,
            "draft": draft, "pond": pond}


@pytest.fixture
def ledger_passage():
    """A real current chunk behind synthetic synthesis passages (IR-597)."""
    import hashlib
    from apps.ai.models import DocumentChunk

    def add(run, record, text, score):
        chunk_set = record.chunk_sets.get(is_active=True)
        sequence = chunk_set.chunks.count()
        chunk = DocumentChunk.objects.create(
            chunk_set=chunk_set, record=record, sequence=sequence, max_sequence=sequence,
            text=text, content=text, text_hash=hashlib.sha256(text.encode()).hexdigest(),
            token_count=1, source_page=1,
        )
        return run.ledger.add_passage(
            record_id=record.pk, chunk_id=chunk.pk, chunk_set_hash=chunk_set.content_hash,
            record_title=record.title, text=text, page=1, context_path=(), score=score,
        )
    return add
