"""The research-grant verifier inside PostgreSQL, under a real restricted role (IR-717)."""

import pytest

from apps.ai.grants import issue
from .corpus import make_user
from .grant_support import owned_run, probe_login

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]


def begin(conn, grant, purpose):
    with conn.cursor() as cursor:
        cursor.execute("SELECT iris_authz.begin_research(%s, %s)", [grant, purpose])
        return cursor.fetchone()[0]


def reader(conn):
    with conn.cursor() as cursor:
        cursor.execute("SELECT iris_authz.current_reader()")
        return cursor.fetchone()[0]


def rejected(conn, grant, purpose):
    import psycopg2

    try:
        begin(conn, grant, purpose)
    except psycopg2.errors.InsufficientPrivilege:
        conn.rollback()
        return True
    conn.rollback()
    return False


def test_a_django_issued_reader_grant_establishes_the_reader(grant_db):
    user = make_user("grant-reader@cit.edu")
    run = owned_run(user)
    grant = issue.reader_grant(user, run).token
    with probe_login() as conn:
        claims = begin(conn, grant, "reader_run")
        assert claims["sub"] == user.pk
        assert reader(conn) == user.pk


def resign(token, secret=b"a" * 32, kid="k1", **changes):
    """The same claims with `changes`, signed with `secret` as `kid`."""
    import base64
    import json

    from apps.ai.grants import tokens

    body = token.split(".")[2]
    claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    claims.update(kid=kid, **changes)
    return tokens.sign(claims, kid, secret)


def test_forged_and_mismatched_grants_are_rejected(grant_db):
    import time

    user = make_user("grant-attack@cit.edu")
    other = make_user("grant-other@cit.edu")
    run = owned_run(user)
    foreign = owned_run(other)
    grant = issue.reader_grant(user, run).token
    head, kid, body, sig = grant.split(".")
    now = int(time.time())
    attacks = {
        "tampered body": f"{head}.{kid}.{body[:-2]}AA.{sig}",
        "forged signature": resign(grant, secret=b"z" * 32),
        "unknown key": resign(grant, kid="k9"),
        "wrong audience": resign(grant, aud="someone-else"),
        "wrong deployment": resign(grant, dep="production"),
        "expired": resign(grant, iat=now - 400, exp=now - 100),
        "too long": resign(grant, exp=now + 3600),
        "foreign run": resign(grant, run=str(foreign.pk), cnv=foreign.conversation_id),
        "other reader": resign(grant, sub=other.pk),
        "wrong scope": resign(grant, rec=999999),
        "garbage": "irg1.k1.not-json.x",
    }
    with probe_login() as conn:
        for name, token in attacks.items():
            assert rejected(conn, token, "reader_run"), name
        assert not rejected(conn, grant, "reader_run")


def test_revocation_and_run_end_are_read_live(grant_db):
    from apps.ai.models import AskRun

    user = make_user("grant-revoke@cit.edu")
    run = owned_run(user)
    grant = issue.reader_grant(user, run).token
    with probe_login() as conn:
        assert not rejected(conn, grant, "reader_run")
        user.credential_version += 1
        user.save(update_fields=["credential_version"])
        assert rejected(conn, grant, "reader_run")

        fresh = issue.reader_grant(user, run).token
        assert not rejected(conn, fresh, "reader_run")
        AskRun.objects.filter(pk=run.pk).update(state="cancelled")
        assert rejected(conn, fresh, "reader_run")

        second = owned_run(user)
        last = issue.reader_grant(user, second).token
        type(user).objects.filter(pk=user.pk).update(is_active=False)
        assert rejected(conn, last, "reader_run")


def test_grants_cannot_be_replayed_across_purposes(grant_db, space):
    from apps.ai.models import IngestionJob
    from apps.records.models import Record

    user = make_user("grant-purpose@cit.edu")
    run_grant = issue.reader_grant(user, owned_run(user)).token
    read_grant = issue.record_read_grant(user).token
    record = Record.objects.create(title="Purpose paper", abstract="a")
    job = IngestionJob.objects.create(record=record, extraction_hash="e" * 64, strategy_id="s",
                                      space=space, idempotency_key="k" * 64)
    job_grant = issue.ingestion_grant(job).token
    with probe_login() as conn:
        # A reader with no Conversation or AskRun still reads as itself.
        assert not rejected(conn, read_grant, "record_read")
        assert not rejected(conn, run_grant, "reader_run")
        assert not rejected(conn, job_grant, "ingestion")
        for token, wrong in ((read_grant, "reader_run"), (read_grant, "ingestion"),
                             (run_grant, "record_read"), (run_grant, "ingestion"),
                             (job_grant, "reader_run"), (job_grant, "record_read")):
            assert rejected(conn, token, wrong), (wrong, token[:20])
        IngestionJob.objects.filter(pk=job.pk).update(extraction_hash="f" * 64)
        assert rejected(conn, job_grant, "ingestion")


