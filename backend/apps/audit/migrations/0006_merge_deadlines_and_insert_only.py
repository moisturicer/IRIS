from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0005_alter_auditevent_event_type"),
        ("audit", "0005_auditevent_insert_only"),
    ]

    operations = []
