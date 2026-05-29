"""Add the IERC (Institutional Ethics Review Committee) role to the Role table."""
from django.db import migrations


def add_ierc(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    Role.objects.get_or_create(name="IERC")


def remove_ierc(apps, schema_editor):
    apps.get_model("accounts", "Role").objects.filter(name="IERC").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_set_is_staff_for_staff_roles"),
    ]

    operations = [
        migrations.RunPython(add_ierc, remove_ierc),
    ]
