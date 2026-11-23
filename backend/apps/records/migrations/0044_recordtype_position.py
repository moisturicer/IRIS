"""
Give record types a fixed order: Proposal, Thesis / Research, Project (IR-1277).

`RecordType` had no ordering, so lists of types came back in storage order,
and saving a type on Setup moved it to the end of Publish's choices.
"""
from django.db import migrations, models

#: The workflow order. Matched by name, since an older database's ids need
#: not follow it (records/0006 removed a "Research Paper" type).
POSITIONS = {"Proposal": 1, "Thesis / Research": 2, "Project": 3}


def set_positions(apps, schema_editor):
    RecordType = apps.get_model("records", "RecordType")
    for name, position in POSITIONS.items():
        RecordType.objects.filter(name=name).update(position=position)


class Migration(migrations.Migration):

    dependencies = [
        ("records", "0043_setup_requirements"),
    ]

    operations = [
        migrations.AddField(
            model_name="recordtype",
            name="position",
            field=models.PositiveSmallIntegerField(default=100),
        ),
        migrations.AlterModelOptions(
            name="recordtype",
            options={"ordering": ["position", "id"]},
        ),
        migrations.RunPython(set_positions, migrations.RunPython.noop),
    ]
