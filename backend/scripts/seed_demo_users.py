"""
Seed demo accounts for local exploration — one login per IRIS role.

Run with:  python manage.py shell < scripts/seed_demo_users.py
Dev only. Every account uses the same throwaway password.
"""
from django.contrib.auth import get_user_model
from apps.accounts.models import Role

User = get_user_model()
PASSWORD = "IrisDemo123!"

DEMO_USERS = [
    ("student@cit.edu",  "Sam",    "Student",  "Student"),
    ("adviser@cit.edu",  "Ana",    "Adviser",  "Adviser"),
    ("ktto@cit.edu",     "Karl",   "Tan",      "KTTO"),
    ("rdco@cit.edu",     "Rita",   "Cruz",     "RDCO"),
    ("itso@cit.edu",     "Ivan",   "Santos",   "ITSO"),
    ("ierc@cit.edu",     "Elena",  "Reyes",    "IERC"),
]

for email, first, last, role_name in DEMO_USERS:
    role, _ = Role.objects.get_or_create(name=role_name)
    user, created = User.objects.get_or_create(
        email=email,
        defaults={"first_name": first, "last_name": last},
    )
    user.first_name    = first
    user.last_name     = last
    user.role          = role
    user.is_verified   = True   # LoginView rejects unverified accounts
    user.is_active     = True
    user.is_locked     = False
    user.consent_given = True
    user.set_password(PASSWORD)
    user.save()
    print(f"{'created' if created else 'updated'}  {email:22} role={role_name}")

admin, created = User.objects.get_or_create(
    email="admin@cit.edu",
    defaults={"first_name": "Iris", "last_name": "Admin"},
)
admin.is_staff     = True
admin.is_superuser = True
admin.is_verified  = True
admin.is_active    = True
admin.set_password(PASSWORD)
admin.save()
print(f"{'created' if created else 'updated'}  admin@cit.edu          (superuser, /admin)")
print(f"\npassword for every account: {PASSWORD}")
