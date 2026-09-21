"""Re-dimension every vector column to the active EmbeddingSpace (IR-280).

Both vector columns were ``vector(1536)``, a literal frozen into migration
0002 and then copied into 0004 — the exact hardcoding ADR-015 introduced
``EmbeddingSpace`` to remove, reintroduced by the newer migration.
``voyage-context-4`` emits 2048, 1024, 512 or 256 dimensions. **1536 is not
among them**, so every write of a real vector would have failed.

**Why the column width is derived from the space row rather than written as
a literal.** A literal here is a fourth opinion about one number, and the
third one is what this migration exists to delete. So the data step writes
the space first, and the schema step reads the width back off it: there is
exactly one place in this file that says 1024, and it says it about the
space, not about a column.

**Why the old space is retired rather than deleted.** ``ChunkEmbedding``
points at a space with ``on_delete=CASCADE``, so deleting a space deletes
its vectors. That is safe today only because the chunk vector table has
never been written to — which is a fact about right now, not a property of
this migration. Retiring is correct whether or not vectors exist, and the
state machine already has the state for it.

**This migration discards vectors, and has to.** A stored 1536-vector
cannot be cast into a 1024 column — Postgres refuses with "expected 1024
dimensions, not 1536" — and even if it could, a vector produced by a model
IRIS no longer calls is not comparable with one produced by the model it
does. Keeping it would mean ranking across two embedding spaces, which does
not error; it returns rows, ranked plausibly, and wrong. So every vector
belonging to a superseded space is deleted before the columns are resized.
That is safe in the sense that matters — a vector is derived data, and
re-embedding recomputes it.

**What the reverse does and does not do.** It restores the *schema*: the
columns go back to the 1536 that migrations 0002 and 0004 created them at,
and the space 0003 seeded becomes active again. It does not bring the
vectors back — nothing can, and re-embedding is the only way to have them
again. The reverse is written rather than omitted because rewinding the
`ai` app is how this repo tests its own migrations, and an irreversible
step in the middle of the history makes every one of those tests
impossible. Each reverse below names exactly what it restores and where
that value comes from; none of them guess.

**Why this is cheap today.** Neither table holds a row on any real
deployment, so in practice nothing is discarded at all. After IR-281 embeds
a corpus, the same change would cost a full re-index, which is why this is
sequenced ahead of it.
"""

import pgvector.django.indexes
import pgvector.django.vector
from django.db import migrations

#: ADR-015's decision, as data: Voyage, always, at its default output
#: dimension. Written here as a literal because a migration is a record of a
#: decision taken at a point in time — reading live settings would let a
#: later environment change silently rewrite this history, and the schema
#: would follow it without a migration.
_ACTIVE_MODEL_ID = "voyage-context-4"
_ACTIVE_DIMENSIONS = 1024
_ACTIVE_METRIC = "cosine"

#: What migration 0003 seeded, repeated here because the reverse has to name
#: the row it reactivates. Kept in step with 0003 by being a frozen literal in
#: both places — the value is history in both files and cannot drift.
_SEEDED_BY_0003_MODEL_ID = "text-embedding-3-small"

#: Every vector column, as (model name, column) — both of them, named once
#: so the resize cannot be applied to one and forgotten on the other.
_VECTOR_COLUMNS = [
    ("RecordEmbedding", "embedding"),
    ("ChunkEmbedding", "embedding"),
]


def adopt_voyage_space(apps, schema_editor):
    """Make the Voyage space the active one, retiring whatever held the slot.

    Idempotent: re-running finds the Voyage row already active and changes
    nothing. The retire-then-activate order matters — the partial unique
    index permits only one active row, so activating first would fail.
    """
    EmbeddingSpace = apps.get_model("ai", "EmbeddingSpace")

    # The exclusion has to name every field `get_or_create` keys on. Naming
    # fewer would leave an active row that is neither retired here nor matched
    # below — say `voyage-context-4`/1024 under a different metric — and the
    # insert would then trip the one-active-space index.
    EmbeddingSpace.objects.filter(state="active").exclude(
        model_id=_ACTIVE_MODEL_ID,
        dimensions=_ACTIVE_DIMENSIONS,
        metric=_ACTIVE_METRIC,
    ).update(state="retired")

    space, created = EmbeddingSpace.objects.get_or_create(
        model_id=_ACTIVE_MODEL_ID,
        dimensions=_ACTIVE_DIMENSIONS,
        metric=_ACTIVE_METRIC,
        defaults={"state": "active"},
    )
    if not created and space.state != "active":
        space.state = "active"
        space.save(update_fields=["state"])


#: The width migrations 0002 and 0004 created the vector columns at, and so
#: the width the reverse restores. Not an arbitrary number and not derived
#: from nothing: it is the recorded prior state of this schema, which is the
#: only thing a reverse migration is entitled to put back.
_PREVIOUS_DIMENSIONS = 1536


def _resize(apps, schema_editor, model_name: str, column: str, *, to: int) -> None:
    table = apps.get_model("ai", model_name)._meta.db_table
    schema_editor.execute(
        f'ALTER TABLE "{table}" '
        f'ALTER COLUMN "{column}" TYPE vector({int(to)}) '
        f'USING "{column}"::vector({int(to)})'
    )


