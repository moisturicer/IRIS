from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        # Rename middle_name → middle_initial (preserves existing data)
        migrations.RenameField(
            model_name="user",
            old_name="middle_name",
            new_name="middle_initial",
        ),
        # Remove username (email is now the login identifier)
        migrations.RemoveField(
            model_name="user",
            name="username",
        ),
        # Remove contact_no (not in the new schema)
        migrations.RemoveField(
            model_name="user",
            name="contact_no",
        ),
    ]
