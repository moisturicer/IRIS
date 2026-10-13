"""Name the audit event for a flagged reader question (IR-514)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("audit", "0002_alter_auditevent_event_type")]

    operations = [
        migrations.AlterField(
            model_name="auditevent",
            name="event_type",
            field=models.CharField(
                max_length=20,
                db_index=True,
                choices=[
                    ("LOGIN", "Login"),
                    ("LOGOUT", "Logout"),
                    ("FAILED_LOGIN", "Failed Login"),
                    ("ACCESS", "Record Access"),
                    ("UPLOAD", "File Upload"),
                    ("DOWNLOAD", "File Download"),
                    ("DELETE", "File Delete"),
                    ("RENAME", "File Rename"),
                    ("PIN_GENERATED", "PIN Generated"),
                    ("PIN_VERIFIED", "PIN Verified"),
                    ("ROLE_CHANGE", "Role Change"),
                    ("ACCOUNT_LOCKED", "Account Locked"),
                    ("ACCOUNT_UNLOCKED", "Account Unlocked"),
                    ("SESSION_REVOKE", "Session Revoked"),
                    ("QUESTION_INJECTION", "Reader Question Injection Flagged"),
                ],
            ),
        ),
    ]
