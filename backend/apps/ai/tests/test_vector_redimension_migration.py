"""Migration 0007 against a database that already holds vectors (IR-280).

Not only an empty one. An empty database is the case this migration was
*written* for — the ticket's whole argument is that no real vector exists
yet — and it is exactly the case that would have hidden the defect: a
stored 1536-vector cannot be cast into a 1024 column, and Postgres refuses
the whole ``ALTER`` with "expected 1024 dimensions, not 1536". Found by the
pre-existing 0003 and 0004 migration tests, which create such a row and
then migrate forward.

So the behaviour under test is the deliberate one: vectors belonging to a
superseded space are **deleted**, because a vector from a model IRIS no
longer calls is not comparable with one from the model it does, and
comparing them does not error — it returns rows, ranked plausibly, and
wrong.

Follows the same shape as ``test_embedding_space_migration.py``: Django's
``MigrationExecutor`` with historical model classes, ``transaction=True``
because the executor manages its own transactions, and a ``finally`` that
puts the database back on current history for the rest of the session.
"""

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.records.models import Record

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

_MIGRATE_FROM = [("ai", "0006_incremental_rechunk")]
_MIGRATE_TO = [("ai", "0007_one_embedding_space_at_1024")]


def column_dimensions(table: str, column: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT format_type(a.atttypid, a.atttypmod)
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            WHERE c.relname = %s AND a.attname = %s AND a.attnum > 0
            """,
            [table, column],
        )
        rendered = cursor.fetchone()[0]
    return int(rendered[len("vector(") : -1])


def test_migration_0007_redimensions_a_database_that_already_holds_a_vector():
    executor = MigrationExecutor(connection)
    old_apps = executor.loader.project_state(_MIGRATE_FROM).apps
    executor.migrate(_MIGRATE_FROM)

    try:
        assert column_dimensions("ai_recordembedding", "embedding") == 1536

        # Set the precondition here rather than leaning on what migration
        # 0003 seeded: this test runs in the `transaction=True` group, whose
        # earlier members truncate every table, so the seeded row may be gone
        # by the time it starts.
        OldEmbeddingSpace = old_apps.get_model("ai", "EmbeddingSpace")
        OldEmbeddingSpace.objects.all().delete()
        superseded = OldEmbeddingSpace.objects.create(
            model_id="text-embedding-3-small",
            dimensions=1536,
            metric="cosine",
            state="active",
        )

        record = Record.objects.create(title="A thesis embedded before ADR-015")
        old_apps.get_model("ai", "RecordEmbedding").objects.create(
            record_id=record.pk,
            embedding=[0.0] * 1536,
            model_name="text-embedding-3-small",
        )

        executor = MigrationExecutor(connection)
        executor.migrate(_MIGRATE_TO)
        new_apps = executor.loader.project_state(_MIGRATE_TO).apps

        assert column_dimensions("ai_recordembedding", "embedding") == 1024
        assert column_dimensions("ai_chunkembedding", "embedding") == 1024

        EmbeddingSpace = new_apps.get_model("ai", "EmbeddingSpace")
        active = EmbeddingSpace.objects.get(state="active")
        assert (active.model_id, active.dimensions) == ("voyage-context-4", 1024)

        assert (
            EmbeddingSpace.objects.get(pk=superseded.pk).state == "retired"
        ), "the superseded space stays on record rather than cascading"

        assert not new_apps.get_model("ai", "RecordEmbedding").objects.exists(), (
            "a vector the active space did not produce must not survive the "
            "re-dimension"
        )
        assert Record.objects.filter(pk=record.pk).exists(), (
            "only the derived vector is discarded, never the record"
        )
    finally:
        call_command("migrate", verbosity=0)
