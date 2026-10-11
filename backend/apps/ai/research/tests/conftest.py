import pytest

from apps.ai.models import VECTOR_COLUMN_DIMENSIONS
from apps.ai.models.embedding_space import EmbeddingSpace
from apps.ai.providers.fakes import DeterministicEmbeddingProvider
from apps.ai.tests.corpus import FLOOD_TEXT, POND_TEXT, make_record, make_user
from apps.records.models import Classification
from core.enums import PipelineStatus


@pytest.fixture
def space(db):
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
