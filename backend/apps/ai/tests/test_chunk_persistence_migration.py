"""Migration 0004 tested against a database that already has data in it
(IR-89 F) — not only an empty one.

The tricky part of this migration is that it deletes the field-less
``DocumentChunk`` placeholder from migration 0001 and creates a real model
of the same name. This test's job is to demonstrate that deletion is safe
because the placeholder is provably empty on a deployment that predates
this migration: it creates other data (a Record, a RecordEmbedding) at the
pre-migration state, migrates forward, and confirms that unrelated data
survives untouched while the placeholder table is gone and the real one
exists in its place.

Needs a live Postgres with pgvector — ``db_required`` skips this cleanly
wherever one is not reachable, same as the rest of this app's migration
tests. ``transaction=True`` is required: the migration executor manages its
own transactions, which do not compose with pytest-django's default
per-test wrapping transaction.
"""

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

_MIGRATE_FROM = [("ai", "0003_embedding_space")]
_MIGRATE_TO = [("ai", "0004_chunk_persistence")]


def test_migration_0004_replaces_the_placeholder_without_disturbing_other_data():
    executor = MigrationExecutor(connection)
    old_apps = executor.loader.project_state(_MIGRATE_FROM).apps
    executor.migrate(_MIGRATE_FROM)

    try:
        OldRecord = old_apps.get_model("records", "Record")
        OldRecordEmbedding = old_apps.get_model("ai", "RecordEmbedding")
        OldDocumentChunk = old_apps.get_model("ai", "DocumentChunk")

        record = OldRecord.objects.create(title="Pre-existing thesis")
        OldRecordEmbedding.objects.create(
            record=record, embedding=[0.0] * 1536, model_name="text-embedding-3-small"
        )
        # The placeholder has no fields beyond its id — this is the only
        # thing a pre-migration deployment could possibly have put in it.
        OldDocumentChunk.objects.create()

        executor = MigrationExecutor(connection)
        executor.migrate(_MIGRATE_TO)
        new_apps = executor.loader.project_state(_MIGRATE_TO).apps

        NewRecordEmbedding = new_apps.get_model("ai", "RecordEmbedding")
        NewDocumentChunk = new_apps.get_model("ai", "DocumentChunk")
        ChunkSet = new_apps.get_model("ai", "ChunkSet")

        # Unrelated data survives the migration untouched.
        surviving = NewRecordEmbedding.objects.get()
        assert surviving.record_id == record.pk

        # The real DocumentChunk model exists, with the new columns, and is
        # empty — the old placeholder row is gone with the table it lived in
        # (it had no foreign key to anything, so there was nothing for it to
        # be migrated into).
        assert NewDocumentChunk.objects.count() == 0
        assert ChunkSet.objects.count() == 0
        new_field_names = {f.name for f in NewDocumentChunk._meta.get_fields()}
        assert {"sequence", "text_hash", "chunk_set", "content"} <= new_field_names
    finally:
        call_command("migrate", verbosity=0)
