"""
IR-882, ADR-052 as amended 2026-11-04 (IR-879): every paper is embargoed by default.

A paper is now embargoed or released, and nothing else. `is_embargoed` is added,
true by default, so a new paper is blocked with nothing stamped. The answer stamps
become who set the date and when, because Publish no longer asks a question.

**Renamed in Django only.** `embargo_date_set_at`/`_by` keep their columns,
`embargo_answered_at`/`_by_id`, so `publication/0008`'s SQL functions stay valid
at every step and this needs no dependency on that app. `publication/0009`
rewrites them to read `is_embargoed`.

Existing rows, by what they read as before:

- **None** (answered "no embargo", no date, not released) becomes **Released**,
  released by whoever answered, at that time. It had no date, so no date stamp.
- **Released** stays released.
- **Active** (a date, not released) stays embargoed, its date and who set it kept.
- **Unknown** (never answered) stays embargoed, with nothing else to write.

The old constraints are dropped before the data moves: "a release needs a date"
no longer holds, because a "no embargo" answer becomes a release with no date.
"""

from django.conf import settings
from django.db import migrations, models
from django.db.models import F, Q


def _check_now(schema_editor):
    """Run the deferred foreign-key checks the updates queued.

    Django's foreign keys are checked at commit, and PostgreSQL refuses the
    `ALTER TABLE` steps after the data step while any are pending.
    """
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    schema_editor.execute("SET CONSTRAINTS ALL DEFERRED")


def forwards(apps, schema_editor):
    Record = apps.get_model("records", "Record")
    rows = Record.objects.all()
    # Before anything else moves: a release is what clears the flag.
    rows.filter(embargo_released_at__isnull=False).update(is_embargoed=False)
    # "No embargo" answers become releases, by the person who answered.
    rows.filter(
        embargo_date_set_at__isnull=False, embargoed_until__isnull=True,
        embargo_released_at__isnull=True,
    ).update(
        is_embargoed=False,
        embargo_released_at=F("embargo_date_set_at"),
        embargo_released_by=F("embargo_date_set_by"),
        embargo_date_set_at=None,
        embargo_date_set_by=None,
    )
    _check_now(schema_editor)


def backwards(apps, schema_editor):
    """Undo what forwards did, as far as the old four states can say it.

    A release with no date reads as the "no embargo" answer it came from. A dated
    release stays a release. An embargo with no date had no old form and reads as
    Unknown again, which was already refused.
    """
    Record = apps.get_model("records", "Record")
    Record.objects.filter(is_embargoed=False, embargoed_until__isnull=True).update(
        embargo_date_set_at=F("embargo_released_at"),
        embargo_date_set_by=F("embargo_released_by"),
        embargo_released_at=None,
        embargo_released_by=None,
    )
    _check_now(schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("records", "0031_version_documents"),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="record", name="record_embargo_date_needs_answer"),
        migrations.RemoveConstraint(model_name="record", name="record_embargo_release_needs_date"),
        migrations.AddField(
            model_name="record",
            name="is_embargoed",
            field=models.BooleanField(
                default=True,
                help_text="True until the Adviser or RDCO releases it. Only a released paper reaches the AI or can be published.",
            ),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RenameField(model_name="record", old_name="embargo_answered_at", new_name="embargo_date_set_at"),
                migrations.RenameField(model_name="record", old_name="embargo_answered_by", new_name="embargo_date_set_by"),
                migrations.AlterField(
                    model_name="record",
                    name="embargo_date_set_at",
                    field=models.DateTimeField(
                        blank=True, null=True, db_column="embargo_answered_at",
                        help_text="When the review date was last set. Null when no date was ever set.",
                    ),
                ),
                migrations.AlterField(
                    model_name="record",
                    name="embargo_date_set_by",
                    field=models.ForeignKey(
                        blank=True, null=True, on_delete=models.deletion.SET_NULL,
                        db_column="embargo_answered_by_id",
                        related_name="embargo_dated_records", to=settings.AUTH_USER_MODEL,
                        help_text="Who set the date. SET_NULL so a deleted account cannot erase the timestamp.",
                    ),
                ),
            ],
            # The columns keep their names; the rest is Django's state only.
            database_operations=[],
        ),
        migrations.RunPython(forwards, backwards),
        migrations.AlterField(
            model_name="record",
            name="embargo_released_at",
            field=models.DateTimeField(
                blank=True, null=True,
                help_text="When a person released the embargo. Null while it is embargoed.",
            ),
        ),
        migrations.AddConstraint(
            model_name="record",
            constraint=models.CheckConstraint(
                condition=(
                    Q(is_embargoed=True, embargo_released_at__isnull=True)
                    | Q(is_embargoed=False, embargo_released_at__isnull=False)
                ),
                name="record_embargo_release_matches_state",
            ),
        ),
        migrations.AddConstraint(
            model_name="record",
            constraint=models.CheckConstraint(
                condition=Q(embargoed_until__isnull=True) | Q(embargo_date_set_at__isnull=False),
                name="record_embargo_date_says_when_set",
            ),
        ),
    ]
