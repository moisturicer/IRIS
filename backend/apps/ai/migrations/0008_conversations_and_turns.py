"""Real Conversation, Turn and TurnCitation tables (IR-295, ADR-019).

The 0001 placeholders are deleted rather than grown into. They were
field-less and nothing ever wrote to them, so adding columns would mean
inventing defaults for a required foreign key on rows that cannot exist -
the reasoning migration 0004 gave for recreating `DocumentChunk`.

`ChatMessage` does not come back under that name; ADR-019 records why.

The reverse restores the placeholders, so the `ai` app can still be rewound.
No data is restored because none exists.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0007_one_embedding_space_at_1024"),
        ("records", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.DeleteModel(name="ChatMessage"),
        migrations.DeleteModel(name="Conversation"),
        migrations.CreateModel(
            name="Conversation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("title", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("record", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="ai_conversations", to="records.record")),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="ai_conversations", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-updated_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="Turn",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("question", models.TextField()),
                ("answer", models.TextField(blank=True)),
                ("state", models.CharField(max_length=20)),
                ("degraded", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("conversation", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="turns", to="ai.conversation")),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="TurnCitation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("marker", models.PositiveSmallIntegerField()),
                ("page", models.PositiveIntegerField(blank=True, null=True)),
                ("chunk", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+", to="ai.documentchunk")),
                ("record", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="+", to="records.record")),
                ("turn", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="citations", to="ai.turn")),
            ],
            options={
                "ordering": ["marker", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="conversation",
            index=models.Index(fields=["user", "-updated_at"],
                               name="ai_conversa_user_id_139fba_idx"),
        ),
        migrations.AddIndex(
            model_name="turn",
            index=models.Index(fields=["conversation", "id"],
                               name="ai_turn_convers_4f2fa8_idx"),
        ),
    ]
