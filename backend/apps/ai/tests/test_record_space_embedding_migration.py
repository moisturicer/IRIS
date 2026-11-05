"""Migration 0040 against a database that already holds Record vectors
(IR-752), not only an empty one.

Rewinds the ``ai`` app to just before the space-keyed table, builds the state a
deployment predating it has -- several records with legacy ``RecordEmbedding``
rows under the active model, one under a retired model, one under a model no
space knows -- then migrates forward and checks the expand step: every legacy
row survives untouched and every reader of it still finds it, matching vectors
are copied under the right space with no claimed text hash, and an unmatched
row is left only where it was. Then it rewinds and migrates again, because the
backfill must be repeatable.

``transaction=True`` for the reason ``test_embedding_space_migration`` gives:
the executor manages its own transactions.
"""

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.records.models import Record

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

_BEFORE = [("ai", "0039_chunkset_source_revision")]
_AFTER = [("ai", "0040_record_space_embedding")]


def _vector(seed):
    return [seed] + [0.0] * 1023


def test_the_backfill_copies_matching_vectors_and_leaves_the_legacy_table_alone():
    executor = MigrationExecutor(connection)
    old_apps = executor.loader.project_state(_BEFORE).apps
    executor.migrate(_BEFORE)

    try:
        Space = old_apps.get_model("ai", "EmbeddingSpace")
        Legacy = old_apps.get_model("ai", "RecordEmbedding")
        Space.objects.all().delete()
        retired = Space.objects.create(model_id="old-model", dimensions=1024,
                                       metric="cosine", state="retired")
        active = Space.objects.create(model_id="live-model", dimensions=1024,
                                      metric="cosine", state="active")
        pending = Space.objects.create(model_id="next-model", dimensions=1024,
                                       metric="cosine", state="pending")

        records = [Record.objects.create(title=f"Thesis {i}") for i in range(6)]
        rows = [
            (records[0], "live-model", 0.1), (records[1], "live-model", 0.2),
            (records[2], "live-model", 0.3), (records[3], "old-model", 0.4),
            (records[4], "next-model", 0.5), (records[5], "unknown-model", 0.6),
        ]
        for record, model, seed in rows:
            Legacy.objects.create(record_id=record.pk, embedding=_vector(seed), model_name=model)

        executor = MigrationExecutor(connection)
        executor.migrate(_AFTER)
        new_apps = executor.loader.project_state(_AFTER).apps

        NewLegacy = new_apps.get_model("ai", "RecordEmbedding")
        Keyed = new_apps.get_model("ai", "RecordSpaceEmbedding")

        assert NewLegacy.objects.count() == 6, "the legacy table is untouched"
        assert {(r.record_id, r.model_name) for r in NewLegacy.objects.all()} == {
            (rec.pk, model) for rec, model, _ in rows
        }

        copied = {k.record_id: (k.space_id, k.source_hash) for k in Keyed.objects.all()}
        assert copied == {
            records[0].pk: (active.pk, ""),
            records[1].pk: (active.pk, ""),
            records[2].pk: (active.pk, ""),
            records[3].pk: (retired.pk, ""),
        }, "a pending space is never a target, an unmatched model is not copied"
        assert pending.pk not in {k.space_id for k in Keyed.objects.all()}

        first = Keyed.objects.get(record_id=records[0].pk)
        assert list(first.embedding)[:2] == pytest.approx([0.1, 0.0])
    finally:
        call_command("migrate", verbosity=0)


def test_the_migration_rewinds_and_applies_again():
    executor = MigrationExecutor(connection)
    executor.migrate(_BEFORE)
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(_AFTER)
        executor = MigrationExecutor(connection)
        executor.migrate(_BEFORE)
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('ai_recordspaceembedding')")
            assert cursor.fetchone()[0] is None
    finally:
        call_command("migrate", verbosity=0)
