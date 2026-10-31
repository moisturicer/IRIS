from django.db import migrations

TYPES = ["Download Access Revoked"]


def seed(apps, schema_editor):
    NotificationType = apps.get_model("notifications", "NotificationType")
    for name in TYPES:
        NotificationType.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("notifications", "0007_add_deadline_types")]
    operations   = [migrations.RunPython(seed, migrations.RunPython.noop)]
