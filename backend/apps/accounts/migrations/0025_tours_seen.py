"""`User.tours_seen` (IR-1342), and every account that exists now counts as toured.

The student tours are for students who register after this ships. Accounts
already here, seed_demo's included, are marked as having seen every tour, so
none of them is walked through a page it already knows.

The keys are written out below rather than imported from `apps.accounts.tours`:
this migration means "the tours that existed when it ran", and that must not
change when a tour is added later (see that module's docstring).

Reversing it drops the field. Running it forward again marks whoever exists
then, so the cutoff is decided once, when it is applied.
"""
from django.db import migrations, models

KEYS_AT_THIS_MIGRATION = [
    "discover",
    "library",
    "ask",
    "calls",
    "guidelines",
    "notifications",
    "publish",
]


def mark_existing_accounts(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.update(tours_seen=KEYS_AT_THIS_MIGRATION)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0024_session_remembered"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="tours_seen",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(mark_existing_accounts, migrations.RunPython.noop),
    ]
