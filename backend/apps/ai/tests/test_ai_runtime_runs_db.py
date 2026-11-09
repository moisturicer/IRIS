"""AI-owned runs on real PostgreSQL under a restricted login (IR-722, ADR-049 §1, §10).

The FastAPI routes and the run store, driven with Django-issued
`reader_session` grants verified inside PostgreSQL. Races use independent
processes on separate connections.
"""

import asyncio
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import asyncpg
import pytest
from django.db import connection

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.runs import config as runs_config  # noqa: E402
from ai.runs.executor import Citation, DeterministicExecutor, Result  # noqa: E402
from ai.runs.migrate import RefusedLogin, migrate  # noqa: E402
from ai.runs.service import RunService  # noqa: E402
from ai.runs.store import Fenced, RunStore  # noqa: E402
from apps.ai.grants import issue  # noqa: E402
from .corpus import make_user  # noqa: E402
from .grant_support import probe_credentials  # noqa: E402

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

SECRET = "ir722-service-secret"
LIMITS = runs_config.RunLimits(
    deadline_seconds=120, deep_deadline_seconds=600, lease_seconds=30, max_attempts=2,
    max_input_tokens=1000, max_output_tokens=500, max_cost_usd=0.5,
)
# Test bounds only; no production value is implied.
DISPATCH = runs_config.Dispatch(
    max_queued=50, max_active_per_reader=10, max_running_per_reader=4,
    deep_concurrency=1, worker_concurrency=2, poll_seconds=0.1,
)
IRIS_AI_TABLES = "iris_ai.research_handle, iris_ai.citation,iris_ai.run_event, iris_ai.turn, iris_ai.ask_run," \
                 " iris_ai.conversation_handoff, iris_ai.conversation, iris_ai.attempt_accounting, iris_ai.run_checkpoint"


def dsn(user, password):
    params = connection.settings_dict
    return (f"postgresql://{quote(user)}:{quote(password)}@{params['HOST'] or 'localhost'}:"
            f"{params['PORT'] or '5432'}/{params['NAME']}")


def admin_dsn():
    params = connection.settings_dict
    return dsn(params["USER"], params["PASSWORD"])


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def runtime(grant_db):
    """iris_ai migrated and a runtime login; iris_ai emptied afterwards."""
    run(migrate(admin_dsn()))
    with probe_credentials("iris_ai_runtime") as (name, password):
        yield dsn(name, password)
    with connection.cursor() as cursor:
        cursor.execute(f"TRUNCATE {IRIS_AI_TABLES}")


class ScriptedExecutor:
    name = "scripted"
    version = "1"
    reserved_units = 7

    def __init__(self, result=None, probe=None):
        self.result = result or Result(answer="Scripted answer.")
        self.probe = probe
        self.calls = 0

    async def answer(self, question, tools):
        self.calls += 1
        if self.probe:
            await self.probe()
        return self.result


class Drain:
    """A wakeup that runs the queue in-process, so a submission returns finished."""

    def __init__(self):
        self.service = None

    async def notify(self):
        while await self.service.run_next():
            pass

    async def wait(self, timeout):
        await asyncio.sleep(timeout)


def service(runtime_dsn, executor=None, notifier=None, dispatch=DISPATCH):
    """By default a submission is drained before it returns (IR-723 queues it)."""
    cfg = runs_config.RunsConfig(database_url=runtime_dsn, executor="deterministic",
                                 limits=LIMITS, dispatch=dispatch)
    drain = notifier is None
    built = RunService(RunStore(runtime_dsn), cfg, executor or DeterministicExecutor(),
                       Drain() if drain else notifier)
    if drain:
        built.notifier.service = built
    return built


@pytest.fixture
def api(runtime, monkeypatch):
    """A TestClient for the gateway whose run routes use `holder['service']`."""
    from fastapi.testclient import TestClient

    import ai.api.runs as runs_api
    import ai.main as gateway

    monkeypatch.setattr(gateway.settings, "SERVICE_SECRET", SECRET)
    holder = {"service": service(runtime)}
    gateway.app.dependency_overrides[runs_api._service] = lambda: holder["service"]
    client = TestClient(gateway.app, headers={"x-iris-service-secret": SECRET})
    yield client, holder
    gateway.app.dependency_overrides.clear()


