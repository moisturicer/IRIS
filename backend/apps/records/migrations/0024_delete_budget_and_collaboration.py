"""
IR-775: drop models no API, screen, import path or seed ever used.

Irreversible for any rows they hold. Nothing in the application writes them.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("records", "0023_download_request_notes"),
    ]

    operations = [
        migrations.DeleteModel(name="Budget"),
        migrations.DeleteModel(name="BudgetType"),
        migrations.DeleteModel(name="Collaboration"),
        migrations.DeleteModel(name="CollaborationType"),
    ]
