"""IR-473: drop the document-access PIN table.

Verifying a PIN unlocked nothing: no permission, download or view read it.
The audit event types `PIN_GENERATED` and `PIN_VERIFIED` stay as choices on
`AuditEvent`, so history written before this migration still renders.
"""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("reviews", "0019_merge_deadline_moment_and_seat_reassignment"),
    ]

    operations = [
        migrations.DeleteModel(name="RecordAuthPin"),
    ]