def session(user):
    return issue.reader_session_grant(user).token


def submit(client, grant, key, question="What did the paper find?", **body):
    headers = {"Idempotency-Key": key}
    if grant is not None:
        headers["X-IRIS-Reader-Grant"] = grant
    return client.post("/api/v1/ai/runs", json={"question": question, **body}, headers=headers)


def as_reader(grant):
    return {"X-IRIS-Reader-Grant": grant}


# --- The reader's routes -----------------------------------------------------

def test_a_repeated_submission_is_one_run_and_one_turn(api):
    client, _ = api
    reader = make_user("runs-once@cit.edu")
    grant = session(reader)
    first = submit(client, grant, "request-0001")
    again = submit(client, grant, "request-0001")
    assert first.status_code == 201 and again.status_code == 200
    run_ = first.json()
    assert again.json()["id"] == run_["id"]
    assert run_["state"] == "completed"
    assert [e["name"] for e in run_["events"]] == ["admitted", "started", "completed"]

    reopened = client.get(f"/api/v1/ai/conversations/{run_['conversation_id']}", headers=as_reader(grant))
    assert reopened.status_code == 200
    body = reopened.json()
    assert body["revision"] == 1
    assert [t["run_id"] for t in body["turns"]] == [run_["id"]]
    assert body["turns"][0]["answer"] == "Deterministic answer: What did the paper find?"


def test_the_original_deadline_allowance_and_versions_are_persisted(api):
    client, _ = api
    reader = make_user("runs-allowance@cit.edu")
    run_ = submit(client, session(reader), "request-allow").json()
    assert run_["allowance"] == LIMITS.allowance()
    assert run_["pinned"] == {
        "executor": "deterministic", "executor_version": "1",
        "protocol": "runs-1", "schema": "0004_agent.sql",
    }
    assert run_["version"] >= 1
    created = run_["created_at"]
    assert run_["deadline_at"] > created


def test_one_identity_with_a_different_question_is_refused(api):
    client, _ = api
    grant = session(make_user("runs-mismatch@cit.edu"))
    assert submit(client, grant, "request-same", "First").status_code == 201
    refused = submit(client, grant, "request-same", "Second")
    assert refused.status_code == 409
    assert refused.json() == {"status": "request_mismatch"}


def test_another_reader_cannot_inspect_stop_reopen_or_delete(api):
    client, _ = api
    owner = make_user("runs-owner@cit.edu")
    other = make_user("runs-other@cit.edu")
    run_ = submit(client, session(owner), "request-own").json()
    theirs = as_reader(session(other))
    missing = uuid.uuid4()
    for path, pk in (("/api/v1/ai/runs/", run_["id"]),
                     ("/api/v1/ai/conversations/", run_["conversation_id"])):
        foreign = client.get(f"{path}{pk}", headers=theirs)
        absent = client.get(f"{path}{missing}", headers=theirs)
        assert foreign.status_code == absent.status_code == 404
        assert foreign.json() == absent.json()
    assert client.post(f"/api/v1/ai/runs/{run_['id']}/cancel", headers=theirs).status_code == 404
    assert client.delete(f"/api/v1/ai/conversations/{run_['conversation_id']}",
                         headers=theirs).status_code == 404
    # The same identity under another reader is that reader's own run.
    own = submit(client, session(other), "request-own")
    assert own.status_code == 201 and own.json()["id"] != run_["id"]
    follow = submit(client, theirs["X-IRIS-Reader-Grant"], "request-intrude",
                    conversation_id=run_["conversation_id"], base_revision=1)
    assert follow.status_code == 404


def test_without_a_valid_reader_session_nothing_is_served(api):
    client, _ = api
    reader = make_user("runs-nogrant@cit.edu")
    assert submit(client, None, "request-anon").status_code == 401
    assert submit(client, "irg1.k1.forged.sig", "request-forged").status_code == 401
    run_grant = issue.record_read_grant(reader).token
    assert submit(client, run_grant, "request-wrong-purpose").status_code == 401
    bare = client.post("/api/v1/ai/runs", json={"question": "x"},
                       headers={"Idempotency-Key": "request-nosecret", "x-iris-service-secret": "",
                                **as_reader(session(reader))})
    assert bare.status_code == 401


