"""EmbeddingSpace: the model and its two accessors (IR-109).

Needs Django and a live database — the partial unique constraint this
model relies on is enforced by Postgres, not by application code, so it can
only be demonstrated against a real database. Marked ``db_required``:
``conftest.py`` skips these cleanly wherever no database is reachable,
rather than reporting a pass it cannot back up.
"""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError

from apps.ai.models import (
    EmbeddingSpace,
    EmbeddingSpaceState,
    assert_embedding_space_consistent,
    get_active_embedding_space,
)

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def _no_seeded_active_space():
    """Migration 0003 seeds one active row from settings on every fresh
    database — correct for a real deployment bootstrapping itself, but every
    test below is exercising the active/retired invariant from a genuinely
    empty table. Clear it so the seed doesn't collide with a test's own
    ``state=active`` row or make "none is active" untrue before the test
    runs anything."""
    EmbeddingSpace.objects.all().delete()


def test_get_active_embedding_space_raises_when_none_is_active():
    with pytest.raises(ImproperlyConfigured):
        get_active_embedding_space()


def test_get_active_embedding_space_returns_the_active_row():
    EmbeddingSpace.objects.create(
        model_id="voyage-context-4",
        dimensions=1024,
        state=EmbeddingSpaceState.ACTIVE,
    )

    space = get_active_embedding_space()

    assert space.model_id == "voyage-context-4"
    assert space.dimensions == 1024


def test_a_retired_space_is_not_returned_as_active():
    EmbeddingSpace.objects.create(
        model_id="text-embedding-3-small", dimensions=1536, state=EmbeddingSpaceState.RETIRED
    )

    with pytest.raises(ImproperlyConfigured):
        get_active_embedding_space()


def test_multiple_retired_spaces_may_coexist():
    """Only 'active' is constrained to at most one row — history accumulates
    freely in 'retired', which is what makes a model change reversible
    rather than destructive."""
    EmbeddingSpace.objects.create(model_id="a", dimensions=100, state=EmbeddingSpaceState.RETIRED)
    EmbeddingSpace.objects.create(model_id="b", dimensions=200, state=EmbeddingSpaceState.RETIRED)

    assert EmbeddingSpace.objects.filter(state=EmbeddingSpaceState.RETIRED).count() == 2


def test_the_database_rejects_a_second_active_space():
    """The invariant this model exists to enforce must not be bypassable by
    application code — it is a database constraint, demonstrated here by
    trying to violate it directly through the ORM."""
    EmbeddingSpace.objects.create(model_id="a", dimensions=100, state=EmbeddingSpaceState.ACTIVE)

    with pytest.raises(IntegrityError):
        EmbeddingSpace.objects.create(model_id="b", dimensions=200, state=EmbeddingSpaceState.ACTIVE)


def test_assert_embedding_space_consistent_is_silent_when_dimensions_agree():
    EmbeddingSpace.objects.create(
        model_id="voyage-context-4", dimensions=1024, state=EmbeddingSpaceState.ACTIVE
    )

    assert_embedding_space_consistent(1024, context="indexing")  # must not raise


def test_assert_embedding_space_consistent_raises_on_a_dimension_mismatch():
    EmbeddingSpace.objects.create(
        model_id="voyage-context-4", dimensions=1024, state=EmbeddingSpaceState.ACTIVE
    )

    with pytest.raises(ImproperlyConfigured):
        assert_embedding_space_consistent(1536, context="indexing")


@pytest.mark.parametrize("context", ["indexing", "query"])
def test_assert_embedding_space_consistent_names_the_caller_in_the_error(context):
    """The error must say which side drifted, not just that a mismatch
    exists — that is what makes it actionable rather than a generic
    assertion failure."""
    EmbeddingSpace.objects.create(
        model_id="voyage-context-4", dimensions=1024, state=EmbeddingSpaceState.ACTIVE
    )

    with pytest.raises(ImproperlyConfigured, match=context):
        assert_embedding_space_consistent(1, context=context)


def test_assert_embedding_space_consistent_raises_when_no_space_is_active():
    with pytest.raises(ImproperlyConfigured):
        assert_embedding_space_consistent(1024, context="indexing")
