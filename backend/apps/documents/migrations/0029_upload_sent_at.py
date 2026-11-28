"""
IR-1322 (ADR-022 Amendment 8): an owner's upload to a submitted Record is held
until they send it. Every upload that exists now was sent when it was stored,
so nothing in flight is held or sent again (point 10).
"""

import django.utils.timezone
from django.db import migrations, models
from django.db.models import F


def mark_existing_sent(apps, schema_editor):
    RecordUpload = apps.get_model("documents", "RecordUpload")
    # AddField gave every row the migration's own time: each was sent when stored.
    RecordUpload.objects.update(sent_at=F("created_at"))


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0028_adviser_templates"),
    ]

    operations = [
        migrations.AddField(
            model_name="recordupload",
            name="sent_at",
            field=models.DateTimeField(blank=True, default=django.utils.timezone.now, null=True),
        ),
        migrations.RunPython(mark_existing_sent, migrations.RunPython.noop),
    ]