def test_a_follow_up_on_a_moved_revision_is_a_recoverable_conflict(api):
    client, _ = api
    grant = session(make_user("runs-revision@cit.edu"))
    first = submit(client, grant, "request-rev-1").json()
    conversation = first["conversation_id"]
    second = submit(client, grant, "request-rev-2", "Compare the second paper",
                    conversation_id=conversation, base_revision=1)
    assert second.status_code == 201 and second.json()["state"] == "completed"
    # Asked against revision 1: "the second paper" may now mean something else.
    stale = submit(client, grant, "request-rev-3", "And the second paper?",
                   conversation_id=conversation, base_revision=1)
    assert stale.status_code == 409
    assert stale.json() == {"status": "revision_conflict", "revision": 2}
    retried = submit(client, grant, "request-rev-4", "And the second paper?",
                     conversation_id=conversation, base_revision=2)
    assert retried.status_code == 201
    turns = client.get(f"/api/v1/ai/conversations/{conversation}", headers=as_reader(grant)).json()["turns"]
    assert [t["ordinal"] for t in turns] == [1, 2, 3]


def test_a_second_run_waits_for_the_first_to_end(api, runtime):
    client, _ = api
    reader = make_user("runs-active@cit.edu")
    grant = session(reader)
    store = RunStore(runtime)
    row, _ = run(store.admit(grant, key="request-act-1", question="q", conversation_id=None,
                             base_revision=None, deadline_seconds=60,
                             allowance=LIMITS.allowance(), pinned={}))
    busy = submit(client, grant, "request-act-2", conversation_id=str(row["conversation_id"]),
                  base_revision=0)
    assert busy.status_code == 409
    assert busy.json() == {"status": "run_in_progress", "run_id": str(row["id"])}


def test_an_overdue_run_no_longer_holds_its_conversation(api, runtime):
    client, _ = api
    grant = session(make_user("runs-overdue@cit.edu"))
    store, row, claim = _admit_and_claim(runtime, grant, "request-overdue")
    with connection.cursor() as cursor:
        cursor.execute("UPDATE iris_ai.ask_run SET deadline_at = now() WHERE id = %s", [row["id"]])
    # Its worker died; the next question expires it rather than waiting forever.
    next_ = submit(client, grant, "request-overdue-2", conversation_id=str(row["conversation_id"]),
                   base_revision=0)
    assert next_.status_code == 201 and next_.json()["state"] == "completed"
    assert run(store.status(grant, row["id"]))["state"] == "expired"
    assert run(store.commit_final(row["id"], claim.fence, Result(answer="late"))) == "expired"


def test_a_run_past_its_deadline_is_ended_not_claimed(runtime):
    grant = session(make_user("runs-deadline@cit.edu"))
    store = RunStore(runtime)
    row, _ = run(store.admit(grant, key="request-deadline", question="q", conversation_id=None,
                             base_revision=None, deadline_seconds=60,
                             allowance=LIMITS.allowance(), pinned={}))
    with connection.cursor() as cursor:
        cursor.execute("UPDATE iris_ai.ask_run SET deadline_at = now() WHERE id = %s", [row["id"]])
    assert run(store.claim(row["id"], worker="w", lease_seconds=30, executor="x", reserved_units=1)) is None
    status = run(store.status(grant, row["id"]))
    assert status["state"] == "expired" and status["end_reason"] == "deadline"


def test_stop_ends_a_run_and_no_later_commit_publishes(api, runtime):
    client, _ = api
    grant = session(make_user("runs-stop@cit.edu"))
    store = RunStore(runtime)
    row, _ = run(store.admit(grant, key="request-stop", question="q", conversation_id=None,
                             base_revision=None, deadline_seconds=60,
                             allowance=LIMITS.allowance(), pinned={}))
    claim = run(store.claim(row["id"], worker="w", lease_seconds=30, executor="x", reserved_units=3))
    stopped = client.post(f"/api/v1/ai/runs/{row['id']}/cancel", headers=as_reader(grant))
    assert stopped.status_code == 200 and stopped.json()["state"] == "cancelled"
    # An ended run stays ended; the late attempt writes nothing.
    assert run(store.commit_final(row["id"], claim.fence, Result(answer="late"))) == "cancelled"
    again = client.post(f"/api/v1/ai/runs/{row['id']}/cancel", headers=as_reader(grant))
    assert again.json()["state"] == "cancelled"
    reopened = client.get(f"/api/v1/ai/conversations/{row['conversation_id']}", headers=as_reader(grant))
    assert reopened.json() == {"id": str(row["conversation_id"]), "revision": 0, "turns": []}


