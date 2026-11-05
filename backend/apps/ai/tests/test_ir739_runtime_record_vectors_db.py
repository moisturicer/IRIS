"""The ``ai/`` runtime's Record stage follows the active Embedding Space (IR-739, ADR-049 §23).

``iris_ai.research_record_vectors(space)`` is what the runtime's ``semantic_search``
ranks Records on. It used to read the legacy table, which has no space key; it
now reads the space-keyed vectors for exactly the space asked for, and only while
that space is the active one, so the runtime's Record stage and Passage stage
(``research_vectors``) are always one space. Read here as the restricted runtime
login under a verified reader grant, on real PostgreSQL:

* before a promotion the active space answers and the pending one does not;
* a promotion moves the answer to the new space and silences the old one in the
  same instant, a rollback moves it back;
* the row-level policy still decides which Records the reader may see, so a
  Record deleted after the promotion is absent after a rollback too.
"""

import pytest

from apps.ai.grants import issue
from apps.ai.space_activation import activate_space
from apps.records.models import Record

from . import test_ai_runtime_runs_db as runs_db
from .grant_support import probe_login
from .test_space_activation import (  # builders shared with the unit suite
    NEW,
    build,
    factory,
    index_active,
    record,
)

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]
runtime = runs_db.runtime


def record_vector_owners(conn, token, space_id):
    """The Record ids ``research_record_vectors(space)`` returns to this verified reader."""
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT iris_authz.begin_research(%s, %s)", [token, "record_read"])
            cursor.execute("SELECT record_id FROM iris_ai.research_record_vectors(%s)", [space_id])
            return {row[0] for row in cursor.fetchall()}
    finally:
        conn.rollback()


def test_the_runtimes_record_stage_follows_promotion_and_rollback(runtime, active, pending, reader):
    papers = [record("Flood prediction", chunks=("rainfall flooding",)),
              record("Pond stocking", chunks=("tilapia ponds",))]
    for paper in papers:
        index_active(paper)
    build(pending, NEW)
    ids = {paper.pk for paper in papers}
    token = issue.record_read_grant(reader).token

    with probe_login("iris_ai_runtime") as conn:
        assert record_vector_owners(conn, token, active.pk) == ids
        assert record_vector_owners(conn, token, pending.pk) == set(), "a pending space is read by nothing"

        activate_space(pending.id, provider_factory=factory, verify_index=False)
        assert record_vector_owners(conn, token, pending.pk) == ids
        assert record_vector_owners(conn, token, active.pk) == set(), "the retired space answers nothing"

        activate_space(active.id, kind="rollback", provider_factory=factory, verify_index=False)
        assert record_vector_owners(conn, token, active.pk) == ids
        assert record_vector_owners(conn, token, pending.pk) == set()


def test_a_record_deleted_after_the_promotion_is_not_returned_after_a_rollback(
    runtime, active, pending, reader,
):
    kept = record("Kept", chunks=("rainfall flooding",))
    gone = record("Deleted later", chunks=("tilapia ponds",))
    for paper in (kept, gone):
        index_active(paper)
    build(pending, NEW)
    activate_space(pending.id, provider_factory=factory, verify_index=False)
    Record.objects.filter(pk=gone.pk).update(is_deleted=True)
    activate_space(active.id, kind="rollback", provider_factory=factory, verify_index=False)
    token = issue.record_read_grant(reader).token

    with probe_login("iris_ai_runtime") as conn:
        assert record_vector_owners(conn, token, active.pk) == {kept.pk}


def test_the_runtime_cannot_write_the_space_keyed_vectors(runtime, active, reader):
    import psycopg2

    index_active(record("Flood prediction", chunks=("rainfall flooding",)))

    with probe_login("iris_ai_runtime") as conn:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM public.ai_recordspaceembedding")
        conn.rollback()
