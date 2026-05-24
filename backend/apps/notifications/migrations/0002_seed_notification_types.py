from django.db import migrations

TYPES = [
    "Role Request - Student",
    "Role Request - Adviser",
    "New Record (Proposal / Thesis)",
    "New Record (Project)",
    "Record Resubmission",
    "Role Request Approved",
    "Delete Request Submitted",
    "Delete Request Approved",
    "Download Request Submitted",
    "Download Request Approved",
    "Record Approved",
    "Record Declined",
]


def seed(apps, schema_editor):
    NotificationType = apps.get_model("notifications", "NotificationType")
    for name in TYPES:
        NotificationType.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("notifications", "0001_initial")]
    operations   = [migrations.RunPython(seed, migrations.RunPython.noop)]
