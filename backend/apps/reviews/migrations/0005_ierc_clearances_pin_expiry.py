"""
Migration: IERC support, parallel office clearances, PIN expiry.

Changes:
  1. Adds 'ierc' to Review.stage choices.
  2. Creates the RecordClearance table for parallel office tracking.
  3. Adds RecordAuthPin.expires_at (nullable DateTimeField).
     Existing rows get expires_at = created_at + 24 h so they remain valid.
"""
from django.conf import settings
from django.db import migrations, models
from datetime import timedelta
import django.db.models.deletion
import django.utils.timezone


def backfill_pin_expiry(apps, schema_editor):
    RecordAuthPin = apps.get_model("reviews", "RecordAuthPin")
    for pin in RecordAuthPin.objects.filter(expires_at__isnull=True):
        pin.expires_at = pin.created_at + timedelta(hours=24)
        pin.save(update_fields=["expires_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("reviews",  "0004_workflow_type_differentiated"),
        ("records",  "0004_pipeline_parallel_review"),
        ("accounts", "0006_seed_ierc_role"),
    ]

    operations = [
        # 1. Add 'ierc' to Review.stage choices (max_length already 20)
        migrations.AlterField(
            model_name="review",
            name="stage",
            field=models.CharField(
                max_length=20,
                db_index=True,
                choices=[
                    ("adviser",     "Adviser"),
                    ("rdco_intake", "RDCO Intake"),
                    ("itso",        "ITSO"),
                    ("ierc",        "IERC"),
                    ("ktto",        "KTTO"),
                    ("rdco",        "RDCO Final"),
                ],
            ),
        ),

        # 2. Create RecordClearance table
        migrations.CreateModel(
            name="RecordClearance",
            fields=[
                ("id",         models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("office",     models.CharField(
                    max_length=10,
                    choices=[("itso", "ITSO"), ("ierc", "IERC"), ("ktto", "KTTO")],
                )),
                ("status",     models.CharField(
                    max_length=10,
                    default="pending",
                    choices=[
                        ("pending",  "Pending"),
                        ("cleared",  "Cleared"),
                        ("declined", "Declined"),
                        ("rejected", "Rejected"),
                    ],
                )),
                ("comment",    models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("record",     models.ForeignKey(
                    to="records.Record",
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="clearances",
                )),
                ("reviewed_by", models.ForeignKey(
                    to=settings.AUTH_USER_MODEL,
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True,
                    related_name="clearances_given",
                )),
            ],
            options={"ordering": ["record", "office"]},
        ),
        migrations.AlterUniqueTogether(
            name="recordclearance",
            unique_together={("record", "office")},
        ),

        # 3. Add expires_at to RecordAuthPin
        migrations.AddField(
            model_name="recordauthpin",
            name="expires_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.RunPython(backfill_pin_expiry, migrations.RunPython.noop),
    ]
