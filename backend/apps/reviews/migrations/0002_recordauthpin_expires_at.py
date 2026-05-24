from django.db import migrations, models


class Migration(migrations.Migration):
    """Add expires_at to RecordAuthPin so PINs can be invalidated after 24 hours."""

    dependencies = [
        ("reviews", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="recordauthpin",
            name="expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
