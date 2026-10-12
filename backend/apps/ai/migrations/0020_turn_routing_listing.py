from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ai", "0019_research_run_audit")]
    operations = [
        migrations.AddField(model_name="turn", name="routing", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="turn", name="listing", field=models.JSONField(blank=True, default=dict)),
    ]
