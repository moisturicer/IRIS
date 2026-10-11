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


#: The last reviews migration before IR-274 retired Intake. 0015 changed only
#: `choices`, so the tables are exactly those `reviews/0014` ran against.
CUTOVER_SCHEMA = ("reviews", "0015_alter_recordassignment_party_and_more")


def at_the_cutover_schema():
    """
    Rewind `reviews` to just before IR-274 (`CUTOVER_SCHEMA`) -- tables
    identical to those IR-260's cutover migration (`reviews/0014`) ran
    against -- for the rest of this test only.

    IR-274's `reviews/0016` forbids an active Intake assignment. A test of
    0014 must build exactly that row -- it is what 0014 retires -- so it
    rewinds 0016, which drops only that constraint. Call it from a `TestCase`:
    PostgreSQL's DDL is transactional, so the test's own rollback restores the
    constraint and the migration record. Pending deferred FK checks would
    block the DDL, so they are run first.
    """
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    if not connection.in_atomic_block:
        raise RuntimeError("at_the_cutover_schema() needs a TestCase's transaction to undo it")
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    MigrationExecutor(connection).migrate([CUTOVER_SCHEMA])
