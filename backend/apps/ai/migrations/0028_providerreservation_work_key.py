from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ai", "0027_turn_comparison")]
    operations = [migrations.AddField(
        model_name="providerreservation", name="work_key",
        field=models.CharField(blank=True, db_index=True, max_length=64),
    )]
