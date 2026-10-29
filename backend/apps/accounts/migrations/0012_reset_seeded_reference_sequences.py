"""
Move the id sequences past 0003's seed rows (IR-126).

0003 seeds Colleges, Departments and Courses with literal ids so the reference
data has stable keys. On Postgres an insert with an explicit id does not
advance the table's id sequence, so the sequences were left at 1 and the first
ordinary create() on any of the three tables asked for id 1 and failed with a
duplicate primary key.

0003 is applied and is not edited here; this sets each sequence to the table's
current maximum id instead. That is also correct on a database where rows were
added by hand since, or seeded by an earlier revision of 0003: setval takes
whatever the maximum is now.

Roles are not touched: 0003 and 0006 create them by name, without an id, so
their sequence was never behind.

On a backend with no sequences to reset, sequence_reset_sql returns nothing and
this does nothing. Reversing it is a no-op: putting a sequence back behind its
rows would only restore the defect.
"""
from django.core.management.color import no_style
from django.db import migrations

SEEDED_WITH_EXPLICIT_IDS = ["College", "Department", "Course"]


def reset_sequences(apps, schema_editor):
    models = [apps.get_model("accounts", name) for name in SEEDED_WITH_EXPLICIT_IDS]
    connection = schema_editor.connection
    for sql in connection.ops.sequence_reset_sql(no_style(), models):
        schema_editor.execute(sql)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_usersession"),
    ]

    operations = [
        migrations.RunPython(reset_sequences, migrations.RunPython.noop),
    ]