def test_a_raw_session_setting_establishes_no_principal(grant_db):
    user = make_user("grant-raw@cit.edu")
    grant = issue.reader_grant(user, owned_run(user)).token
    with probe_login() as conn, conn.cursor() as cursor:
        cursor.execute("SET iris.research_grant = %s", [grant])
        cursor.execute("SET iris.research_purpose = 'reader_run'")
        cursor.execute("SET iris.research_bind = 'deadbeef'")
        cursor.execute("SET iris.reader_id = %s", [str(user.pk)])
        assert reader(conn) is None
        conn.rollback()
        # A valid binding from one transaction is dead in the next, even
        # when copied into a session-level setting.
        claims = begin(conn, grant, "reader_run")
        assert claims["sub"] == user.pk
        cursor.execute("SELECT current_setting('iris.research_bind')")
        tag = cursor.fetchone()[0]
        conn.commit()
        cursor.execute("SET iris.research_grant = %s", [grant])
        cursor.execute("SET iris.research_purpose = 'reader_run'")
        cursor.execute("SET iris.research_bind = %s", [tag])
        assert reader(conn) is None
        conn.rollback()


def test_one_pooled_connection_never_carries_a_reader_forward(grant_db):
    import psycopg2

    alice = make_user("grant-alice@cit.edu")
    bob = make_user("grant-bob@cit.edu")
    alice_grant = issue.reader_grant(alice, owned_run(alice)).token
    bob_grant = issue.reader_grant(bob, owned_run(bob)).token
    with probe_login() as conn:
        begin(conn, alice_grant, "reader_run")
        assert reader(conn) == alice.pk
        conn.commit()
        assert reader(conn) is None
        conn.rollback()

        begin(conn, bob_grant, "reader_run")
        assert reader(conn) == bob.pk
        # No switching identity inside a transaction.
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            begin(conn, alice_grant, "reader_run")
        conn.rollback()
        assert reader(conn) is None
        conn.rollback()

        # A savepoint rolled back takes its identity with it.
        with conn.cursor() as cursor:
            cursor.execute("SAVEPOINT s")
        begin(conn, alice_grant, "reader_run")
        with conn.cursor() as cursor:
            cursor.execute("ROLLBACK TO SAVEPOINT s")
        assert reader(conn) is None
        conn.rollback()

        # A failed transaction, then a retry as the other reader.
        assert rejected(conn, alice_grant + "x", "reader_run")
        begin(conn, bob_grant, "reader_run")
        assert reader(conn) == bob.pk
        conn.commit()

        # Autocommit: the identity lives for one statement only.
        conn.autocommit = True
        begin(conn, alice_grant, "reader_run")
        assert reader(conn) is None


def denied(conn, sql, params=()):
    import psycopg2

    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
    except psycopg2.errors.InsufficientPrivilege:
        conn.rollback()
        return True
    conn.rollback()
    return False


