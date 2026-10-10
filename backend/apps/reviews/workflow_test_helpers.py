"""Shared account factory for adviser-first API tests."""

from apps.accounts.models import Role, User


def make_user(email, role_name):
    # Role rows are seeded by migrations; reuse them rather than colliding with
    # their explicit primary keys.
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", first_name="Test",
        last_name="User", role=role, is_verified=True,
    )
