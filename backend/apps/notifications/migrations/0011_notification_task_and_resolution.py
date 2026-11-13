from django.db import migrations, models


class Migration(migrations.Migration):
    """
    ADR-069 (IR-1075): a notification that asks for action can say when its
    task ended. Four additive columns, all nullable or blank, so no row needs
    rewriting: notifications sent before this have no task and are never
    resolved (they stay as they were).
    """

    dependencies = [
        ("notifications", "0010_add_account_deletion_types"),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="task_kind",
            field=models.CharField(
                blank=True, default="", max_length=20,
                choices=[
                    ("assignment", "An office's (or the Adviser's) turn at a record"),
                    ("seat", "One reviewer's seat"),
                    ("revision", "A revision request"),
                    ("document_request", "A document request"),
                    ("download_request", "A download request"),
                    ("delete_request", "A delete request"),
                    ("role_request", "A role request"),
                ],
            ),
        ),
        migrations.AddField(
            model_name="notification",
            name="task_id",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="notification",
            name="resolved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="notification",
            name="resolved_label",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
    ]
