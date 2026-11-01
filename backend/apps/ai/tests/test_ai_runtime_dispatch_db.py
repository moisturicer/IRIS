"""Durable dispatch and fair admission for AI-owned runs (IR-723, ADR-049 §2, §3, §12).

Real PostgreSQL under a restricted login; workers are independent processes
(`ai.tests.dispatch_worker`). Every bound here is a test value, not a
production one.
"""

import asyncio
import json
import subprocess
import sys
import time
from dataclasses import asdict, replace
from datetime import datetime

import asyncpg
import pytest
from django.db import connection

from apps.ai.grants import issue

# Importing the run suite puts the repo root, and so `ai`, on the path.
from . import test_ai_runtime_runs_db as runs_db
from .corpus import make_user
from .test_ai_runtime_runs_db import (
    DISPATCH, LIMITS, REPO, admin_dsn, as_reader, run, service, session, submit,
)
from ai.runs.dispatch import WAKEUP_KEY, PollingNotifier, RedisNotifier  # noqa: E402
from ai.runs.executor import Result  # noqa: E402
from ai.runs.store import Busy, RunStore  # noqa: E402

# The run suite's fixtures, shared by name.
api = runs_db.api
runtime = runs_db.runtime

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

REDIS_URL = "redis://localhost:6379/15"
APP = "iris-ai-runs"


class LostWakeup:
    """Redis is down: every wakeup fails after the run is committed."""

    async def notify(self):
        raise ConnectionError("redis unreachable")

    async def wait(self, timeout):
        await asyncio.sleep(timeout)


def queue_only(api, notifier=None, dispatch=DISPATCH):
    """Submissions are committed and left for workers."""
    client, holder = api
    holder["service"] = service(holder["dsn"], notifier=notifier or PollingNotifier(), dispatch=dispatch)
    return client, holder["service"]


@pytest.fixture
def queued(api, runtime):
    api[1]["dsn"] = runtime
    return api


