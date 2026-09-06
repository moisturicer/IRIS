"""
Reverse 0005's is_staff seeding on the four office roles (IR-165).

0005 set `is_staff = True` for RDCO, KTTO, ITSO and IERC so those accounts could
open the Django admin site. The side effect was the authorization defect this
migration's companion code change closes: every permission class in
`core/permissions.py` began `is_django_staff(user) or <role check>`, and
`is_django_staff` reads `is_staff` -- so the left operand was always True for
those four roles and the role check never ran. `ADMIN_ROLES` constrained nobody,
and the audit log, intended for RDCO alone, admitted all four offices.

With authorization now decided by application role, the flag no longer has to
carry that weight, so it is removed from role-holders. Two accounts are
deliberately left alone:

  * `is_superuser` accounts -- the real administrators. Django requires
    `is_staff` to open /admin at all, so clearing it would lock them out of the
    admin site, which is the opposite of what IR-165 asks for ("reserve
    is_superuser for Django admin only" -- reserve, not revoke).
  * Anyone whose `is_staff` was set by hand rather than by role is
    indistinguishable from 0005's work at this point; the filter below matches
    0005's exactly, so this reverses that migration and nothing else.

Reversible: the backwards operation restores 0005's behaviour precisely.
"""
from django.db import migrations

# The same four names 0005 filtered on.
STAFF_ROLE_NAMES = ["RDCO", "KTTO", "ITSO", "IERC"]


def unset_is_staff(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(
        role__name__in=STAFF_ROLE_NAMES,
        is_superuser=False,
    ).update(is_staff=False)


def set_is_staff(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(role__name__in=STAFF_ROLE_NAMES).update(is_staff=True)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_drop_storage_tables"),
    ]

    operations = [
        migrations.RunPython(unset_is_staff, reverse_code=set_is_staff),
    ]
