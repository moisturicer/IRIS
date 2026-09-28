"""Add `Turn.reasoning` (IR-381).

Blank on every existing row, which is honest rather than lossy: the reasoning
those Turns streamed was discarded as it arrived (IR-327), so there is nothing
to backfill. `had_reasoning` stays the only thing that can be said about them.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0015_chunk_keyword_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="turn",
            name="reasoning",
            field=models.TextField(blank=True),
        ),
    ]
