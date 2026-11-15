"""IR-691: readers report Comments, and RDCO or the System Admin act on them.

Additive and reversible: one new table, `records_commentreport`, with a
one-report-per-reader constraint and an index for the open-reports queue.
Nothing existing changes.
"""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("records", "0041_deleterequest_rdco_note"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CommentReport",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("spam", "Spam"),
                            ("harassment", "Harassment"),
                            ("off_topic", "Off-topic"),
                            ("other", "Other"),
                        ],
                        max_length=20,
                    ),
                ),
                ("note", models.TextField(blank=True, default="")),
                ("reported_text", models.TextField()),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("open", "Open"),
                            ("dismissed", "Dismissed"),
                            ("removed", "Closed by removal"),
                            (
                                "writer_deleted",
                                "Closed: the writer deleted the comment",
                            ),
                        ],
                        default="open",
                        max_length=20,
                    ),
                ),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "comment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reports",
                        to="records.publiccomment",
                    ),
                ),
                (
                    "reporter",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "resolved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["created_at", "pk"],
                "indexes": [
                    models.Index(
                        fields=["state", "comment"], name="comment_report_queue"
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("reporter__isnull", False)),
                        fields=("comment", "reporter"),
                        name="comment_report_one_per_reader",
                    )
                ],
            },
        ),
    ]
