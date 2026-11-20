"""Ask IRIS reads only papers that may reach the AI (IR-1252, ADR-052 as amended 2026-11-21).

`iris_authz.research_record_ids()` under a `reader_session` grant (the AI
runtime's) must return exactly the papers the reader may open that Django's
disclosure gate also allows: published and not deleted, released from embargo,
consented, and any IP mark released. These tests pin the database check to
`Record.objects.visible_to` and `disclosure_permits` on the same papers, so the
two definitions can't drift. Django's own `record_read` purpose still reads by
visibility alone (`test_research_reads`).
"""

import pytest
from django.utils import timezone

from apps.ai.grants import issue
from apps.ai.policy.outbound import disclosure_permits
from apps.records.models import Record, RecordOwner
from core.enums import PipelineStatus
from core.permissions import ROLE_ADVISER, ROLE_RDCO, ROLE_STUDENT
from .corpus import make_user
from .grant_support import probe_login

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

READERS = ("owner", "adviser", "office", "stranger")


def _paper(title, owner, adviser, *, status=PipelineStatus.PUBLISHED, released=True,
           consent=True, ip=None, deleted=False):
    """`ip` is None (no mark), "marked" (KTTO hasn't released it) or "released"."""
    record = Record.objects.create(title=title, abstract="a", pipeline_status=status,
                                   adviser=adviser, added_by=owner)
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    now = timezone.now()
    Record.objects.filter(pk=record.pk).update(
        ai_consent=consent, is_deleted=deleted, is_ip=ip is not None,
        ip_released_at=now if ip == "released" else None,
        **({"is_embargoed": False, "embargo_released_at": now} if released else {}),
    )
    return record


@pytest.fixture
def papers():
    owner = make_user("disclose-owner@cit.edu", ROLE_STUDENT)
    adviser = make_user("disclose-adviser@cit.edu", ROLE_ADVISER)
    people = {
        "owner": owner, "adviser": adviser,
        "office": make_user("disclose-office@cit.edu", ROLE_RDCO),
        "stranger": make_user("disclose-stranger@cit.edu", ROLE_STUDENT),
    }
    made = {
        "published": _paper("Published and released", owner, adviser),
        "ip released": _paper("IP released by KTTO", owner, adviser, ip="released"),
        "embargoed": _paper("Published, embargoed again", owner, adviser, released=False),
        "no consent": _paper("Published, no consent", owner, adviser, consent=None),
        "said no": _paper("Published, said no", owner, adviser, consent=False),
        "ip marked": _paper("Published, IP not released", owner, adviser, ip="marked"),
        "deleted": _paper("Published, deleted", owner, adviser, deleted=True),
        "in review": _paper("Released, in review", owner, adviser, status=PipelineStatus.IN_REVIEW),
        "unlisted": _paper("Released, kept unlisted", owner, adviser, status=PipelineStatus.COMPLETED),
        "accepted": _paper("Released Proposal, accepted", owner, adviser, status=PipelineStatus.APPROVED),
        "draft": _paper("Released draft", owner, adviser, status=PipelineStatus.DRAFT),
    }
    return people, made


def runtime_ids(user, record_id=None):
    """The records the AI runtime's grant may read, read as `iris_ai_runtime`."""
    token = issue.reader_session_grant(user, record_id).token
    with probe_login("iris_ai_runtime") as conn:
        with conn, conn.cursor() as cursor:
            cursor.execute("SELECT iris_authz.begin_research(%s, 'reader_session')", [token])
            cursor.execute("SELECT id FROM records_record")
            return {row[0] for row in cursor.fetchall()}


def gate_ids(user):
    return {r.pk for r in Record.objects.visible_to(user) if disclosure_permits(r)}


def test_only_published_released_papers_reach_the_runtime(grant_db, papers):
    people, made = papers
    expected = {made["published"].pk, made["ip released"].pk}
    for key in READERS:
        assert runtime_ids(people[key]) == expected, key


def test_the_database_check_agrees_with_the_python_gate(grant_db, papers):
    """One definition: neither side may let a paper through the other refuses."""
    people, _ = papers
    for key in READERS:
        assert runtime_ids(people[key]) == gate_ids(people[key]), key


def test_a_paper_chat_scope_on_an_unpublished_paper_reads_nothing(grant_db, papers):
    people, made = papers
    assert runtime_ids(people["owner"], made["in review"].pk) == set()
    assert runtime_ids(people["owner"], made["published"].pk) == {made["published"].pk}


def test_django_s_own_reads_still_go_by_visibility(grant_db, papers):
    """`record_read` is Django's purpose; it shows a reader their papers, so it is not narrowed."""
    people, made = papers
    token = issue.record_read_grant(people["owner"]).token
    with probe_login("iris_django_runtime") as conn:
        with conn, conn.cursor() as cursor:
            cursor.execute("SELECT iris_authz.begin_research(%s, 'record_read')", [token])
            cursor.execute("SELECT id FROM records_record")
            found = {row[0] for row in cursor.fetchall()}
    assert made["in review"].pk in found and made["embargoed"].pk in found
