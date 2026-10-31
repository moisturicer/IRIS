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


def model_at_current_state(app_label, model_name):
    """A fixture model matching the migrations actually applied to its table."""
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    loader = MigrationExecutor(connection).loader
    return loader.project_state(list(loader.applied_migrations)).apps.get_model(app_label, model_name)


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
    model_at_current_state("records", "Record").objects.all().delete()


def at_the_cutover_schema():
    """
    Permit active Intake fixtures for the rest of this test only.

    IR-274's `reviews/0016` forbids an active Intake assignment. A test of
    0014 must build exactly that row -- it is what 0014 retires -- so it
    removes only that constraint. Rewinding to 0015 would also remove later
    columns (IR-619) that these tests' live model fixtures need. These tests
    drive the cutover functions directly; migration executor tests separately
    exercise historical schemas. Call from a `TestCase`: PostgreSQL's DDL is
    transactional, so its rollback restores the constraint. No migration
    records or expected outcomes change.
    """
    from django.db import connection
    from .models import RecordAssignment

    if not connection.in_atomic_block:
        raise RuntimeError("at_the_cutover_schema() needs a TestCase's transaction to undo it")
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    constraint = next(c for c in RecordAssignment._meta.constraints
                      if c.name == "no_active_assignment_for_a_retired_party")
    with connection.schema_editor() as editor:
        editor.remove_constraint(RecordAssignment, constraint)