@pytest.mark.parametrize("group", ["iris_ai_runtime", "iris_django_runtime"])
def test_runtime_roles_cannot_mint_read_keys_or_escalate(grant_db, group):
    from django.core.management import call_command
    from django.db import connection

    with probe_login(group) as conn:
        assert denied(conn, "SELECT secret FROM iris_authz.grant_key")
        assert denied(conn, "SELECT iris_authz.binding_tag('irg1.k1.x.y', 'reader_run')")
        assert denied(conn, "SELECT iris_authz.hmac_sha256('k'::bytea, 'm'::bytea)")
        assert denied(conn, "INSERT INTO iris_authz.grant_key VALUES ('kx', %s, 'a', 'd', NULL)",
                      [b"x" * 32])
        assert denied(conn, "CREATE FUNCTION iris_authz.evil() RETURNS int LANGUAGE sql AS 'SELECT 1'")
        assert denied(conn, "SELECT password FROM accounts_user")
        assert denied(conn, "SET ROLE iris_authz_verifier")
        assert denied(conn, "ALTER TABLE accounts_user DISABLE ROW LEVEL SECURITY")
    if group == "iris_ai_runtime":
        with probe_login(group) as conn:
            assert denied(conn, "SELECT iris_authz.verify_research_grant('x', 'reader_run')")

    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT rolsuper OR rolbypassrls OR rolcreaterole OR rolcanlogin
                 FROM pg_roles WHERE rolname = %s""", [group])
        assert cursor.fetchone()[0] is False
        cursor.execute(
            """SELECT count(*) FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner
                WHERE r.rolname = %s""", [group])
        assert cursor.fetchone()[0] == 0
        cursor.execute(
            """SELECT p.proname, r.rolname, p.proconfig FROM pg_proc p
                 JOIN pg_namespace n ON n.oid = p.pronamespace JOIN pg_roles r ON r.oid = p.proowner
                WHERE n.nspname = 'iris_authz' AND p.prosecdef""")
        definers = cursor.fetchall()
    assert {name for name, _, _ in definers} >= {"begin_research", "verify_research_grant",
                                                 "current_reader", "current_research_claims"}
    for name, owner, config_ in definers:
        assert owner == "iris_authz_verifier", name
        assert "search_path=pg_catalog, pg_temp" in config_, name
    call_command("provision_research_roles", "--check")


def test_key_rotation_overlaps_for_one_grant_lifetime_only(grant_db):
    from django.core.management import call_command
    from django.db import connection

    from .grant_support import KEY_A, KEY_B, enable_grants

    user = make_user("grant-rotate@cit.edu")
    run = owned_run(user)
    old = issue.reader_grant(user, run).token
    enable_grants(grant_db, keys=f"k2:{KEY_B},k1:{KEY_A}", active="k2", ttl=300)
    call_command("install_research_grant_keys")
    new = issue.reader_grant(user, run).token
    assert new.split(".")[1] == "k2"
    with connection.cursor() as cursor:
        cursor.execute("SELECT retire_at - now() FROM iris_authz.grant_key WHERE kid = 'k1'")
        assert cursor.fetchone()[0].total_seconds() <= 300
    # Re-installing never pushes the retirement later.
    call_command("install_research_grant_keys")
    with probe_login() as conn:
        assert not rejected(conn, old, "reader_run")
        assert not rejected(conn, new, "reader_run")
        with connection.cursor() as cursor:
            cursor.execute("UPDATE iris_authz.grant_key SET retire_at = now() - interval '1 second' "
                           "WHERE kid = 'k1'")
        assert rejected(conn, old, "reader_run")
        call_command("install_research_grant_keys")
        assert rejected(conn, old, "reader_run")
        enable_grants(grant_db, keys=f"k2:{KEY_B}", active="k2")
        call_command("install_research_grant_keys")
        assert not rejected(conn, new, "reader_run")
    with connection.cursor() as cursor:
        cursor.execute("SELECT array_agg(kid) FROM iris_authz.grant_key")
        assert cursor.fetchone()[0] == ["k2"]


@pytest.fixture
def maintenance_login(grant_db):
    """A CREATEROLE, non-superuser login owning what provisioning touches."""
    import secrets
    import uuid

    from django.db import connection

    from apps.ai.management.commands.provision_research_roles import (
        HELPER_FUNCTIONS, RUNTIME_ROLES, VERIFIER, VERIFIER_COLUMNS,
    )
    from apps.ai.grants.policy import PROTECTED_TABLES

    name = f"iris_maint_{uuid.uuid4().hex[:10]}"
    password = secrets.token_urlsafe(16)
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE ROLE "{name}" LOGIN CREATEROLE PASSWORD %s', [password])
        # What PostgreSQL 16 gives the creator of a role: ADMIN, no SET.
        for role in (VERIFIER, *RUNTIME_ROLES):
            cursor.execute(f'GRANT {role} TO "{name}" WITH ADMIN TRUE, INHERIT FALSE, SET FALSE')
        cursor.execute(f'ALTER SCHEMA iris_authz OWNER TO "{name}"')
        cursor.execute(f'ALTER TABLE iris_authz.grant_key OWNER TO "{name}"')
        for fn in HELPER_FUNCTIONS:
            cursor.execute(f'ALTER FUNCTION iris_authz.{fn} OWNER TO "{name}"')
        for table in {*VERIFIER_COLUMNS, *PROTECTED_TABLES}:
            cursor.execute(f'ALTER TABLE public.{table} OWNER TO "{name}"')
    try:
        yield name, password
    finally:
        connection.close()
        with connection.cursor() as cursor:
            cursor.execute(f'REASSIGN OWNED BY "{name}" TO CURRENT_USER')
            cursor.execute(f'DROP OWNED BY "{name}"')
            cursor.execute(f'DROP ROLE "{name}"')


def test_provisioning_leaves_the_maintenance_login_outside_the_verifier(maintenance_login):
    import psycopg2
    from django.core.management import call_command
    from django.db import connection

    from .grant_support import connected_as

    name, password = maintenance_login
    with connected_as(name, password):
        call_command("provision_research_roles")

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_has_role(%s, 'iris_authz_verifier', 'SET'), "
                       "pg_has_role(%s, 'iris_authz_verifier', 'USAGE')", [name, name])
        assert cursor.fetchone() == (False, False)
    params = connection.settings_dict
    conn = psycopg2.connect(host=params["HOST"] or "localhost", port=params["PORT"] or "5432",
                            dbname=params["NAME"], user=name, password=password)
    try:
        assert denied(conn, "SET ROLE iris_authz_verifier")
    finally:
        conn.close()
