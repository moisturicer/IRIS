from django.db import migrations

#: ADR-022 §3.4: the owner is told when the requesting party rejects an
#: upload, and why (IR-263).
NAMES = ("Document Rejected",)


def seed(apps, schema_editor):
    NotificationType = apps.get_model("notifications", "NotificationType")
    for name in NAMES:
        NotificationType.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("notifications", "0005_add_document_request_types")]
    operations   = [migrations.RunPython(seed, migrations.RunPython.noop)]
