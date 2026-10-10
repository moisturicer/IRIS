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


def purge_records_at_current_state():
    """
    Delete every Record, through the models as of the migrations applied now.

    A migration test rewinds an app, builds old-model rows to assert a
    backfill, then migrates forward to restore the schema. Its rows are
    deliberately partial, so IR-260's cutover (`reviews/0014`) would rightly
    refuse them on the way forward. They are the test's own fixtures and
    nothing reads them afterwards, so the test deletes them first, through
    the historical models, since the live ones may name columns the rewound
    tables lack.
    """
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    loader = MigrationExecutor(connection).loader
    state = loader.project_state(list(loader.applied_migrations))
    state.apps.get_model("records", "Record").objects.all().delete()
