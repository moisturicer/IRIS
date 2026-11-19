# Written for IR-666 (ADR-074 decision 4): a stored file that fails the
# one-time malware scan is taken out of use, and its uploader and RDCO are told.
#
# Seeds the one notice type. Reversing removes nothing it seeded: the type may
# already name sent notices, and deleting it would cascade to them.
from django.db import migrations

TYPES = ["File Quarantined"]


def seed(apps, schema_editor):
    NotificationType = apps.get_model("notifications", "NotificationType")
    for name in TYPES:
        NotificationType.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("notifications", "0013_comment_report_task")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
