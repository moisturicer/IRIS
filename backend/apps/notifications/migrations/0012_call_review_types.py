# Written for IR-762: an Adviser's Call waits for RDCO (ADR-050 decisions 8-11).
#
# Adds the `call_request` task kind, which binds RDCO's request notice to the
# Call so it settles once RDCO decides (ADR-069), and seeds the five notice
# types. Reversing removes nothing it seeded: a type may already name sent
# notices, and deleting it would cascade to them.
from django.db import migrations, models

TYPES = [
    "Call Request Submitted",
    "Call Confirmed",
    "Call Rejected",
    "Call Removed",
    "Call Request Lapsed",
]


def seed(apps, schema_editor):
    NotificationType = apps.get_model("notifications", "NotificationType")
    for name in TYPES:
        NotificationType.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("notifications", "0011_notification_task_and_resolution")]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="task_kind",
            field=models.CharField(
                blank=True, default="", max_length=20,
                choices=[
                    ("assignment", "An office's (or the Adviser's) turn at a record"),
                    ("seat", "One reviewer's seat"),
                    ("revision", "A revision request"),
                    ("document_request", "A document request"),
                    ("download_request", "A download request"),
                    ("delete_request", "A delete request"),
                    ("role_request", "A role request"),
                    ("call_request", "A Call waiting for RDCO"),
                ],
            ),
        ),
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