def test_missing_limits_refuse_every_submission(api, monkeypatch):
    import ai.api.runs as runs_api
    import ai.main as gateway
    from ai.infrastructure.settings import Settings

    client, _ = api
    gateway.app.dependency_overrides.clear()
    unset = Settings(_env_file=None, RUNS_DATABASE_URL="postgresql://x", RUNS_DEADLINE_SECONDS=60)
    monkeypatch.setattr("ai.infrastructure.settings.settings", unset)
    assert runs_api._service() is None
    response = submit(client, session(make_user("runs-unset@cit.edu")), "request-unset")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


# --- The run store -----------------------------------------------------------

def test_the_executor_runs_with_no_transaction_or_connection_open(runtime):
    grant = session(make_user("runs-transport@cit.edu"))
    seen = []

    async def probe():
        conn = await asyncpg.connect(admin_dsn())
        try:
            seen.append(await conn.fetchval(
                "SELECT count(*) FROM pg_stat_activity WHERE application_name = 'iris-ai-runs'"
            ))
        finally:
            await conn.close()

    executor = ScriptedExecutor(probe=probe)
    run_, created = run(service(runtime, executor).submit(
        grant, key="request-transport", question="q", conversation_id=None, base_revision=None))
    assert created and run_["state"] == "completed"
    assert executor.calls == 1 and seen == [0]


def test_turn_citations_revision_and_journal_commit_together(runtime):
    grant = session(make_user("runs-atomic@cit.edu"))
    good = Result(answer="Cited.", citations=(Citation(record_id=11, page=3, quote="a"),
                                              Citation(record_id=12, page=None, quote="b")))
    run_, _ = run(service(runtime, ScriptedExecutor(good)).submit(
        grant, key="request-atomic-1", question="q", conversation_id=None, base_revision=None))
    reopened = run(RunStore(runtime).reopen(grant, run_["conversation_id"]))
    assert reopened["revision"] == 1
    assert reopened["turns"][0]["citations"] == [
        {"record_id": 11, "page": 3, "quote": "a", "revision": None, "regions": []},
        {"record_id": 12, "page": None, "quote": "b", "revision": None, "regions": []},
    ]

    # The second citation violates a constraint after the Turn row is written.
    bad = Result(answer="Half.", citations=(Citation(record_id=1, page=1, quote="ok"),
                                            Citation(record_id=2, page=0, quote="bad")))
    failed, _ = run(service(runtime, ScriptedExecutor(bad)).submit(
        grant, key="request-atomic-2", question="q2",
        conversation_id=uuid.UUID(run_["conversation_id"]), base_revision=1))
    assert failed["state"] == "failed" and failed["end_reason"] == "commit_failed"
    assert failed["turn_id"] is None
    after = run(RunStore(runtime).reopen(grant, run_["conversation_id"]))
    assert after["revision"] == 1 and len(after["turns"]) == 1
    # The second run was given Turn 1 as history, so its claim records that (IR-721).
    assert [e["name"] for e in failed["events"]] == ["admitted", "started", "carried", "failed"]


def _admit_and_claim(runtime, grant, key):
    store = RunStore(runtime)
    row, _ = run(store.admit(grant, key=key, question="q", conversation_id=None,
                             base_revision=None, deadline_seconds=60,
                             allowance=LIMITS.allowance(), pinned={}))
    claim = run(store.claim(row["id"], worker="w", lease_seconds=30, executor="x", reserved_units=5))
    return store, row, claim


