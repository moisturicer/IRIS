"""`User.tours_off` (IR-1349): "Don't show tours again".

Every account starts with it unset. Accounts that existed before IR-1342 have
already seen every tour (`0025_tours_seen`), so leaving it unset changes
nothing for them.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0025_tours_seen"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="tours_off",
            field=models.BooleanField(default=False),
        ),
    ]
