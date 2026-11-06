from django.db import migrations

TYPES = ["Embargo Review"]


def seed(apps, schema_editor):
    NotificationType = apps.get_model("notifications", "NotificationType")
    for name in TYPES:
        NotificationType.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("notifications", "0008_add_download_revoked_type")]
    operations   = [migrations.RunPython(seed, migrations.RunPython.noop)]
