"""
IR-791, ADR-054 decision 10: the Contact person's AI answer a paper keeps.

One nullable column, no backfill. Every existing paper reads "no answer stored",
which the disclosure gate refuses, and the per-paper stamps (`dpa_accepted_at`)
stop counting (ADR-054 decision 17; IRIS isn't deployed, so no real paper is
affected). Test data answers Yes again through `seed_demo`, `load_corpus` and
`mark_corpus_cleared`.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('records', '0033_version_review_text'),
    ]

    operations = [
        migrations.AddField(
            model_name='record',
            name='ai_consent',
            field=models.BooleanField(blank=True, help_text="The Contact person's AI answer when this draft was created. Null means none stored; the gate refuses it.", null=True),
        ),
    ]
