"""Additive: who wrote a reservation, and why (IR-725).

Existing rows are Django's. The AI runtime writes the same ledger.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ai", "0037_reader_session_reads")]
    operations = [
        migrations.AddField(
            model_name="providerreservation", name="owner",
            field=models.CharField(default="django", db_default="django", max_length=16),
        ),
        migrations.AddField(
            model_name="providerreservation", name="purpose",
            field=models.CharField(blank=True, default="", db_default="", max_length=32),
        ),
        migrations.AddField(
            model_name="providerreservation", name="purpose_version",
            field=models.CharField(blank=True, default="", db_default="", max_length=64),
        ),
    ]
