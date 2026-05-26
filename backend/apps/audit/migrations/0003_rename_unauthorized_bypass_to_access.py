"""
Renames the audit event type value from 'UNAUTHORIZED_BYPASS' to
'UNAUTHORIZED_ACCESS' to align with the SDD §6.3 sequence diagram which
specifies:  log_event(user_id, 'UNAUTHORIZED_ACCESS', view_name)

Also updates any existing rows in the DB that used the old value.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0002_alter_auditevent_event_type'),
    ]

    operations = [
        # 1. Rename existing stored values in the database rows
        migrations.RunSQL(
            sql="""
                UPDATE audit_auditevent
                SET event_type = 'UNAUTHORIZED_ACCESS'
                WHERE event_type = 'UNAUTHORIZED_BYPASS';
            """,
            reverse_sql="""
                UPDATE audit_auditevent
                SET event_type = 'UNAUTHORIZED_BYPASS'
                WHERE event_type = 'UNAUTHORIZED_ACCESS';
            """,
        ),

        # 2. Update the field's choices list to match the new constant
        migrations.AlterField(
            model_name='auditevent',
            name='event_type',
            field=models.CharField(
                choices=[
                    ('LOGIN',               'Login'),
                    ('LOGOUT',              'Logout'),
                    ('ACCESS',              'Record Access'),
                    ('UPLOAD',              'File Upload'),
                    ('DOWNLOAD',            'File Download'),
                    ('DELETE',              'File Delete'),
                    ('RENAME',              'File Rename'),
                    ('UNAUTHORIZED_ACCESS', 'Unauthorized Access Attempt'),
                ],
                db_index=True,
                max_length=30,
            ),
        ),
    ]
