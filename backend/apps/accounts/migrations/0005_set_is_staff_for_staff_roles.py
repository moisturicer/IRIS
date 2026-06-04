"""
Set is_staff=True on any User whose role is one of the IRIS staff roles
(RDCO, KTTO, ITSO, IERC).  These users need Django's is_staff flag so that:

  - The DRF IsStaff permission check works via both the role name AND the
    Django flag (consistent with irisadmin which was already is_staff=True).
  - The Django admin site is accessible to staff users if ever needed.

Safe to re-run: uses update() which is idempotent.
"""
from django.db import migrations

STAFF_ROLE_NAMES = {"RDCO", "KTTO", "ITSO", "IERC"}


def set_is_staff(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(role__name__in=STAFF_ROLE_NAMES).update(is_staff=True)


def unset_is_staff(apps, schema_editor):
    # Only unset for users that ONLY qualify via role (not originally superusers).
    User = apps.get_model("accounts", "User")
    User.objects.filter(
        role__name__in=STAFF_ROLE_NAMES,
        is_superuser=False,
    ).update(is_staff=False)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_alter_user_middle_initial"),
    ]

    operations = [
        migrations.RunPython(set_is_staff, reverse_code=unset_is_staff),
    ]
