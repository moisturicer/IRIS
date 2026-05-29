from django.db import migrations


def seed(apps, schema_editor):
    NotificationType = apps.get_model("notifications", "NotificationType")
    NotificationType.objects.get_or_create(name="Record Advanced")


class Migration(migrations.Migration):
    dependencies = [("notifications", "0003_add_declined_notification_types")]
    operations   = [migrations.RunPython(seed, migrations.RunPython.noop)]