def _race(runtime, commands):
    """Start every worker blocked on one lock, release them together, collect outputs."""
    loop = asyncio.new_event_loop()
    holder = loop.run_until_complete(asyncpg.connect(admin_dsn()))
    try:
        loop.run_until_complete(holder.execute("SELECT pg_advisory_lock(722)"))
        procs = [subprocess.Popen([sys.executable, "-m", "ai.tests.race_worker", runtime, *cmd],
                                  cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for cmd in commands]
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            waiting = loop.run_until_complete(holder.fetchval(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND objid = 722 AND NOT granted"
            ))
            if waiting == len(commands):
                break
            time.sleep(0.05)
        loop.run_until_complete(holder.execute("SELECT pg_advisory_unlock(722)"))
        outputs = []
        for proc in procs:
            out, err = proc.communicate(timeout=60)
            assert proc.returncode == 0, err
            outputs.append(out.strip())
        return outputs
    finally:
        loop.run_until_complete(holder.close())
        loop.close()


def test_two_processes_racing_final_commits_publish_one_turn(runtime):
    grant = session(make_user("runs-race@cit.edu"))
    for n in range(3):
        store, row, claim = _admit_and_claim(runtime, grant, f"request-race-{n}")
        outputs = _race(runtime, [["commit", str(row["id"]), str(claim.fence), "A"],
                                  ["commit", str(row["id"]), str(claim.fence), "B"]])
        assert outputs == ["completed", "completed"]
        reopened = run(store.reopen(grant, row["conversation_id"]))
        assert reopened["revision"] == 1
        assert len(reopened["turns"]) == 1 and reopened["turns"][0]["answer"] in ("A", "B")
        status = run(store.status(grant, row["id"]))
        assert [e["name"] for e in status["events"]].count("completed") == 1


def test_stop_racing_a_final_commit_has_one_outcome(runtime):
    grant = session(make_user("runs-race-stop@cit.edu"))
    for n in range(4):
        store, row, claim = _admit_and_claim(runtime, grant, f"request-rstop-{n}")
        commit, stop = _race(runtime, [["commit", str(row["id"]), str(claim.fence), "A"],
                                       ["stop", str(row["id"]), grant]])
        status = run(store.status(grant, row["id"]))
        turns = run(store.reopen(grant, row["conversation_id"]))["turns"]
        if status["state"] == "completed":
            assert commit == "completed" and stop == "completed" and len(turns) == 1
        else:
            assert status["state"] == "cancelled" and commit == "cancelled" and stop == "cancelled"
            assert turns == []
        names = [e["name"] for e in status["events"]]
        assert names.count("completed") + names.count("cancelled") == 1


def test_a_superseded_lease_cannot_publish(runtime):
    grant = session(make_user("runs-fence@cit.edu"))
    store, row, first = _admit_and_claim(runtime, grant, "request-fence")
    with connection.cursor() as cursor:
        cursor.execute("UPDATE iris_ai.ask_run SET lease_expires_at = now() WHERE id = %s", [row["id"]])
    second = run(store.claim(row["id"], worker="w2", lease_seconds=30, executor="x", reserved_units=5))
    assert second.fence == first.fence + 1
    with pytest.raises(Fenced):
        run(store.commit_final(row["id"], first.fence, Result(answer="stale")))
    assert run(store.commit_final(row["id"], second.fence, Result(answer="current"))) == "completed"
    # The attempt cap is the original allowance's; a third claim is refused.
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*), sum(reserved_units) FROM iris_ai.attempt_accounting WHERE run_id = %s",
                       [row["id"]])
        assert cursor.fetchone() == (2, 10)


def test_attempts_beyond_the_allowance_end_the_run(runtime):
    grant = session(make_user("runs-attempts@cit.edu"))
    store, row, _ = _admit_and_claim(runtime, grant, "request-attempts")
    for _ in range(2):
        with connection.cursor() as cursor:
            cursor.execute("UPDATE iris_ai.ask_run SET lease_expires_at = now() WHERE id = %s", [row["id"]])
        run(store.claim(row["id"], worker="w", lease_seconds=30, executor="x", reserved_units=1))
    status = run(store.status(grant, row["id"]))
    assert status["state"] == "failed" and status["end_reason"] == "attempts_exhausted"


# --- Deletion ----------------------------------------------------------------

