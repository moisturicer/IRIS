"""
Create each retention period's system setting, blank (ADR-051 decision 19, IR-794).

A settings PATCH never creates a key (IR-667), so the key has to exist before the
System Admin can set it. Blank is the only value created: a blank period erases
nothing, and no default period exists anywhere in code. A later retention type
adds its own migration.
"""
from django.db import migrations

KEYS = ["retention.download_notes_days"]


def create_blank(apps, schema_editor):
    SystemSetting = apps.get_model("accounts", "SystemSetting")
    for key in KEYS:
        SystemSetting.objects.get_or_create(key=key, defaults={"value": ""})


def remove(apps, schema_editor):
    apps.get_model("accounts", "SystemSetting").objects.filter(key__in=KEYS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0019_data_notice_and_answers"),
    ]

    operations = [
        migrations.RunPython(create_blank, remove),
    ]
