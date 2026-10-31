from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [("records", "0020_record_derived_from")]

    operations = [
        migrations.AddField(
            model_name="record", name="origin",
            field=models.CharField(
                max_length=24, default="unknown",
                choices=[("unknown", "Unknown"), ("institutional", "Institutional"),
                         ("imported_reference", "Imported reference"), ("synthetic", "Synthetic")],
            ),
        ),
        migrations.AddField(
            model_name="record", name="publication_year",
            field=models.PositiveIntegerField(null=True, blank=True, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(9999)]),
        ),
    ]
