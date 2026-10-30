"""Why a sign-in ended (IR-645).

Nullable and not backfilled: whether a session ended before this idled out or
logged out cannot be known, so it keeps a null reason and reads as inactivity,
the message it had before.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0012_reset_seeded_reference_sequences")]

    operations = [
        migrations.AddField(
            model_name="usersession",
            name="ended_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("logout", "Signed out"),
                    ("idle", "Inactive too long"),
                    ("locked", "Account locked"),
                    ("password_changed", "Password changed"),
                ],
                max_length=32,
                null=True,
            ),
        ),
    ]
