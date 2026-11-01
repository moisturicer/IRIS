"""One research-read policy in PostgreSQL, compared with `visible_to` under real restricted roles (IR-718)."""

import pytest

from apps.ai.grants import issue
from apps.records.models import Record, RecordOwner
from core.enums import PipelineStatus
from core.permissions import ROLE_ADVISER, ROLE_STUDENT, STAFF_ROLES
from .corpus import make_record, make_user
from .grant_support import grant_db, owned_run, probe_login  # noqa: F401

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]


def begin(conn, grant, purpose):
    with conn.cursor() as cursor:
        cursor.execute("SELECT iris_authz.begin_research(%s, %s)", [grant, purpose])


def ids(conn, sql, params=()):
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        return {row[0] for row in cursor.fetchall()}


def read_as(conn, grant, purpose, sql="SELECT id FROM records_record", params=()):
    """Rows visible to one verified transaction, which is then ended.

    A grant PostgreSQL rejects reads nothing, as an empty set.
    """
    import psycopg2

    try:
        if grant is not None:
            try:
                begin(conn, grant, purpose)
            except psycopg2.errors.InsufficientPrivilege:
                return set()
        return ids(conn, sql, params)
    finally:
        conn.rollback()


@pytest.fixture
def world(grant_db, space, embedder):
    """Every ground `visible_to` has, plus soft deletion."""
    owner = make_user("rls-owner@cit.edu", ROLE_STUDENT)
    adviser = make_user("rls-adviser@cit.edu", ROLE_ADVISER)
    stranger = make_user("rls-stranger@cit.edu", ROLE_STUDENT)
    other = make_user("rls-other@cit.edu", ROLE_STUDENT)
    offices = {name: make_user(f"rls-{name.lower()}@cit.edu", name) for name in STAFF_ROLES}
    no_role = make_user("rls-norole@cit.edu", None)

    def record(title, status, owner_=None):
        return make_record(title=title, text=f"text of {title}", embedder=embedder,
                           space=space, status=status, owner=owner_)

    published = record("Public paper", PipelineStatus.PUBLISHED, other)
    draft = record("Owner draft", PipelineStatus.DRAFT, owner)
    Record.objects.filter(pk=draft.pk).update(adviser=adviser)
    foreign = record("Foreign draft", PipelineStatus.DRAFT, other)
    gone = record("Deleted paper", PipelineStatus.PUBLISHED, owner)
    Record.objects.filter(pk=gone.pk).update(is_deleted=True)
    return {
        "users": {"owner": owner, "adviser": adviser, "stranger": stranger, "other": other,
                  "no_role": no_role, **{f"office:{n}": u for n, u in offices.items()}},
        "records": {"published": published, "draft": draft, "foreign": foreign, "gone": gone},
    }


def expected(user):
    return set(Record.objects.visible_to(user).values_list("pk", flat=True))


def test_the_database_policy_matches_visible_to_in_both_runtimes(world):
    with probe_login("iris_django_runtime") as django_conn, probe_login("iris_ai_runtime") as ai_conn:
        for name, user in world["users"].items():
            want = expected(user)
            assert want, name
            django_read = read_as(django_conn, issue.record_read_grant(user).token, "record_read")
            ai_read = read_as(ai_conn, issue.reader_grant(user, owned_run(user)).token, "reader_run")
            assert django_read == want, name
            assert ai_read == want, name


def test_paper_chat_scope_narrows_to_its_record_and_never_widens(world):
    users, records = world["users"], world["records"]
    with probe_login("iris_ai_runtime") as conn:
        for user_name, record_name, want in (
            ("owner", "draft", {"draft"}),
            ("owner", "published", {"published"}),
            ("stranger", "draft", set()),
            ("stranger", "published", {"published"}),
            ("owner", "gone", set()),
        ):
            user, record = users[user_name], records[record_name]
            grant = issue.reader_grant(user, owned_run(user, record=record)).token
            got = read_as(conn, grant, "reader_run")
            assert got == {records[n].pk for n in want}, (user_name, record_name)


