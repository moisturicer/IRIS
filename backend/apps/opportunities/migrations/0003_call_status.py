# Written for IR-762: a Call's status with RDCO (ADR-050 decision 8).
#
# Every Call that exists when this ships is confirmed (decision 8's last
# bullet): the column is added with that default, which fills existing rows,
# and only then is the default changed to pending for new ones.
from django.db import migrations, models


STATUS_CHOICES = [
    ("pending", "Waiting for RDCO"),
    ("confirmed", "Confirmed"),
    ("rejected", "Rejected"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("opportunities", "0002_call_fields"),
    ]

    operations = [
        # Featured no longer moves a Call up the board (decision 12).
        migrations.AlterModelOptions(
            name="opportunity",
            options={"ordering": ["due_date", "id"], "verbose_name_plural": "opportunities"},
        ),
        migrations.AddField(
            model_name="opportunity",
            name="status",
            field=models.CharField(choices=STATUS_CHOICES, default="confirmed", max_length=16),
        ),
        migrations.AlterField(
            model_name="opportunity",
            name="status",
            field=models.CharField(choices=STATUS_CHOICES, default="pending", max_length=16),
        ),
        migrations.AddField(
            model_name="opportunity",
            name="review_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="opportunity",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
