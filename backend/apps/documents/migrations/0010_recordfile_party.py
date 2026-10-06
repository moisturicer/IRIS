"""
IR-476: a supplementary file belongs to the office that filed it.

Adds `RecordFile.party` and fills existing rows from the uploader's *current*
role (decision 7). The mapping is written out here rather than imported from
`apps.reviews.tracker`, so a later change to who staffs what cannot rewrite
what this migration did. RDCO maps to `rdco`, never `intake`. A row whose
uploader is gone or is not an office stays null, and only the superuser can
remove it, in Django admin.
"""

from django.db import migrations, models

ROLE_TO_PARTY = {
    "ITSO": "itso",
    "IERC": "ierc",
    "KTTO": "ktto",
    "RDCO": "rdco",
}


def fill_party(apps, schema_editor):
    RecordFile = apps.get_model("documents", "RecordFile")
    for role_name, party in ROLE_TO_PARTY.items():
        RecordFile.objects.filter(
            party__isnull=True, uploaded_by__role__name=role_name,
        ).update(party=party)


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0009_document_request_decisions"),
        # The backfill reads `User.role`; every office role exists from here.
        ("accounts", "0006_seed_ierc_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="recordfile",
            name="party",
            field=models.CharField(
                blank=True, null=True, max_length=20,
                choices=[
                    ("adviser", "Adviser"), ("intake", "Intake & Triage"), ("itso", "ITSO"),
                    ("ierc", "IERC"), ("ktto", "KTTO"), ("rdco", "RDCO Final"),
                ],
            ),
        ),
        # Reversing drops the column, so there is nothing to undo here.
        migrations.RunPython(fill_party, migrations.RunPython.noop),
    ]