def workers(runtime, count, *, ordinary=0.0, deep=0.0, idle=1.5, dispatch=DISPATCH, redis_url=""):
    spec = json.dumps({
        "limits": asdict(LIMITS), "dispatch": asdict(dispatch), "redis_url": redis_url,
        "ordinary_seconds": ordinary, "deep_seconds": deep, "idle_seconds": idle,
    })
    return [subprocess.Popen([sys.executable, "-m", "ai.tests.dispatch_worker", runtime, spec],
                             cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for _ in range(count)]


def finish(procs, timeout=90):
    ran = []
    for proc in procs:
        out, err = proc.communicate(timeout=timeout)
        assert proc.returncode == 0, err
        ran.append(int(out.strip()))
    return ran


def turns_of(conversation_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM iris_ai.turn WHERE conversation_id = %s", [conversation_id])
        return cursor.fetchone()[0]


def _wait_for_state(run_id, state, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute("SELECT state FROM iris_ai.ask_run WHERE id = %s", [run_id])
            if cursor.fetchone()[0] == state:
                return
        time.sleep(0.05)
    raise AssertionError(f"run never reached {state}")


def redis_or_skip():
    import redis

    client = redis.Redis.from_url(REDIS_URL, socket_connect_timeout=1)
    try:
        client.ping()
    except redis.exceptions.ConnectionError:
        pytest.skip("no Redis at localhost:6379")
    client.delete(WAKEUP_KEY)
    return client


# --- Durable work, wakeups and reconnecting ----------------------------------

def test_a_committed_run_survives_a_lost_wakeup_and_the_reader_leaving(queued, runtime):
    client, _ = queue_only(queued, LostWakeup())
    grant = session(make_user("dispatch-lost@cit.edu"))
    submitted = submit(client, grant, "request-lost")
    # The wakeup failed, but the run was committed first.
    assert submitted.status_code == 201
    run_ = submitted.json()
    assert run_["state"] == "queued" and run_["started_at"] is None
    assert run_["awaiting_reader"] is False
    # The reader goes away: no stream, no poll, and nothing cancels the run.

    assert sum(finish(workers(runtime, 2))) == 1
    reconnected = client.get(f"/api/v1/ai/runs/{run_['id']}", headers=as_reader(grant)).json()
    assert reconnected["state"] == "completed"
    assert [e["name"] for e in reconnected["events"]] == ["admitted", "started", "completed"]
    assert reconnected["latency_seconds"] >= reconnected["queued_seconds"] > 0
    assert turns_of(run_["conversation_id"]) == 1


def test_redelivered_wakeups_and_restarted_workers_deliver_one_turn(queued, runtime):
    redis = redis_or_skip()
    client, _ = queue_only(queued, RedisNotifier(REDIS_URL))
    grant = session(make_user("dispatch-redeliver@cit.edu"))
    run_ = submit(client, grant, "request-redeliver").json()
    assert redis.llen(WAKEUP_KEY) == 1
    # Redelivery: the same wakeup arrives again and again.
    redis.lpush(WAKEUP_KEY, 1, 1, 1)

    first = workers(runtime, 1, ordinary=30.0, idle=5, redis_url=REDIS_URL)
    _wait_for_state(run_["id"], "running")
    first[0].kill()  # Dispatch restarts mid-run; its lease is still held.
    first[0].communicate()
    with connection.cursor() as cursor:
        cursor.execute("UPDATE iris_ai.ask_run SET lease_expires_at = now() WHERE id = %s", [run_["id"]])
    assert sum(finish(workers(runtime, 3, idle=1.0, redis_url=REDIS_URL))) == 1

    status = client.get(f"/api/v1/ai/runs/{run_['id']}", headers=as_reader(grant)).json()
    names = [e["name"] for e in status["events"]]
    assert status["state"] == "completed" and names.count("completed") == 1
    assert turns_of(run_["conversation_id"]) == 1
    redis.delete(WAKEUP_KEY)


def test_a_reconnect_renews_a_lapsed_grant_but_never_widens_it(queued, runtime):
    client, svc = queue_only(queued)
    reader = make_user("dispatch-renew@cit.edu")

    run_ = submit(client, issue.reader_session_grant(reader, 41).token, "request-renew").json()
    with connection.cursor() as cursor:
        cursor.execute("UPDATE iris_ai.ask_run SET grant_expires_at = now() - interval '1 second'"
                       " WHERE id = %s", [run_["id"]])
    # A lapsed grant waits for its reader rather than running unauthorised.
    assert run(svc.run_next()) is False
    waiting = client.get(f"/api/v1/ai/runs/{run_['id']}", headers=as_reader(session(reader))).json()
    assert waiting["state"] == "queued" and waiting["awaiting_reader"] is True
    # That unscoped grant could see the run but did not become its authority.
    assert run(svc.run_next()) is False
    client.get(f"/api/v1/ai/runs/{run_['id']}",
               headers=as_reader(issue.reader_session_grant(reader, 41).token))
    assert run(svc.run_next()) is True
    with connection.cursor() as cursor:
        cursor.execute("SELECT state, reader_grant, grant_expires_at FROM iris_ai.ask_run WHERE id = %s",
                       [run_["id"]])
        assert cursor.fetchone() == ("completed", None, None)


# --- Deadlines and public states ---------------------------------------------

def test_queue_waiting_counts_against_the_original_deadline(queued, runtime):
    client, svc = queue_only(queued)
    grant = session(make_user("dispatch-deadline@cit.edu"))
    waiting = submit(client, grant, "request-wait").json()
    late = submit(client, grant, "request-late").json()
    with connection.cursor() as cursor:
        cursor.execute("UPDATE iris_ai.ask_run SET deadline_at = now() WHERE id = %s", [late["id"]])
    time.sleep(0.2)
    assert run(svc.run_next()) is True
    assert run(svc.run_next()) is False

    ran = client.get(f"/api/v1/ai/runs/{waiting['id']}", headers=as_reader(grant)).json()
    assert ran["deadline_at"] == waiting["deadline_at"]
    assert ran["queued_seconds"] >= 0.2
    expired = client.get(f"/api/v1/ai/runs/{late['id']}", headers=as_reader(grant)).json()
    assert (expired["state"], expired["end_reason"], expired["started_at"]) == ("expired", "deadline", None)
    assert expired["queued_seconds"] == expired["latency_seconds"]


def test_deep_and_ordinary_keep_their_own_deadlines(queued):
    client, _ = queue_only(queued)
    grant = session(make_user("dispatch-depth@cit.edu"))

    def span(body):
        return (datetime.fromisoformat(body["deadline_at"])
                - datetime.fromisoformat(body["created_at"])).total_seconds()

    ordinary = submit(client, grant, "request-ordinary").json()
    deep = submit(client, grant, "request-deep", depth="deep").json()
    assert ordinary["depth"] == "ordinary" and deep["depth"] == "deep"
    assert round(span(ordinary)) == LIMITS.deadline_seconds
    assert round(span(deep)) == LIMITS.deep_deadline_seconds
    assert submit(client, grant, "request-odd", depth="thorough").status_code == 422


def test_full_queues_answer_busy_and_write_nothing(queued):
    tight = replace(DISPATCH, max_queued=2, max_active_per_reader=1)
    client, _ = queue_only(queued, dispatch=tight)
    one = session(make_user("dispatch-busy-1@cit.edu"))
    two = session(make_user("dispatch-busy-2@cit.edu"))
    three = session(make_user("dispatch-busy-3@cit.edu"))
    first = submit(client, one, "request-busy-1")
    assert first.status_code == 201
    mine = submit(client, one, "request-busy-2")
    assert (mine.status_code, mine.json()) == (503, {"status": "busy", "reason": "reader_queue_full"})
    # A repeated identity is the same run, not new work.
    assert submit(client, one, "request-busy-1").status_code == 200
    assert submit(client, two, "request-busy-3").status_code == 201
    full = submit(client, three, "request-busy-4")
    assert (full.status_code, full.json()) == (503, {"status": "busy", "reason": "queue_full"})
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM iris_ai.ask_run")
        assert cursor.fetchone()[0] == 2


def test_one_run_advances_a_conversation_while_queued(queued):
    client, _ = queue_only(queued)
    grant = session(make_user("dispatch-revision@cit.edu"))
    first = submit(client, grant, "request-rev-a").json()
    conversation = first["conversation_id"]
    second = submit(client, grant, "request-rev-b", "Now the second paper",
                    conversation_id=conversation, base_revision=0)
    assert (second.status_code, second.json()) == (409, {"status": "run_in_progress", "run_id": first["id"]})
    stale = submit(client, grant, "request-rev-c", conversation_id=conversation, base_revision=3)
    assert stale.json() == {"status": "revision_conflict", "revision": 0}


# --- Fair claiming -----------------------------------------------------------

def _admit(store, grant, key, depth="ordinary"):
    row, _ = run(store.admit(grant, key=key, question=f"{depth}: {key}", conversation_id=None,
                             base_revision=None, deadline_seconds=60, allowance=LIMITS.allowance(),
                             pinned={}, depth=depth))
    return row["id"]


def _next(store, deep=1, per_reader=4):
    claim = run(store.claim_next(worker="w", lease_seconds=30, executor="x", reserved_units=1,
                                 deep_concurrency=deep, max_running_per_reader=per_reader))
    return claim and claim.run_id


def test_deep_runs_get_their_share_and_never_more(runtime):
    store = RunStore(runtime)
    grants = [session(make_user(f"dispatch-fair-{n}@cit.edu")) for n in range(4)]
    o1 = _admit(store, grants[0], "request-fair-o1")
    d1 = _admit(store, grants[1], "request-fair-d1", "deep")
    d2 = _admit(store, grants[2], "request-fair-d2", "deep")
    o2 = _admit(store, grants[3], "request-fair-o2")
    # Deep is owed a slot even behind older ordinary work, so it cannot starve.
    assert _next(store) == d1
    # At its cap, deep waits and ordinary keeps every other slot.
    assert [_next(store), _next(store), _next(store)] == [o1, o2, None]
    run(store.commit_final(d1, 1, Result(answer="a")))
    assert _next(store) == d2


def test_one_reader_cannot_hold_every_slot(runtime):
    store = RunStore(runtime)
    busy = session(make_user("dispatch-hog@cit.edu"))
    other = session(make_user("dispatch-polite@cit.edu"))
    first, second = _admit(store, busy, "request-hog-1"), _admit(store, busy, "request-hog-2")
    theirs = _admit(store, other, "request-polite-1")
    assert _next(store, per_reader=1) == first
    assert _next(store, per_reader=1) == theirs
    assert _next(store, per_reader=1) is None
    with connection.cursor() as cursor:
        cursor.execute("SELECT state FROM iris_ai.ask_run WHERE id = %s", [second])
        assert cursor.fetchone()[0] == "queued"


# --- A declared synthetic workload -------------------------------------------

def test_ordinary_capacity_is_protected_and_deep_work_completes(queued, runtime):
    """Two processes x two slots; deep capped at one, so three slots stay ordinary.

    Workload: 3 deep runs of 1.5 s and 6 ordinary runs of 0.2 s from nine
    readers, all queued before any worker starts.
    """
    client, _ = queue_only(queued)
    deep_seconds = 1.5
    ids = {"deep": [], "ordinary": []}
    for n in range(3):
        grant = session(make_user(f"dispatch-load-d{n}@cit.edu"))
        ids["deep"].append(submit(client, grant, f"request-load-d{n}", f"deep: {n}", depth="deep").json()["id"])
    for n in range(6):
        grant = session(make_user(f"dispatch-load-o{n}@cit.edu"))
        ids["ordinary"].append(submit(client, grant, f"request-load-o{n}", f"ordinary {n}").json()["id"])

    procs = workers(runtime, 2, ordinary=0.2, deep=deep_seconds, idle=1.5)
    peak = asyncio.run(_peak_connections(procs))
    assert sum(finish(procs)) == 9

    with connection.cursor() as cursor:
        cursor.execute("""SELECT id::text, depth, state, started_at, finished_at,
                                 extract(epoch FROM started_at - min(started_at) OVER ())
                            FROM iris_ai.ask_run""")
        rows = cursor.fetchall()
    assert {r[2] for r in rows} == {"completed"}
    intervals = [(r[3], r[4], r[1]) for r in rows]

    def most_at_once(kind=None):
        chosen = [(s, f) for s, f, d in intervals if kind in (None, d)]
        return max(sum(1 for s, f in chosen if s <= t < f) for t, _ in chosen)

    assert most_at_once("deep") == 1
    assert most_at_once() <= 2 * DISPATCH.worker_concurrency
    # Every ordinary question started before the first deep one could end:
    # none waited behind deep work (measured from the first claim, so
    # process start-up is not counted).
    assert max(float(r[5]) for r in rows if r[1] == "ordinary") < deep_seconds
    # Each slot holds one connection at most, plus nothing idle.
    assert peak <= 2 * DISPATCH.worker_concurrency


async def _peak_connections(procs):
    conn = await asyncpg.connect(admin_dsn())
    peak = 0
    try:
        while any(p.poll() is None for p in procs):
            peak = max(peak, await conn.fetchval(
                "SELECT count(*) FROM pg_stat_activity WHERE application_name = $1", APP))
            await asyncio.sleep(0.02)
    finally:
        await conn.close()
    return peak


def test_busy_is_raised_before_any_write(runtime):
    store = RunStore(runtime)
    grant = session(make_user("dispatch-store-busy@cit.edu"))
    with pytest.raises(Busy):
        run(store.admit(grant, key="busy-store", question="q", conversation_id=None,
                        base_revision=None, deadline_seconds=60, allowance=LIMITS.allowance(),
                        pinned={}, max_queued=0))
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM iris_ai.conversation")
        assert cursor.fetchone()[0] == 0
