from datetime import timedelta

from django.conf import settings
from django.db import migrations, models
from django.utils import timezone

STATUS_CHOICES = [
    ("pending", "Pending"), ("approved", "Approved"),
    ("declined", "Declined"), ("revoked", "Revoked"),
]


def grant_existing_approvals(apps, schema_editor):
    """Requests approved before grants existed get a full grant from today (ADR-048, decision 8)."""
    DownloadRequest = apps.get_model("records", "DownloadRequest")
    DownloadRequest.objects.filter(status="approved", grant_expires_at__isnull=True).update(
        grant_expires_at=timezone.now() + timedelta(days=settings.DOWNLOAD_GRANT_DAYS),
    )


class Migration(migrations.Migration):
    dependencies = [("records", "0021_record_research_metadata")]

    operations = [
        migrations.AddField(
            model_name="downloadrequest", name="grant_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="downloadrequest", name="status",
            field=models.CharField(choices=STATUS_CHOICES, default="pending", max_length=10),
        ),
        migrations.AlterField(
            model_name="deleterequest", name="status",
            field=models.CharField(choices=STATUS_CHOICES, default="pending", max_length=10),
        ),
        migrations.RunPython(grant_existing_approvals, migrations.RunPython.noop),
    ]
