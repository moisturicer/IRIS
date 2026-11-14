"""A chunk's keyword text, and the trigger that reads it first (IR-1102).

Null on every existing row, which the trigger reads as `content`, so no
existing keyword index changes and nothing is backfilled.
"""

from django.db import migrations, models

from apps.ai.keyword_index import (
    CREATE_KEYWORD_TEXT_TRIGGER_SQL,
    CREATE_TRIGGER_SQL,
    DROP_TRIGGER_SQL,
)


class Migration(migrations.Migration):

    dependencies = [
        ('ai', '0047_chunkset_trial_variant'),
    ]

    operations = [
        migrations.AddField(
            model_name='documentchunk',
            name='keyword_text',
            field=models.TextField(blank=True, default=None, null=True),
        ),
        migrations.RunSQL(
            sql=CREATE_KEYWORD_TEXT_TRIGGER_SQL,
            reverse_sql=DROP_TRIGGER_SQL + CREATE_TRIGGER_SQL,
        ),
    ]
