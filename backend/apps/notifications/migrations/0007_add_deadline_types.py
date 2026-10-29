from django.db import migrations

#: ADR-043 §7: in-app reminders before and on a due date, and the
#: coordinator's overdue escalation (IR-620, IR-621).
NAMES = ("Review Due Soon", "Review Due Today", "Review Overdue")


def seed(apps, schema_editor):
    NotificationType = apps.get_model("notifications", "NotificationType")
    for name in NAMES:
        NotificationType.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("notifications", "0006_add_document_rejected_type")]
    operations   = [migrations.RunPython(seed, migrations.RunPython.noop)]
