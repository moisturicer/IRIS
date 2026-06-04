"""
Add 'parallel_review' to Record.pipeline_status choices.

This new status represents the phase where multiple reviewing offices
(IERC + KTTO for Thesis/Research; IERC + KTTO after ITSO for Project)
are working in parallel. It replaces the old sequential 'ktto_review' stage
for new submissions; 'ktto_review' is retained for backward compatibility with
any existing records.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("records", "0003_record_ip_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="record",
            name="pipeline_status",
            field=models.CharField(
                max_length=20,
                db_index=True,
                default="draft",
                choices=[
                    ("draft",           "Draft"),
                    ("adviser_review",  "Adviser Review"),
                    ("rdco_intake",     "RDCO Intake Review"),
                    ("itso_review",     "ITSO Review"),
                    ("parallel_review", "Parallel Office Review"),
                    ("ktto_review",     "KTTO Review"),
                    ("rdco_review",     "RDCO Final Review"),
                    ("published",       "Published"),
                    ("declined",        "Declined"),
                    ("rejected",        "Rejected"),
                    ("pending_delete",  "Pending Deletion"),
                ],
            ),
        ),
    ]
