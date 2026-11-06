from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("records", "0026_record_manuscript_filename_and_more")]

    operations = [
        migrations.AddField(
            model_name="record", name="duplicate_acknowledgement",
            field=models.CharField(blank=True, editable=False, max_length=64),
        ),
    ]
