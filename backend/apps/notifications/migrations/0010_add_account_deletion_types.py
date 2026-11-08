from django.db import migrations

# IR-785: a rejected account deletion, and an owner who became Contact person.
TYPES = ["Account Deletion Rejected", "Contact Person Changed"]


def seed(apps, schema_editor):
    NotificationType = apps.get_model("notifications", "NotificationType")
    for name in TYPES:
        NotificationType.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("notifications", "0009_add_embargo_review_type")]
    operations   = [migrations.RunPython(seed, migrations.RunPython.noop)]
