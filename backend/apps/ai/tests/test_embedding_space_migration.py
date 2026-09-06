"""Migration 0003 tested against a database that already has data in it
(IR-109) — not only an empty one.

Rolls the database back to the migration just before EmbeddingSpace
existed, creates a Record and a RecordEmbedding the way they would already
exist on a deployment that predates it, then migrates forward and checks
that pre-existing row survived untouched and exactly one EmbeddingSpace
came out active.

Uses Django's own documented pattern for migration tests
(``MigrationExecutor`` plus historical model classes from
``project_state``), rather than asserting against the current ORM models —
the current ``Record``/``RecordEmbedding`` classes are not guaranteed to
match the schema as it existed at migration 0002, and a real migration test
has to use the models as they existed at that point in history.

Needs a live Postgres with pgvector — ``db_required`` skips this cleanly
wherever one is not reachable, same as the rest of the ``EmbeddingSpace``
suite. ``transaction=True`` is required here specifically: the migration
executor manages its own transactions, which do not compose with
pytest-django's default per-test wrapping transaction.

Note on ``Record``: this test rewinds **only the ``ai`` app**, so the
``records_record`` table stays at its latest schema throughout. The historical
``records.Record`` class from ``project_state`` therefore does *not* match that
table -- it predates ``records/0009``, whose ``requested_itso/ierc/ktto`` columns
are ``NOT NULL`` with the database default dropped after backfill, so an INSERT
through the historical class omits them and Postgres rejects the row. The
current model is the one that matches the live table, so unrelated fixture data
is created through it. This was latent from 2026-09-03 until IR-165 gave CI a
database and the suite actually ran.
"""

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.records.models import Record

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

_MIGRATE_FROM = [("ai", "0002_embeddingjob_recordembedding")]
_MIGRATE_TO = [("ai", "0003_embedding_space")]


def test_migration_0003_seeds_one_active_space_and_leaves_existing_record_embeddings_untouched():
    executor = MigrationExecutor(connection)
    old_apps = executor.loader.project_state(_MIGRATE_FROM).apps
    executor.migrate(_MIGRATE_FROM)

    try:
        OldRecordEmbedding = old_apps.get_model("ai", "RecordEmbedding")

        record = Record.objects.create(title="A pre-existing thesis")
        OldRecordEmbedding.objects.create(
            record_id=record.pk,
            embedding=[0.0] * 1536,
            model_name="text-embedding-3-small",
        )

        # Forward through 0003 — a fresh executor, since migrate() above
        # invalidated the loader's cached applied-migration state.
        executor = MigrationExecutor(connection)
        executor.migrate(_MIGRATE_TO)
        new_apps = executor.loader.project_state(_MIGRATE_TO).apps

        NewRecordEmbedding = new_apps.get_model("ai", "RecordEmbedding")
        EmbeddingSpace = new_apps.get_model("ai", "EmbeddingSpace")

        surviving = NewRecordEmbedding.objects.get()
        assert surviving.model_name == "text-embedding-3-small"
        assert surviving.record_id == record.pk

        active_spaces = EmbeddingSpace.objects.filter(state="active")
        assert active_spaces.count() == 1
        assert active_spaces.get().dimensions > 0
    finally:
        # The executor left the database mid-history; every other test in
        # this session needs it back on the real, current migration state.
        call_command("migrate", verbosity=0)
