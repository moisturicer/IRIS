"""Add `Turn.widened` (IR-298, ADR-026 §9).

False by default and false on every existing row: no Turn written before this
ticket could have been widened, because there was no widen control yet.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0010_turn_embedding"),
    ]

    operations = [
        migrations.AddField(
            model_name="turn",
            name="widened",
            field=models.BooleanField(default=False),
        ),
    ]
