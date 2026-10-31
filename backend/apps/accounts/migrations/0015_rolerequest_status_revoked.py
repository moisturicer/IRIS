from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0014_usersession_revoked_reason")]

    operations = [
        migrations.AlterField(
            model_name="rolerequest", name="status",
            field=models.CharField(
                choices=[("pending", "Pending"), ("approved", "Approved"),
                         ("declined", "Declined"), ("revoked", "Revoked")],
                default="pending", max_length=10,
            ),
        ),
    ]
