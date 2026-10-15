"""Local deterministic HTTP fixtures for the IR-589 evaluation controls."""

import pytest

from apps.ai.models import VECTOR_COLUMN_DIMENSIONS
from apps.ai.models.embedding_space import EmbeddingSpace
from apps.ai.providers.fakes import DeterministicEmbeddingProvider


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
def client_for():
    from rest_framework.test import APIClient

    def client(user):
        result = APIClient()
        result.force_authenticate(user=user)
        return result

    return client
