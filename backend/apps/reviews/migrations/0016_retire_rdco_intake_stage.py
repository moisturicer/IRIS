"""IR-274: one spelling for the retired Intake, and no active Intake ever again.

`rdco_intake` and `intake` were two stored spellings of one party: the fixed
pipeline recorded RDCO's intake decisions as `rdco_intake`, ADR-021 named the
party `intake`, and both were labelled "Intake (retired)" by IR-260. This
rewrites the old spelling to `intake`, so historical Reviews stay readable
under the one remaining value, then removes `rdco_intake` from the choices.

It then adds a database constraint that refuses an *active* assignment to a
retired party (ADR-032 §13). `reviews.0014` withdrew every active intake
assignment; if one is found anyway, this refuses with its ID rather than letting
the constraint fail with a bare integrity error.

**The reverse is lossy, on purpose and harmlessly.** It drops the constraint and
restores the choice, but cannot tell which `intake` Reviews were once spelled
`rdco_intake`, so it leaves them as `intake`. Both spellings carried the same
label and meant the same party.
"""

from django.db import migrations, models


def unify_intake_spelling(apps, schema_editor):
    Review = apps.get_model("reviews", "Review")
    Review.objects.filter(stage="rdco_intake").update(stage="intake")


def refuse_active_intake(apps, schema_editor):
    RecordAssignment = apps.get_model("reviews", "RecordAssignment")
    active = list(
        RecordAssignment.objects.filter(party="intake", state="active")
        .order_by("pk").values_list("pk", "record_id")
    )
    if active:
        raise RuntimeError(
            "IR-274 cannot retire Intake while assignments to it are active "
            f"(assignment, record): {active}. Apply reviews.0014's cutover "
            "(IR-260) or withdraw them by hand first."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("reviews", "0015_alter_recordassignment_party_and_more"),
    ]

    operations = [
        migrations.RunPython(unify_intake_spelling, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="review",
            name="stage",
            field=models.CharField(
                choices=[
                    ("adviser", "Adviser"), ("intake", "Intake (retired)"),
                    ("itso", "ITSO"), ("ierc", "IERC"), ("ktto", "KTTO"),
                    ("rdco", "RDCO Final"),
                ],
                db_index=True, max_length=20,
            ),
        ),
        migrations.RunPython(refuse_active_intake, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="recordassignment",
            constraint=models.CheckConstraint(
                condition=~models.Q(state="active", party__in=["intake"]),
                name="no_active_assignment_for_a_retired_party",
            ),
        ),
    ]
