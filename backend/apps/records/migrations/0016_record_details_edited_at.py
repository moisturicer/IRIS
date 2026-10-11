# IR-273: when a record's details last actually changed. Nullable and not
# backfilled: nothing records when an earlier edit happened, so an edit made
# before this column existed does not count as answering a revision request.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('records', '0015_backfill_record_versions'),
    ]

    operations = [
        migrations.AddField(
            model_name='record',
            name='details_edited_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
