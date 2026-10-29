"""
Audit rows are insert-only, enforced by PostgreSQL (IR-166, NFR-S5).

Until now immutability rested on the absence of an endpoint, so a shell, a
careless migration or a future view could rewrite history. A trigger is the
control an application check cannot be: it binds every client of the table.

Every DELETE and every UPDATE that changes anything is refused. An UPDATE that
rewrites a row with its own values (an unchanged ``save()``) is let through,
since it alters nothing. The comparison is the whole row, so a column added
later is protected without editing this trigger.

That leaves no room for ``on_delete=SET_NULL``, which updates audit rows when
their User or Record is deleted. So the two foreign keys become
``DO_NOTHING`` with no database constraint, first, in this same migration:
deleting a subject leaves its audit rows untouched, still carrying its id.

TRUNCATE is not row-level and is not caught. Django's test teardown uses it,
and nothing in the application issues it.

The trigger does not stop the table's owner from dropping it. A deliberate
change to history therefore has to be a reviewed migration that says so, which
is the point: it can no longer happen by accident.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

FORWARD = """
CREATE FUNCTION audit_auditevent_insert_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND to_jsonb(NEW) = to_jsonb(OLD) THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'audit_auditevent is insert-only: % refused (IR-166)', TG_OP;
END;
$$;

CREATE TRIGGER audit_auditevent_insert_only
BEFORE UPDATE OR DELETE ON audit_auditevent
FOR EACH ROW EXECUTE FUNCTION audit_auditevent_insert_only();
"""

REVERSE = """
DROP TRIGGER IF EXISTS audit_auditevent_insert_only ON audit_auditevent;
DROP FUNCTION IF EXISTS audit_auditevent_insert_only();
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0004_workflow_event_types")]

    operations = [
        migrations.AlterField(
            model_name="auditevent",
            name="user",
            field=models.ForeignKey(
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="audit_events",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="auditevent",
            name="record",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="audit_events",
                to="records.record",
            ),
        ),
        migrations.RunSQL(FORWARD, REVERSE),
    ]
