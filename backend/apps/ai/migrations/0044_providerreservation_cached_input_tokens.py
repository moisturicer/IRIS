from django.db import migrations, models


class Migration(migrations.Migration):
    """Record prompt-cache hits per attempt (IR-953). Additive and nullable."""

    dependencies = [("ai", "0043_reader_status_deleted_account")]

    operations = [
        migrations.AddField(
            model_name="providerreservation",
            name="cached_input_tokens",
            field=models.BigIntegerField(blank=True, null=True),
        ),
    ]
