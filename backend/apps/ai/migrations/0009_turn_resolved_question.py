"""Add `Turn.resolved_question` (IR-296, ADR-026).

Blank by default and blank on every existing row, which is correct: no Turn
written before this ticket ever had a follow-up resolved against it, and
"blank" is exactly the wire's signal that resolution did not run or did not
change anything.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0008_conversations_and_turns"),
    ]

    operations = [
        migrations.AddField(
            model_name="turn",
            name="resolved_question",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
    ]