def test_no_verified_context_reads_nothing(world, space):
    from apps.ai.models import IngestionJob

    users, records = world["users"], world["records"]
    job = IngestionJob.objects.create(record=records["published"], extraction_hash="e" * 64,
                                      strategy_id="s", space=space, idempotency_key="j" * 64)
    with probe_login("iris_ai_runtime") as conn:
        assert read_as(conn, None, None) == set()
        with conn.cursor() as cursor:
            cursor.execute("SET iris.research_grant = 'irg1.k1.x.y'")
            cursor.execute("SET iris.research_purpose = 'record_read'")
            cursor.execute("SET iris.research_bind = 'forged'")
        assert read_as(conn, None, None) == set()
        with conn.cursor() as cursor:
            cursor.execute("RESET ALL")
        conn.commit()
        # A job grant verifies, and still reads no content until IR-737.
        begin(conn, issue.ingestion_grant(job).token, "ingestion")
        for sql in DEPENDENT_READS.values():
            assert ids(conn, sql) == set(), sql
        assert ids(conn, "SELECT id FROM records_record") == set()
        conn.rollback()


def test_disabled_accounts_and_revoked_grounds_read_nothing_next_time(world):
    from apps.ai.grants.issue import GrantRefused
    from django.contrib.auth import get_user_model

    User = get_user_model()
    users, records = world["users"], world["records"]
    owner, adviser = users["owner"], users["adviser"]
    with probe_login("iris_django_runtime") as conn:
        owner_grant = issue.record_read_grant(owner).token
        adviser_grant = issue.record_read_grant(adviser).token
        assert records["draft"].pk in read_as(conn, owner_grant, "record_read")
        assert records["draft"].pk in read_as(conn, adviser_grant, "record_read")

        RecordOwner.objects.filter(record=records["draft"], user=owner).delete()
        Record.objects.filter(pk=records["draft"].pk).update(adviser=None)
        assert records["draft"].pk not in read_as(conn, owner_grant, "record_read")
        assert records["draft"].pk not in read_as(conn, adviser_grant, "record_read")

        Record.objects.filter(pk=records["published"].pk).update(is_deleted=True)
        assert records["published"].pk not in read_as(conn, owner_grant, "record_read")

        User.objects.filter(pk=owner.pk).update(is_active=False)
        assert read_as(conn, owner_grant, "record_read") == set()
        with pytest.raises(GrantRefused):
            issue.record_read_grant(User.objects.get(pk=owner.pk))
        User.objects.filter(pk=adviser.pk).update(is_locked=True)
        assert read_as(conn, adviser_grant, "record_read") == set()


#: Each protected relation and how a direct read reaches its Record.
DEPENDENT_READS = {
    "records_recordowner": "SELECT record_id FROM records_recordowner",
    "records_author": "SELECT record_id FROM records_author",
    "documents_pdfextraction": "SELECT record_id FROM documents_pdfextraction",
    "ai_chunkset": "SELECT record_id FROM ai_chunkset",
    "ai_documentchunk": "SELECT record_id FROM ai_documentchunk",
    "ai_chunkembedding": "SELECT c.record_id FROM ai_chunkembedding e "
                         "JOIN ai_documentchunk c ON c.id = e.chunk_id",
    "ai_recordembedding": "SELECT record_id FROM ai_recordembedding",
}


def _content(records):
    from apps.documents.models import PdfExtraction
    from apps.records.models import Author

    for record in records.values():
        Author.objects.create(record=record, name=f"Author of {record.title}")
        PdfExtraction.objects.create(record=record, status="done", extracted_text="full text")


def test_dependent_relations_cannot_evade_the_policy(world):
    from apps.ai.models.chunk import ChunkEmbedding

    users, records = world["users"], world["records"]
    _content(records)
    stranger = users["stranger"]
    want = expected(stranger)
    assert records["draft"].pk not in want
    with probe_login("iris_ai_runtime") as conn:
        grant = issue.reader_grant(stranger, owned_run(stranger)).token
        for table, sql in DEPENDENT_READS.items():
            assert read_as(conn, grant, "reader_run", sql) == want, table
            assert read_as(conn, None, None, sql) == set(), table
        # Embedding rows carry no record_id: read them bare, by chunk.
        chunk_ids = read_as(conn, grant, "reader_run", "SELECT chunk_id FROM ai_chunkembedding")
        assert chunk_ids == set(ChunkEmbedding.objects.filter(
            chunk__record__in=want).values_list("chunk_id", flat=True))
        assert read_as(conn, None, None, "SELECT chunk_id FROM ai_chunkembedding") == set()


