"""IR-873 (ADR-058 §3 as amended 2026-11-08): a review text names the reader
it was made for, so a comparison can ask for one file read by one reader and
find it again. Texts already read are given the reader that read them; a text
not read yet keeps a blank, and is whichever reader reads it."""
from django.db import migrations, models


def name_the_reader(apps, schema_editor):
    ReviewText = apps.get_model("records", "ReviewText")
    ReviewText.objects.exclude(reader="").update(requested_reader=models.F("reader"))


class Migration(migrations.Migration):

    dependencies = [
        ("records", "0036_record_ai_consent"),
    ]

    operations = [
        migrations.AddField(
            model_name="reviewtext",
            name="requested_reader",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.RunPython(name_the_reader, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="reviewtext",
            constraint=models.UniqueConstraint(
                condition=models.Q(("requested_reader", ""), _negated=True),
                fields=("record", "source_file", "manuscript_sha256", "requested_reader"),
                name="review_text_one_reading_per_reader",
            ),
        ),
    ]
