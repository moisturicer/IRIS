"""
Migration: type-differentiated workflow routing.

Changes:
  1. Removes unique_together on Review(record, reviewed_by, stage) so the same
     reviewer can review the same stage multiple times across revision cycles.
  2. Increases Review.stage max_length 10 -> 20 to accommodate "rdco_intake".
  3. Increases Review.status max_length 10 -> 20 to match.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reviews", "0003_remove_recordauthpin_expires_at"),
    ]

    operations = [
        # 1. Drop the unique constraint so revision loops work correctly
        migrations.AlterUniqueTogether(
            name="review",
            unique_together=set(),
        ),
        # 2. Widen stage to fit "rdco_intake" (11 chars)
        migrations.AlterField(
            model_name="review",
            name="stage",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("adviser",     "Adviser"),
                    ("rdco_intake", "RDCO Intake"),
                    ("itso",        "ITSO"),
                    ("ktto",        "KTTO"),
                    ("rdco",        "RDCO Final"),
                ],
                db_index=True,
            ),
        ),
        # 3. Widen status to match
        migrations.AlterField(
            model_name="review",
            name="status",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("approved", "Approved"),
                    ("declined", "Declined"),
                    ("rejected", "Rejected"),
                ],
                db_index=True,
            ),
        ),
    ]
