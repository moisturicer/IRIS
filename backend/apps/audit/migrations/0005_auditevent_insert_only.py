"""
Audit rows are insert-only, enforced by PostgreSQL (IR-166, NFR-S5).

Until now immutability rested on the absence of an endpoint, so a shell, a
careless migration or a future view could rewrite history. A trigger is the
control an application check cannot be: it binds every client of the table.

DELETE is always refused. UPDATE is refused with one exception, which is
Django's own ``on_delete=SET_NULL``: deleting a User or a Record sets
``user_id``/``record_id`` to NULL on the rows that name it. That UPDATE is
allowed only when it clears one or both of those pointers and changes nothing
else, so the row -- type, time, metadata -- survives its subject.

TRUNCATE is not row-level and is not caught. Django's test teardown uses it,
and nothing in the application issues it.

The trigger does not stop the table's owner from dropping it. A deliberate
change to history therefore has to be a reviewed migration that says so, which
is the point: it can no longer happen by accident.
"""

from django.db import migrations

FORWARD = """
CREATE FUNCTION audit_auditevent_insert_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'audit_auditevent is insert-only: DELETE refused (IR-166)';
    END IF;

    -- UPDATE: only on_delete=SET_NULL detaching the row from its subject.
    IF NEW.id = OLD.id
       AND NEW.event_type = OLD.event_type
       AND NEW.metadata = OLD.metadata
       AND NEW.created_at = OLD.created_at
       AND (NEW.user_id IS NOT DISTINCT FROM OLD.user_id OR NEW.user_id IS NULL)
       AND (NEW.record_id IS NOT DISTINCT FROM OLD.record_id OR NEW.record_id IS NULL)
    THEN
        RETURN NEW;
    END IF;

    RAISE EXCEPTION 'audit_auditevent is insert-only: UPDATE refused (IR-166)';
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

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
