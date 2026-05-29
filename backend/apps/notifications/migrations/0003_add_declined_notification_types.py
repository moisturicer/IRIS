from django.db import migrations

TYPES = [
    "Download Request Declined",
    "Delete Request Declined",
]


def seed(apps, schema_editor):
    NotificationType = apps.get_model("notifications", "NotificationType")
    for name in TYPES:
        NotificationType.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("notifications", "0002_seed_notification_types")]
    operations   = [migrations.RunPython(seed, migrations.RunPython.noop)]
