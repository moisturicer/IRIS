from django.db import migrations

#: ADR-022 §3: the owner is told when documents are requested, and the
#: requesting party when every item has an upload (IR-262).
NAMES = ("Document Requested", "Document Request Fulfilled")


def seed(apps, schema_editor):
    NotificationType = apps.get_model("notifications", "NotificationType")
    for name in NAMES:
        NotificationType.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("notifications", "0004_add_record_advanced_type")]
    operations   = [migrations.RunPython(seed, migrations.RunPython.noop)]
