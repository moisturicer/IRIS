"""Add the System Admin role (ADR-051 §1, IR-781)."""
from django.db import migrations


def add_system_admin(apps, schema_editor):
    apps.get_model("accounts", "Role").objects.get_or_create(name="System Admin")


def remove_system_admin(apps, schema_editor):
    apps.get_model("accounts", "Role").objects.filter(name="System Admin").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0017_request_status_cancelled"),
    ]

    operations = [
        migrations.RunPython(add_system_admin, remove_system_admin),
    ]
