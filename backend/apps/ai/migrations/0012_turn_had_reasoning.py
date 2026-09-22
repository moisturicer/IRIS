"""Add `Turn.had_reasoning` (IR-327).

False by default and false on every existing row: no Turn written before this
ticket's streaming reasoning channel existed could have carried reasoning.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0011_turn_widened"),
    ]

    operations = [
        migrations.AddField(
            model_name="turn",
            name="had_reasoning",
            field=models.BooleanField(default=False),
        ),
    ]
