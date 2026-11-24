"""The verifier may read every column its functions read, without re-provisioning (IR-1285)."""

import importlib

import pytest
from django.core.management import CommandError, call_command
from django.db import connection

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

VERIFIER = "iris_authz_verifier"
GRANTS = importlib.import_module("apps.ai.migrations.0052_verifier_reads_added_by").GRANTS


def can_read_added_by() -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT has_column_privilege(%s, 'public.records_record', 'added_by_id', 'SELECT')", [VERIFIER])
        return cursor.fetchone()[0]


@pytest.fixture
def added_by_revoked(grant_db):
    """A database provisioned before ai/0049: the verifier cannot read added_by_id."""
    with connection.cursor() as cursor:
        cursor.execute(f"REVOKE SELECT (added_by_id) ON public.records_record FROM {VERIFIER}")
    try:
        yield
    finally:
        call_command("provision_research_roles")


def test_check_names_a_column_the_verifier_cannot_read(added_by_revoked, capsys):
    with pytest.raises(CommandError):
        call_command("provision_research_roles", "--check")
    assert f"role {VERIFIER} cannot read records_record.added_by_id" in capsys.readouterr().out


def test_the_migration_grants_what_research_record_ids_reads(added_by_revoked):
    assert not can_read_added_by()
    with connection.cursor() as cursor:
        cursor.execute(GRANTS)
    assert can_read_added_by()
    call_command("provision_research_roles", "--check")


def test_the_migration_skips_a_database_without_the_verifier(grant_db):
    with connection.cursor() as cursor:
        cursor.execute(GRANTS.replace(f"'{VERIFIER}'", "'iris_no_such_role'"))
    call_command("provision_research_roles", "--check")
