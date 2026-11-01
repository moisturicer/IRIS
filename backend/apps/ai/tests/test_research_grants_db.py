"""The research-grant verifier inside PostgreSQL, under a real restricted role (IR-717)."""

import pytest

from apps.ai.grants import issue
from .corpus import make_user
from .grant_support import grant_db, owned_run, probe_login  # noqa: F401

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
