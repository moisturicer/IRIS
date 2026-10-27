from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ai", "0026_paper_brief")]
    operations = [migrations.AddField(
        model_name="turn", name="comparison", field=models.JSONField(blank=True, default=dict),
    )]