def test_aggregates_and_lookups_reveal_nothing_about_hidden_records(world):
    users, records = world["users"], world["records"]
    stranger = users["stranger"]
    hidden, missing = records["foreign"].pk, 10**9
    with probe_login("iris_ai_runtime") as conn:
        grant = issue.reader_grant(stranger, owned_run(stranger)).token
        total = read_as(conn, grant, "reader_run", "SELECT count(*) FROM records_record")
        assert total == {len(expected(stranger))}
        for record_id in (hidden, missing):
            for sql in ("SELECT count(*) FROM records_record WHERE id = %s",
                        "SELECT count(*) FROM ai_documentchunk WHERE record_id = %s",
                        "SELECT count(*) FROM records_recordowner WHERE record_id = %s"):
                assert read_as(conn, grant, "reader_run", sql, [record_id]) == {0}
            assert read_as(conn, grant, "reader_run",
                           "SELECT title FROM records_record WHERE id = %s", [record_id]) == set()


def test_runtime_roles_cannot_write_research_relations(world):
    import psycopg2

    users, records = world["users"], world["records"]
    office = users["office:RDCO"]
    statements = (
        ("UPDATE records_record SET title = 'x' WHERE id = %s", [records["published"].pk]),
        ("DELETE FROM ai_documentchunk WHERE record_id = %s", [records["published"].pk]),
        ("INSERT INTO records_recordowner (record_id, user_id, is_primary) VALUES (%s, %s, false)",
         [records["draft"].pk, office.pk]),
    )
    for group in ("iris_ai_runtime", "iris_django_runtime"):
        with probe_login(group) as conn:
            grant = issue.record_read_grant(office).token
            for sql, params in statements:
                begin(conn, grant, "record_read") if group == "iris_django_runtime" else None
                with pytest.raises(psycopg2.errors.InsufficientPrivilege), conn.cursor() as cursor:
                    cursor.execute(sql, params)
                conn.rollback()
    assert Record.objects.get(pk=records["published"].pk).title == "Public paper"


def test_the_policy_names_the_same_offices_and_catalogue_as_visible_to():
    import importlib

    from core.enums import PUBLICLY_VISIBLE_STATUSES

    migration = importlib.import_module("apps.ai.migrations.0035_research_read_policy")
    assert set(migration.OFFICE_ROLES) == {str(role) for role in STAFF_ROLES}
    assert set(migration.PUBLIC_STATUSES) == {str(s) for s in PUBLICLY_VISIBLE_STATUSES}


