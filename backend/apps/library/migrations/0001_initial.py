import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("records", "0023_download_request_notes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SavedRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reading_status", models.CharField(blank=True, choices=[("want_to_read", "Want to read"), ("reading", "Reading"), ("completed", "Completed")], max_length=16, null=True)),
                ("saved_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="saved_records", to=settings.AUTH_USER_MODEL)),
                ("record", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="records.record")),
            ],
            options={
                "indexes": [models.Index(fields=["owner", "-saved_at"], name="library_saved_owner_idx")],
                "constraints": [models.UniqueConstraint(fields=("owner", "record"), name="unique_saved_record")],
            },
        ),
    ]
