"""
Migration: add ip_type field to Record for structured IP classification.

FR-M5-05 — RDCO/KTTO staff can tag published records with Patent, Copyright,
Trade Secret, or Utility Model labels, which are then filterable in browse.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("records", "0002_seed_record_types"),
    ]

    operations = [
        migrations.AddField(
            model_name="record",
            name="ip_type",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("patent",        "Patent"),
                    ("copyright",     "Copyright"),
                    ("trade_secret",  "Trade Secret"),
                    ("utility_model", "Utility Model"),
                ],
                blank=True,
                default="",
                db_index=True,
                help_text="Specific IP classification set by RDCO/KTTO after final review.",
            ),
        ),
    ]
