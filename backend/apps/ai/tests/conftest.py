"""Fixtures shared by the HTTP-boundary suites in this package.

Here rather than in one test module and imported by the other (IR-295): a
fixture imported by name is redefined by every test that requests it, which
flake8 reports as F811 on every signature. A conftest is how pytest shares a
fixture, and it keeps `test_ask_http.py` and `test_conversations_http.py`
driving the same corpus builder rather than two that drift.
"""

import pytest

from apps.ai.models import VECTOR_COLUMN_DIMENSIONS
from apps.ai.models.embedding_space import EmbeddingSpace
from apps.ai.providers.fakes import DeterministicEmbeddingProvider


@pytest.fixture
def space(db):
    """The one active space. A test may not create a second — the database
    constraint forbids it, and so does the property it exists to protect."""
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
    def _client(user):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=user)
        return client

    return _client
