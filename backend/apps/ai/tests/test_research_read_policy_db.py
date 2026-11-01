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
    """Rows visible to one verified transaction, which is then ended."""
    try:
        if grant is not None:
            begin(conn, grant, purpose)
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
