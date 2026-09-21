"""The vector columns and the active EmbeddingSpace agree (IR-280).

This is the regression guard for a whole class of bug rather than for one
defect. A dimension mismatch between what a column stores and what the
active space says produced it does not raise anywhere: pgvector rejects the
*write*, and where a write does land, a query across two dimensionalities
returns rows, ranked plausibly, and wrong.

Before IR-280 there were three disagreeing declarations of one number —
``vector(1536)`` frozen into two migrations, ``AI_EMBEDDING_DIMENSIONS``
defaulting to 1536 in settings, and ``VOYAGE_EMBED_DIMENSIONS`` at 1024 for
the provider actually in scope (ADR-015). ``voyage-context-4`` offers 2048,
1024, 512 and 256; 1536 is not among them, so every write of a real vector
would have failed.

These tests read the **live database column**, not the model's declaration,
because the model reading the right constant is exactly the thing that was
already true and still produced the wrong column.
"""

import pytest
from django.db import connection

from apps.ai.models import (
    VECTOR_COLUMN_DIMENSIONS,
    ChunkEmbedding,
    RecordEmbedding,
    get_active_embedding_space,
)

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

#: Every table holding a vector, and the column that holds it.
VECTOR_COLUMNS = [
    (RecordEmbedding, "embedding"),
    (ChunkEmbedding, "embedding"),
]


def column_dimensions(model, column: str) -> int:
    """The dimension Postgres itself reports for a vector column.

    Read through ``format_type``, which renders the type modifier as
    ``vector(1024)``, rather than by trusting the Django field: the field
    and the column disagreeing is the defect under test.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT format_type(a.atttypid, a.atttypmod)
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            WHERE c.relname = %s AND a.attname = %s AND a.attnum > 0
            """,
            [model._meta.db_table, column],
        )
        row = cursor.fetchone()
    assert row is not None, f"{model._meta.db_table}.{column} does not exist"
    rendered = row[0]
    assert rendered.startswith("vector("), f"expected a vector column, got {rendered}"
    return int(rendered[len("vector(") : -1])


@pytest.mark.parametrize("model,column", VECTOR_COLUMNS)
def test_every_vector_column_matches_the_active_embedding_space(model, column):
    active = get_active_embedding_space()
    assert column_dimensions(model, column) == active.dimensions, (
        f"{model._meta.db_table}.{column} cannot hold a vector from the "
        f"active space {active.model_id!r}"
    )


@pytest.mark.parametrize("model,column", VECTOR_COLUMNS)
def test_every_vector_column_matches_what_the_model_declares(model, column):
    assert column_dimensions(model, column) == VECTOR_COLUMN_DIMENSIONS


def test_the_active_space_is_the_provider_in_scope():
    """ADR-015: Voyage, always, at its 1024-dimension default. A space naming
    a model IRIS does not call is a space no vector can be written under."""
    active = get_active_embedding_space()
    assert active.model_id == "voyage-context-4"
    assert active.dimensions == 1024
    assert active.metric == "cosine"
