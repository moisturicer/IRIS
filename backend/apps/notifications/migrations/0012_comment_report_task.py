# Written for IR-691: a notice that a comment was reported settles when its reports are handled (ADR-069).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0011_notification_task_and_resolution"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="task_kind",
            field=models.CharField(
                blank=True,
                choices=[
                    ("assignment", "An office's (or the Adviser's) turn at a record"),
                    ("seat", "One reviewer's seat"),
                    ("revision", "A revision request"),
                    ("document_request", "A document request"),
                    ("download_request", "A download request"),
                    ("delete_request", "A delete request"),
                    ("role_request", "A role request"),
                    ("comment_report", "A reported comment"),
                ],
                default="",
                max_length=20,
            ),
        ),
    ]
