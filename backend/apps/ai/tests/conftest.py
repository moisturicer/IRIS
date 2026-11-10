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
from .grant_support import grant_db, grant_keys  # noqa: F401  shared fixtures (IR-717)


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


# -- two Embedding Spaces for the activation suites (IR-739) -----------------------
# An old (active) and a new (pending) identity; the suites build the pending one
# beside the live one, then promote and roll back. `activation_support` holds the
# plain builders; the fixtures live here so no test module redefines them.

ACTIVATION_OLD, ACTIVATION_NEW = "identity-old", "identity-new"


@pytest.fixture
def fresh_vector_indexes(db):
    """Start the HNSW indexes empty. Vectors rolled back by earlier tests stay in
    the graph until vacuumed and can fill a small scan before these rows are
    reached (the same reason the visibility suites truncate)."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("TRUNCATE ai_recordembedding, ai_recordspaceembedding, ai_chunkembedding")


@pytest.fixture
def active(fresh_vector_indexes):
    EmbeddingSpace.objects.all().delete()
    return EmbeddingSpace.objects.create(
        model_id=ACTIVATION_OLD, dimensions=VECTOR_COLUMN_DIMENSIONS, metric="cosine",
        state="active")


@pytest.fixture
def pending(active):
    return EmbeddingSpace.objects.create(
        model_id=ACTIVATION_NEW, dimensions=VECTOR_COLUMN_DIMENSIONS, metric="cosine",
        state="pending")


@pytest.fixture
def reader():
    from .corpus import make_user

    return make_user("activation-reader@cit.edu")