def test_deleting_a_conversation_fences_it_and_keeps_only_accounting(api, runtime):
    client, _ = api
    grant = session(make_user("runs-delete@cit.edu"))
    done = submit(client, grant, "request-del-1").json()
    conversation = done["conversation_id"]
    store = RunStore(runtime)
    row, _ = run(store.admit(grant, key="request-del-2", question="secret follow-up",
                             conversation_id=uuid.UUID(conversation), base_revision=1,
                             deadline_seconds=60, allowance=LIMITS.allowance(), pinned={}))
    claim = run(store.claim(row["id"], worker="w", lease_seconds=30, executor="x", reserved_units=9))

    assert client.delete(f"/api/v1/ai/conversations/{conversation}", headers=as_reader(grant)).status_code == 204
    assert client.get(f"/api/v1/ai/conversations/{conversation}", headers=as_reader(grant)).status_code == 404
    assert client.get(f"/api/v1/ai/runs/{done['id']}", headers=as_reader(grant)).status_code == 404
    assert run(store.commit_final(row["id"], claim.fence, Result(answer="too late"))) == "deleted"
    follow = submit(client, grant, "request-del-3", conversation_id=conversation, base_revision=1)
    assert follow.status_code == 404
    assert submit(client, grant, "request-del-1").status_code == 404

    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM iris_ai.turn WHERE conversation_id = %s", [conversation])
        assert cursor.fetchone()[0] == 0
        cursor.execute("""SELECT count(*) FROM iris_ai.run_event e JOIN iris_ai.ask_run r ON r.id = e.run_id
                           WHERE r.conversation_id = %s""", [conversation])
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT question, request_hash, state FROM iris_ai.ask_run"
                       " WHERE conversation_id = %s ORDER BY created_at", [conversation])
        assert cursor.fetchall() == [(None, "", "completed"), (None, "", "deleted")]
        cursor.execute("SELECT reserved_units, outcome FROM iris_ai.attempt_accounting WHERE run_id = %s",
                       [row["id"]])
        assert cursor.fetchall() == [(9, "deleted")]


def test_a_departed_account_is_fenced_then_purged(runtime):
    reader = make_user("runs-departed@cit.edu")
    grant = session(reader)
    store, row, claim = _admit_and_claim(runtime, grant, "request-departed")
    reader.is_active = False
    reader.save(update_fields=["is_active"])
    # Deactivation: no new access, no publication; content kept.
    assert run(store.commit_final(row["id"], claim.fence, Result(answer="x"))) == "cancelled"
    assert run(store.purge_departed()) == 0
    reader.delete()
    assert run(store.purge_departed()) == 1
    with connection.cursor() as cursor:
        cursor.execute("SELECT deleted_at IS NOT NULL, (SELECT question FROM iris_ai.ask_run WHERE id = %s)"
                       " FROM iris_ai.conversation WHERE id = %s", [row["id"], row["conversation_id"]])
        assert cursor.fetchone() == (True, None)
        cursor.execute("SELECT count(*) FROM iris_ai.attempt_accounting WHERE run_id = %s", [row["id"]])
        assert cursor.fetchone()[0] == 1


# --- One writer, one migration owner -----------------------------------------

def test_only_the_ai_runtime_writes_iris_ai_and_neither_runtime_owns_it(runtime):
    with connection.cursor() as cursor:
        cursor.execute("""SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                           JOIN pg_roles r ON r.oid = c.relowner
                          WHERE n.nspname = 'iris_ai' AND r.rolname IN ('iris_ai_runtime', 'iris_django_runtime')""")
        assert cursor.fetchall() == []
        cursor.execute("SELECT has_table_privilege('iris_ai_runtime', 'iris_ai.ask_run', 'INSERT')")
        assert cursor.fetchone()[0] is True
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            cursor.execute("SELECT has_table_privilege('iris_django_runtime', 'iris_ai.ask_run', %s)", [privilege])
            assert cursor.fetchone()[0] is False
        cursor.execute("SELECT has_table_privilege('iris_ai_runtime', 'iris_ai.attempt_accounting', 'DELETE')")
        assert cursor.fetchone()[0] is False
        cursor.execute("SELECT has_table_privilege('iris_ai_runtime', 'iris_authz.grant_key', 'SELECT')")
        assert cursor.fetchone()[0] is False

    async def ddl():
        conn = await asyncpg.connect(runtime)
        try:
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await conn.execute("CREATE TABLE iris_ai.intruder (id int)")
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await conn.execute("DELETE FROM iris_ai.attempt_accounting")
        finally:
            await conn.close()

    run(ddl())
    with pytest.raises(RefusedLogin):
        run(migrate(runtime))
    # Re-running applies nothing and keeps the grants.
    assert run(migrate(admin_dsn())) == []
