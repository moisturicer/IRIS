"""Pooled runtime connections on real PostgreSQL (IR-1012).

A process's pool is bounded and reused, an exhausted one makes the store
`busy` (503, never 500), and a returned connection carries no reader's grant.
"""

import asyncio

import asyncpg
import pytest

# Imported first: it puts the repository root on sys.path for `ai`.
from .test_ai_runtime_runs_db import admin_dsn, api, runtime, service, session  # noqa: F401
from .corpus import make_user

from ai.infrastructure import db  # noqa: E402
from ai.runs.store import Busy, RunStore  # noqa: E402

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]


def run(coro):
    """A pool belongs to its loop, so close this loop's before it ends."""
    async def closing():
        try:
            return await coro
        finally:
            await db.close()

    return asyncio.run(closing())


#: Generous: opening a connection can take seconds on a developer machine.
ACQUIRE = 15.0


@pytest.fixture
def pooled(runtime):  # noqa: F811
    db.configure(runtime, db.PoolSize(2, ACQUIRE))
    yield runtime
    db.unconfigure(runtime)


async def _pooled_backends():
    conn = await asyncpg.connect(admin_dsn())
    try:
        return await conn.fetchval(
            "SELECT count(*) FROM pg_stat_activity WHERE application_name = $1", db.APP_NAME)
    finally:
        await conn.close()


def test_many_readers_at_once_share_a_bounded_pool(pooled):
    grants = [session(make_user(f"pool-reader-{i}@cit.edu")) for i in range(10)]

    async def go():
        store = RunStore(pooled)
        listed = await asyncio.gather(*(store.list_conversations(g) for g in grants))
        return listed, await _pooled_backends()

    listed, backends = run(go())
    assert listed == [[]] * 10
    assert 1 <= backends <= 2


def test_an_exhausted_pool_makes_the_store_busy(pooled):
    grant = session(make_user("pool-busy@cit.edu"))

    async def go():
        async with db.connection(pooled), db.connection(pooled):
            db.configure(pooled, db.PoolSize(2, 0.2))
            with pytest.raises(Busy) as busy:
                await RunStore(pooled).list_conversations(grant)
        return busy.value.reason

    assert run(go()) == "database"


def test_a_refused_connection_answers_the_reader_503_busy(api, runtime):  # noqa: F811
    client, holder = api
    grant = session(make_user("pool-route@cit.edu"))
    # Nothing listens on port 1: PostgreSQL down or restarting.
    closed = runtime.rsplit("@", 1)[0] + "@127.0.0.1:1/" + runtime.rsplit("/", 1)[1]
    holder["service"] = service(closed)
    db.configure(closed, db.PoolSize(2, ACQUIRE))
    try:
        response = client.post("/api/v1/ai/runs", json={"question": "q"},
                               headers={"X-IRIS-Reader-Grant": grant, "Idempotency-Key": "request-busy"})
    finally:
        db.unconfigure(closed)
    assert response.status_code == 503
    assert response.json() == {"status": "busy", "reason": "database"}


def test_a_returned_connection_carries_no_readers_grant(runtime):  # noqa: F811
    db.configure(runtime, db.PoolSize(1, ACQUIRE))
    grant = session(make_user("pool-grant@cit.edu"))

    async def go():
        async with db.connection(runtime) as conn, conn.transaction():
            await conn.fetchval("SELECT iris_authz.begin_research($1, 'reader_session')", grant)
            first = conn.get_server_pid()
        async with db.connection(runtime) as conn:
            return first == conn.get_server_pid(), await conn.fetchval(
                "SELECT current_setting('iris.research_grant', true)")

    try:
        same, left = run(go())
    finally:
        db.unconfigure(runtime)
    assert same
    assert not left


def test_a_submission_still_completes_through_the_pool(pooled):
    grant = session(make_user("pool-submit@cit.edu"))
    run_, created = run(service(pooled).submit(
        grant, key="request-pooled", question="q", conversation_id=None, base_revision=None))
    assert created and run_["state"] == "completed"
