"""
Seed RecordType rows (Proposal, Thesis / Research, Project).
"""
from django.db import migrations


RECORD_TYPES = ["Proposal", "Thesis / Research", "Project"]


def seed_record_types(apps, schema_editor):
    RecordType = apps.get_model("records", "RecordType")
    for name in RECORD_TYPES:
        RecordType.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("records", "0001_initial")]
    operations   = [migrations.RunPython(seed_record_types, migrations.RunPython.noop)]
