"""The chunk keyword index, its GIN index, its trigger and the first fill
(IR-393, ADR-033 §2).

The fill runs here so `migrate` never leaves the fallback reading an empty
column; the command is the same function, for a corpus loaded later.
"""

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import migrations

from apps.ai.keyword_index import (
    CREATE_TRIGGER_SQL,
    DROP_TRIGGER_SQL,
    backfill_chunk_keyword_index,
)


def fill_existing_chunks(apps, schema_editor):
    backfill_chunk_keyword_index()


def noop(apps, schema_editor):
    """Nothing to undo: reversing drops the column that holds the values."""


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0014_record_overview_cache"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentchunk",
            name="search_vector",
            field=SearchVectorField(editable=False, null=True),
        ),
        migrations.AddIndex(
            model_name="documentchunk",
            index=GinIndex(fields=["search_vector"], name="ai_chunk_search_gin_idx"),
        ),
        migrations.RunSQL(sql=CREATE_TRIGGER_SQL, reverse_sql=DROP_TRIGGER_SQL),
        migrations.RunPython(fill_existing_chunks, noop),
    ]
