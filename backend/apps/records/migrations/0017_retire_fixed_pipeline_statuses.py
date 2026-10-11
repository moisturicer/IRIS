"""IR-274: remove the fixed pipeline's statuses from `Record.pipeline_status`.

`reviews.0014` (IR-260) moved every record holding one of these six values to
`in_review`. This migration only narrows the field's choices, and first refuses,
naming the rows, if any record -- or any delete request's remembered status --
still holds one: a value outside the vocabulary would read as a raw string and
match no workflow rule. Nothing is rewritten here; resolve such a row by hand,
or apply `reviews.0014`'s cutover first. The choices change is reversible.
"""

from django.db import migrations, models


RETIRED = (
    "adviser_review", "rdco_intake", "itso_review", "parallel_review",
    "rdco_review", "declined",
)


def refuse_retired_statuses(apps, schema_editor):
    Record = apps.get_model("records", "Record")
    DeleteRequest = apps.get_model("records", "DeleteRequest")
    records = list(
        Record.objects.filter(pipeline_status__in=RETIRED)
        .order_by("pk").values_list("pk", "pipeline_status")
    )
    requests = list(
        DeleteRequest.objects.filter(previous_pipeline_status__in=RETIRED)
        .order_by("pk").values_list("pk", "previous_pipeline_status")
    )
    if records or requests:
        raise RuntimeError(
            "IR-274 cannot remove the fixed pipeline's statuses while rows hold "
            f"them. Records: {records}. Delete requests: {requests}. Apply "
            "reviews.0014's cutover (IR-260) or resolve each row by hand first."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("records", "0016_record_details_edited_at"),
        ("reviews", "0015_alter_recordassignment_party_and_more"),
    ]

    operations = [
        migrations.RunPython(refuse_retired_statuses, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="record",
            name="pipeline_status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"), ("in_review", "In Review"),
                    ("approved", "Approved"), ("completed", "Completed"),
                    ("published", "Published"), ("rejected", "Rejected"),
                    ("pending_delete", "Pending Deletion"),
                ],
                db_index=True, default="draft", max_length=20,
            ),
        ),
    ]
