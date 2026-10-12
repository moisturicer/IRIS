from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ai", "0021_record_overview_generation_state")]
    operations = [
        migrations.AddField(model_name="turn", name="research", field=models.JSONField(blank=True, default=dict)),
    ]
