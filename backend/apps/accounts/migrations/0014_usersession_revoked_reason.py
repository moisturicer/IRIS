"""An administrator's revocation is a reason a sign-in ended (IR-657). Choices only."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0013_usersession_ended_reason")]

    operations = [
        migrations.AlterField(
            model_name="usersession",
            name="ended_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("logout", "Signed out"),
                    ("idle", "Inactive too long"),
                    ("locked", "Account locked"),
                    ("password_changed", "Password changed"),
                    ("revoked", "Revoked by an administrator"),
                ],
                max_length=32,
                null=True,
            ),
        ),
    ]
