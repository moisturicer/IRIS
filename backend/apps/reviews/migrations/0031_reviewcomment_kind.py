"""
A review comment is discussion or a thread (ADR-032 §7 as amended 2026-11-16,
IR-1194). Every existing row starts as a thread, as it was; `0032` returns
the ones nobody treated as a review item to Conversation.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reviews", "0030_backfill_reply_parties"),
    ]

    operations = [
        migrations.AddField(
            model_name="reviewcomment",
            name="kind",
            field=models.CharField(
                choices=[("discussion", "Discussion"), ("thread", "Thread")],
                default="thread", max_length=12,
            ),
        ),
    ]