def restore_previous_space(apps, schema_editor):
    """Retire the Voyage space and reactivate the one migration 0003 seeded.

    Identified by 0003's own frozen values rather than by "whichever space
    was retired first", which on a database with earlier retired spaces
    would silently reactivate the wrong one. If that row is gone, nothing
    is left active — the loud failure ``get_active_embedding_space`` exists
    to raise, which is the right outcome for a database nobody can name an
    embedding space for.
    """
    EmbeddingSpace = apps.get_model("ai", "EmbeddingSpace")
    EmbeddingSpace.objects.filter(
        model_id=_ACTIVE_MODEL_ID,
        dimensions=_ACTIVE_DIMENSIONS,
        metric=_ACTIVE_METRIC,
    ).update(state="retired")
    EmbeddingSpace.objects.filter(
        model_id=_SEEDED_BY_0003_MODEL_ID, dimensions=_PREVIOUS_DIMENSIONS
    ).update(state="active")


def discard_superseded_vectors(apps, schema_editor):
    """Delete every vector that the active space did not produce.

    ``ChunkEmbedding`` names its space, so "superseded" is a question the
    row can answer. ``RecordEmbedding`` does not — it predates
    ``EmbeddingSpace`` and carries only a free-text ``model_name`` — so
    every row of it is by definition from before the space existed, and
    none can be claimed by the space now becoming active.
    """
    EmbeddingSpace = apps.get_model("ai", "EmbeddingSpace")
    active = EmbeddingSpace.objects.get(state="active")

    apps.get_model("ai", "ChunkEmbedding").objects.exclude(space=active).delete()
    apps.get_model("ai", "RecordEmbedding").objects.all().delete()


def keep_the_vectors_deleted(apps, schema_editor):
    """The reverse of a deletion, which is nothing.

    Named rather than left as ``RunPython.noop`` so that reading the
    operations list shows this migration is lossy in one direction: going
    back gets the schema, not the vectors.
    """


def restore_previous_width(apps, schema_editor):
    """Put the columns back to the width 0002 and 0004 created them at."""
    for model_name, column in _VECTOR_COLUMNS:
        _resize(apps, schema_editor, model_name, column, to=_PREVIOUS_DIMENSIONS)


def resize_to_active_space(apps, schema_editor):
    """Set every vector column to the width the *active space* declares.

    Narrowing, on every database this will actually run against — the name
    says resize rather than widen because 1536 → 1024 is the whole point.

    Reading it back off the row rather than taking the constant above is
    the point of the exercise: if a deployment has some other space active,
    this migration sizes the columns for that one and the startup assertion
    in ``assert_embedding_space_consistent`` is what will then object —
    loudly, and about the real disagreement.
    """
    EmbeddingSpace = apps.get_model("ai", "EmbeddingSpace")
    width = EmbeddingSpace.objects.get(state="active").dimensions
    for model_name, column in _VECTOR_COLUMNS:
        _resize(apps, schema_editor, model_name, column, to=width)


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0006_incremental_rechunk"),
    ]

    operations = [
        migrations.RunPython(adopt_voyage_space, restore_previous_space),
        # Before the columns narrow, not after: the cast is what fails on a
        # stored 1536-vector.
        migrations.RunPython(discard_superseded_vectors, keep_the_vectors_deleted),
        # The HNSW indexes are dropped and rebuilt around the type change:
        # an index is built over a type, and pgvector will not carry one
        # across a change of dimension.
        migrations.RemoveIndex(model_name="recordembedding", name="embedding_hnsw_idx"),
        migrations.RemoveIndex(
            model_name="chunkembedding", name="chunk_embedding_hnsw_idx"
        ),
        migrations.SeparateDatabaseAndState(
            # The database side derives the width from the space row; the
            # state side reuses the constant above, because Django's
            # autodetector compares model state to migration state and
            # cannot run a query to do it. A drift between that and the
            # model's own `VECTOR_COLUMN_DIMENSIONS` shows up as a pending
            # migration; a drift from the live column shows up in
            # `test_vector_dimensions.py`.
            database_operations=[
                migrations.RunPython(
                    resize_to_active_space, restore_previous_width
                ),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="recordembedding",
                    name="embedding",
                    field=pgvector.django.vector.VectorField(
                        dimensions=_ACTIVE_DIMENSIONS
                    ),
                ),
                migrations.AlterField(
                    model_name="chunkembedding",
                    name="embedding",
                    field=pgvector.django.vector.VectorField(
                        dimensions=_ACTIVE_DIMENSIONS
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="recordembedding",
            index=pgvector.django.indexes.HnswIndex(
                ef_construction=64,
                fields=["embedding"],
                m=16,
                name="embedding_hnsw_idx",
                opclasses=["vector_cosine_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="chunkembedding",
            index=pgvector.django.indexes.HnswIndex(
                ef_construction=64,
                fields=["embedding"],
                m=16,
                name="chunk_embedding_hnsw_idx",
                opclasses=["vector_cosine_ops"],
            ),
        ),
    ]
