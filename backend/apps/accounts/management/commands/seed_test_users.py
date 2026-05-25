"""
Create or update local test users with @cit.edu emails.

Usage:
    python manage.py seed_test_users
    python manage.py seed_test_users --password mypass
    python manage.py seed_test_users --purge-iris-dev
"""
from django.core.management.base import BaseCommand

from apps.accounts.models import User, Role

# (email, role name)
TEST_USERS = [
    ("iris-student@cit.edu", "Student"),
    ("iris-adviser@cit.edu", "Adviser"),
    ("iris-ktto@cit.edu",    "KTTO"),
    ("iris-rdco@cit.edu",    "RDCO"),
    ("iris-itso@cit.edu",    "ITSO"),
    ("iris-ierc@cit.edu",    "IERC"),
]

EXTRA_ROLES = ["IERC", "System Administrator", "TBI"]

LEGACY_IRIS_DEV_EMAILS = [
    "student@iris.dev",
    "adviser@iris.dev",
    "ktto@iris.dev",
    "rdco@iris.dev",
    "itso@iris.dev",
    "ierc@iris.dev",
]


class Command(BaseCommand):
    help = "Seed verified test users (iris-*@cit.edu) for local development."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="testpass123",
            help="Password for all test accounts (default: testpass123).",
        )
        parser.add_argument(
            "--purge-iris-dev",
            action="store_true",
            help="Delete legacy @iris.dev test accounts after seeding.",
        )

    def handle(self, *args, **options):
        password = options["password"]

        for name in EXTRA_ROLES:
            Role.objects.get_or_create(name=name)

        for email, role_name in TEST_USERS:
            role = Role.objects.get(name=role_name)
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": "Test",
                    "last_name":  role_name,
                },
            )
            user.set_password(password)
            user.role = role
            user.is_verified = True
            user.is_active = True
            user.save()
            verb = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{verb}: {email} -> {role_name}"))

        if options["purge_iris_dev"]:
            deleted, _ = User.objects.filter(email__in=LEGACY_IRIS_DEV_EMAILS).delete()
            if deleted:
                self.stdout.write(self.style.WARNING(f"Removed {deleted} legacy @iris.dev user(s)."))

        self.stdout.write("")
        self.stdout.write("Sign in at /login with any account above and password:")
        self.stdout.write(f"  {password}")