def test_every_protected_table_has_row_security_and_its_policy(db):
    from django.db import connection

    from apps.ai.grants.policy import PROTECTED_TABLES

    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT c.relname FROM pg_class c JOIN pg_policy p ON p.polrelid = c.oid
                WHERE c.relrowsecurity AND p.polname = 'iris_research_read'""")
        assert {row[0] for row in cursor.fetchall()} == set(PROTECTED_TABLES)


def test_the_role_check_reports_missing_row_security_and_runtime_write_privileges(grant_db):
    from django.core.management import CommandError, call_command
    from django.db import connection

    call_command("provision_research_roles", "--check")
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE public.ai_documentchunk DISABLE ROW LEVEL SECURITY")
        cursor.execute("GRANT UPDATE ON public.records_record TO iris_ai_runtime")
    try:
        with pytest.raises(CommandError):
            call_command("provision_research_roles", "--check")
    finally:
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE public.ai_documentchunk ENABLE ROW LEVEL SECURITY")
            cursor.execute("REVOKE UPDATE ON public.records_record FROM iris_ai_runtime")
    # Provisioning repairs privileges, never row security, which is migrate's.
    call_command("provision_research_roles", "--check")


def test_problems_name_what_is_wrong(grant_db):
    from django.db import connection

    from apps.ai.management.commands.provision_research_roles import problems

    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE public.ai_documentchunk DISABLE ROW LEVEL SECURITY")
        cursor.execute("GRANT DELETE ON public.records_author TO iris_django_runtime")
        try:
            found = problems(cursor)
        finally:
            cursor.execute("ALTER TABLE public.ai_documentchunk ENABLE ROW LEVEL SECURITY")
            cursor.execute("REVOKE DELETE ON public.records_author FROM iris_django_runtime")
    assert "ai_documentchunk has no row security" in found
    assert "role iris_django_runtime can write records_author" in found


def test_force_row_security_is_an_explicit_cutover_step(world):
    from django.core.management import call_command
    from django.db import connection

    from apps.ai.grants.policy import PROTECTED_TABLES

    def forced():
        with connection.cursor() as cursor:
            cursor.execute("SELECT relname FROM pg_class WHERE relforcerowsecurity "
                           "AND relname = ANY(%s)", [list(PROTECTED_TABLES)])
            return {row[0] for row in cursor.fetchall()}

    assert forced() == set()
    call_command("provision_research_roles", "--force-row-security")
    try:
        assert forced() == set(PROTECTED_TABLES)
        stranger = world["users"]["stranger"]
        with probe_login("iris_ai_runtime") as conn:
            grant = issue.reader_grant(stranger, owned_run(stranger)).token
            assert read_as(conn, grant, "reader_run") == expected(stranger)
    finally:
        with connection.cursor() as cursor:
            for table in PROTECTED_TABLES:
                cursor.execute(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY")


@pytest.mark.parametrize("group", ["iris_ai_runtime", "iris_django_runtime"])
def test_the_migration_refuses_to_run_as_a_runtime_login(grant_db, group):
    import importlib

    import psycopg2

    migration = importlib.import_module("apps.ai.migrations.0035_research_read_policy")
    with probe_login(group) as conn:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege, match="runtime"), \
                conn.cursor() as cursor:
            cursor.execute(migration.REFUSE_RUNTIME_LOGIN)
        conn.rollback()


def test_an_authenticated_django_read_agrees_with_the_ai_side_read(world, client_for):
    from django.urls import reverse

    records = world["records"]
    missing = 10**9
    with probe_login("iris_ai_runtime") as conn:
        for name, user in world["users"].items():
            allowed = read_as(conn, issue.reader_grant(user, owned_run(user)).token, "reader_run")
            client = client_for(user)
            for record in records.values():
                status = client.get(reverse("record-detail", args=[record.pk])).status_code
                assert status == (200 if record.pk in allowed else 404), (name, record.title)
            denied = [r.pk for r in records.values() if r.pk not in allowed]
            if denied:
                hidden = client.get(reverse("record-detail", args=[denied[0]]))
                absent = client.get(reverse("record-detail", args=[missing]))
                assert hidden.status_code == absent.status_code == 404
                assert hidden.json() == absent.json(), name


def test_policy_tables_match_the_policies_postgres_holds(db):
    from django.db import connection

    from apps.ai.grants.policy import PROTECTED_TABLES

    with connection.cursor() as cursor:
        cursor.execute("SELECT tablename, policyname, cmd FROM pg_policies WHERE schemaname = 'public'")
        rows = cursor.fetchall()
    assert {table for table, _, _ in rows} == set(PROTECTED_TABLES)
    assert {(name, cmd) for _, name, cmd in rows} == {("iris_research_read", "SELECT")}


@pytest.mark.parametrize("group", ["iris_ai_runtime", "iris_django_runtime"])
def test_migrate_refuses_a_runtime_login_in_any_direction(grant_db, group):
    from django.core.management import call_command
    from django.db import connection

    from .grant_support import connected_as, probe_credentials

    with probe_credentials(group) as (name, password):
        with connection.cursor() as cursor:
            # Enough to reach migrate's own checks.
            cursor.execute(f'GRANT SELECT ON django_migrations TO "{name}"')
        with connected_as(name, password), pytest.raises(Exception, match="runtime login"):
            call_command("migrate", "ai", verbosity=0)
