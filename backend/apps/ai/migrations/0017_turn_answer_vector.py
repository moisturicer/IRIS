"""A Turn carries two vectors, not one (IR-447, ADR-026 §7 as amended).

`kind` tells them apart, and the per-space uniqueness constraint widens to
include it -- without that, writing the answer vector would collide with the
question vector already stored for the same Turn and space.

**Existing rows need no data migration.** Every `TurnEmbedding` written
before this migration is a question vector, which is exactly what the
column's default says, so the backfill is the default itself. Answer vectors
appear only for Turns recorded after this ships; a Conversation that predates
it keeps working and recalls on questions alone, which is the behaviour it
was written under.

The constraint is dropped *before* the column is added, because the
replacement constraint names a column that does not exist yet.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0016_turn_reasoning"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="turnembedding",
            name="unique_turn_embedding_per_space",
        ),
        migrations.AddField(
            model_name="turnembedding",
            name="kind",
            field=models.CharField(
                choices=[("question", "Question"), ("answer", "Answer")],
                default="question",
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="turnembedding",
            constraint=models.UniqueConstraint(
                fields=("turn", "space", "kind"),
                name="unique_turn_vector_per_space_and_kind",
            ),
        ),
    ]
