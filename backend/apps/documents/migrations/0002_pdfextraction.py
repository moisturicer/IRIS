import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PdfExtraction",
            fields=[
                ("id",             models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("upload",         models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="pdf_extraction", to="documents.recordupload")),
                ("status",         models.CharField(choices=[("queued", "Queued"), ("running", "Running"), ("done", "Done"), ("failed", "Failed")], db_index=True, default="queued", max_length=10)),
                ("extracted_text", models.TextField(blank=True)),
                ("celery_task_id", models.CharField(blank=True, max_length=200)),
                ("error",          models.TextField(blank=True)),
                ("created_at",     models.DateTimeField(auto_now_add=True)),
                ("completed_at",   models.DateTimeField(null=True, blank=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
