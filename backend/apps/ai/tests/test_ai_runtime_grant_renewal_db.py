"""A running investigation keeps reading while its reader keeps a grant (IR-880, ADR-049 §6, §9).

Real PostgreSQL under the restricted `iris_ai_runtime` login. The grants are
Django-signed `reader_session` grants with a few seconds of real lifetime,
verified inside PostgreSQL against its clock, so a lapse is a real lapse. A
reconnect is `RunStore.status` with a fresh grant, as the reader's poll makes it.
"""

import asyncio
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote, urlparse

import asyncpg
import pytest
from django.db import connection

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.admission import errors  # noqa: E402
from ai.admission.errors import AdmissionDenied  # noqa: E402
from ai.admission.guard import SendGuard  # noqa: E402
from ai.admission.scope import RunBinding  # noqa: E402
from ai.research.tools import ResearchTools  # noqa: E402
from ai.runs import config as runs_config  # noqa: E402
from ai.runs.executor import Result, Unavailable  # noqa: E402
from ai.runs.service import RunService  # noqa: E402
from ai.runs.store import NotFound, RunStore  # noqa: E402
from apps.ai.grants import config as grant_config, issue  # noqa: E402
from . import test_ai_runtime_runs_db as runs_db  # noqa: E402
from .corpus import make_user  # noqa: E402
from .test_ai_runtime_research_db import FLOOD, paper  # noqa: E402
from .test_ai_runtime_runs_db import DISPATCH, LIMITS, run  # noqa: E402

runtime = runs_db.runtime

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

#: A short lease, so a run can be claimed on a grant that lives a few seconds.
QUICK = replace(LIMITS, lease_seconds=1)
LIFETIME = 4


def short_grant(user, record_id=None, seconds=LIFETIME):
    """A genuine reader_session grant that lapses `seconds` from now."""
    cfg = grant_config.read()
    now = int(time.time())
    return issue._sign(cfg, issue._claims(
        cfg, issue.READER_SESSION, now=now, exp=now + seconds,
        sub=user.pk, gen=user.credential_version, rec=record_id,
    ))


def fresh(user, record_id=None):
    """A full-lifetime reader_session grant token, as a reconnecting reader presents."""
    return issue.reader_session_grant(user, record_id).token


class Quiet:
    """No wakeup: the test claims the committed run itself."""

    async def notify(self):
        pass

    async def wait(self, timeout):
        await asyncio.sleep(timeout)


def quick_service(dsn, executor):
    cfg = runs_config.RunsConfig(database_url=dsn, executor="deterministic",
                                 limits=QUICK, dispatch=DISPATCH)
    return RunService(RunStore(dsn), cfg, executor, Quiet())


async def past(grant, extra=0.6):
    """Wait until the grant has really lapsed."""
    await asyncio.sleep(max(0.0, grant.claims["exp"] + extra - time.time()))


class Investigation:
    """An executor that reads, lets time pass (and perhaps a reconnect), then reads again."""

    name = "investigation"
    version = "1"
    reserved_units = 0

    def __init__(self, grant, dsn, *, between=None):
        self.grant, self.dsn, self.between = grant, dsn, between
        self.seen = []
        self.connections_while_idle = None
        self.run_id = None

    async def _idle_connections(self):
        conn = await asyncpg.connect(runs_db.admin_dsn())
        try:
            # Every connection of the runtime login, whatever it calls itself (the send
            # guard names none).
            return await conn.fetchval(
                "SELECT count(*) FROM pg_stat_activity WHERE usename = $1",
                unquote(urlparse(self.dsn).username))
        finally:
            await conn.close()

    async def answer(self, question, tools):
        self.run_id = tools.run_id
        self.seen.append(await tools.search("flooding"))
        if self.between:
            await self.between(tools)
        await past(self.grant)
        # The model is "thinking": no connection of the runtime is open.
        self.connections_while_idle = await self._idle_connections()
        self.seen.append(await tools.search("flooding"))
        for result in self.seen:
            if result.status != "ok":
                raise Unavailable(result.reason)
        return Result(answer="Finished.")


def ask(runtime, user, executor, grant, key):
    """Submit on `grant`, let a worker run it, and read the outcome as the reconnected reader."""
    svc = quick_service(runtime, executor)
    queued, _ = run(svc.submit(grant.token, key=key, question="Which model predicts flooding?",
                               conversation_id=None, base_revision=None))
    assert run(svc.run_next()) is True
    # Read as the operator would: the reader may have lost access by now.
    state, end_reason = stored(queued["id"])[:2]
    return {"state": state, "end_reason": end_reason}


def stored(run_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT state, end_reason, reader_grant, grant_expires_at FROM iris_ai.ask_run"
                       " WHERE id = %s", [run_id])
        return cursor.fetchone()


def reconnect_with(runtime, grant):
    async def between(tools):
        await RunStore(runtime).status(grant, tools.run_id)

    return between


# --- AC1, AC4, AC5: a reconnect reaches the run already in progress --------------

def test_a_reconnect_mid_run_lets_a_long_investigation_finish_past_its_first_grant(runtime):
    user = make_user("renew-finish@cit.edu")
    paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    first = short_grant(user)
    executor = Investigation(first, runtime, between=reconnect_with(runtime, fresh(user)))
    done = ask(runtime, user, executor, first, "request-renew-finish")
    assert done["state"] == "completed"
    assert [r.status for r in executor.seen] == ["ok", "ok"]
    # No connection of the runtime was open while the model would have been thinking (AC4).
    assert executor.connections_while_idle == 0


def test_without_a_reconnect_the_same_investigation_ends_unauthorized(runtime):
    user = make_user("renew-lapse@cit.edu")
    paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    first = short_grant(user)
    executor = Investigation(first, runtime)
    ended = ask(runtime, user, executor, first, "request-renew-lapse")
    assert [r.status for r in executor.seen] == ["ok", "unavailable"]
    assert executor.seen[1].reason == "unauthorized"
    assert ended["state"] == "failed" and ended["end_reason"] == "unavailable"


# --- AC3: a reader who stops reconnecting, or loses access, still ends it ---------

def test_a_lapsed_grant_is_refused_at_provider_admission_too(runtime):
    user = make_user("renew-admission@cit.edu")
    first = short_grant(user)
    seen = {}

    async def between(tools):
        binding = RunBinding(tools.run_id, tools.fence)
        pin = SimpleNamespace(data_policy="no-training")
        await SendGuard(runtime).check(binding, pin)  # still granted
        await past(first)
        try:
            await SendGuard(runtime).check(binding, pin)
        except AdmissionDenied as denied:
            seen["code"] = denied.reason

    executor = Investigation(first, runtime, between=between)
    ask(runtime, user, executor, first, "request-renew-admission")
    assert seen["code"] == errors.ACCESS_REVOKED


def test_a_renewed_run_ends_at_the_next_read_and_admission_once_the_reader_loses_access(runtime):
    user = make_user("renew-revoked@cit.edu")
    paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    first = short_grant(user)
    seen = {}

    async def between(tools):
        await RunStore(runtime).status(fresh(user), tools.run_id)
        await past(first)
        seen["before"] = await tools.search("flooding")
        # The account is deactivated while the renewed grant is still unexpired.
        await asyncio.to_thread(_deactivate, user.pk)
        seen["after"] = await tools.search("flooding")
        try:
            await SendGuard(runtime).check(RunBinding(tools.run_id, tools.fence),
                                           SimpleNamespace(data_policy="no-training"))
        except AdmissionDenied as denied:
            seen["admission"] = denied.reason

    ask(runtime, user, Investigation(first, runtime, between=between), first, "request-renew-revoked")
    assert seen["before"].status == "ok"
    assert (seen["after"].status, seen["after"].reason) == ("unavailable", "unauthorized")
    assert seen["admission"] == errors.ACCESS_REVOKED


def _deactivate(user_id):
    # Runs in a worker thread, which has its own Django connection to close.
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE accounts_user SET is_active = false WHERE id = %s", [user_id])
    finally:
        connection.close()


def test_a_stop_after_a_renewal_still_ends_the_run_at_the_next_read(runtime):
    user = make_user("renew-stop@cit.edu")
    paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    first = short_grant(user)
    seen = {}

    async def between(tools):
        token = fresh(user)
        store = RunStore(runtime)
        await store.status(token, tools.run_id)
        await store.cancel(token, tools.run_id)
        seen["after"] = await tools.search("flooding")

    ask(runtime, user, Investigation(first, runtime, between=between), first, "request-renew-stop")
    assert (seen["after"].status, seen["after"].reason) == ("unavailable", "run_ended")


# --- AC2: a renewal never widens what the run reads -------------------------------

def _begin(runtime, user, key, record_id=None):
    """A queued then claimed run on a short grant, without the executor."""
    first = short_grant(user, record_id)
    store = RunStore(runtime)
    row, _ = run(store.admit(first.token, key=key, question="q", conversation_id=None, base_revision=None,
                             deadline_seconds=60, allowance=QUICK.allowance(), pinned={}))
    claim = run(store.claim(row["id"], worker="w", lease_seconds=1, executor="x", reserved_units=0))
    return store, row, claim, first


def test_only_a_grant_of_exactly_the_conversations_scope_renews_a_running_run(runtime):
    user, other = make_user("renew-scope@cit.edu"), make_user("renew-scope-other@cit.edu")
    store, row, claim, first = _begin(runtime, user, "request-scope-1", record_id=41)
    original = stored(row["id"])
    # An unscoped grant of the same reader may look at the run, and is wider than it:
    # it is not stored as the run's authority (IR-723).
    run(store.status(fresh(user), row["id"]))
    assert stored(row["id"]) == original
    # Another Paper Chat scope cannot even see the run.
    with pytest.raises(NotFound):
        run(store.status(fresh(user, 42), row["id"]))
    assert stored(row["id"]) == original
    # Nor does another reader's grant, which cannot even see the run.
    with pytest.raises(NotFound):
        run(store.status(fresh(other, 41), row["id"]))
    assert stored(row["id"]) == original
    # The exact scope renews.
    renewed = fresh(user, 41)
    run(store.status(renewed, row["id"]))
    assert stored(row["id"])[2] == renewed != original[2]


def test_an_unscoped_run_is_not_renewed_by_a_paper_chat_grant(runtime):
    user = make_user("renew-unscoped@cit.edu")
    store, row, claim, first = _begin(runtime, user, "request-scope-2")
    original = stored(row["id"])
    with pytest.raises(NotFound):
        run(store.status(fresh(user, 41), row["id"]))
    assert stored(row["id"]) == original


def test_the_tools_themselves_refuse_a_stored_grant_of_another_reader_or_scope(runtime):
    user, other = make_user("renew-tools@cit.edu"), make_user("renew-tools-other@cit.edu")
    paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    store, row, claim, first = _begin(runtime, user, "request-scope-3")
    tools = ResearchTools(runtime, claim.grant, row["id"], claim.fence, claim.scope_record_id,
                          follow_stored_grant=True)
    assert run(tools.search("flooding")).status == "ok"

    def store_grant(grant):
        with connection.cursor() as cursor:
            cursor.execute("UPDATE iris_ai.ask_run SET reader_grant = %s WHERE id = %s",
                           [grant, row["id"]])

    # Even if a wrong grant were somehow stored, the run reads nothing under it.
    store_grant(fresh(other))
    refused = run(tools.search("flooding"))
    assert (refused.status, refused.reason) == ("unavailable", "run_ended")
    store_grant(fresh(user, 41))
    refused = run(tools.search("flooding"))
    assert (refused.status, refused.reason) == ("unavailable", "unauthorized")
    store_grant(fresh(user))
    assert run(tools.search("flooding")).status == "ok"


def test_a_tool_that_does_not_follow_the_stored_grant_keeps_reading_under_its_own(runtime):
    """The default is unchanged: an explicit grant is the one that is checked."""
    user, other = make_user("renew-default@cit.edu"), make_user("renew-default-other@cit.edu")
    store, row, claim, first = _begin(runtime, user, "request-scope-4")
    intruder = ResearchTools(runtime, fresh(other), row["id"], claim.fence)
    assert run(intruder.search("flooding")).reason == "run_ended"


def test_a_run_with_no_stored_grant_reads_nothing(runtime):
    user = make_user("renew-none@cit.edu")
    store, row, claim, first = _begin(runtime, user, "request-scope-5")
    with connection.cursor() as cursor:
        cursor.execute("UPDATE iris_ai.ask_run SET reader_grant = NULL WHERE id = %s", [row["id"]])
    tools = ResearchTools(runtime, claim.grant, row["id"], claim.fence, claim.scope_record_id,
                          follow_stored_grant=True)
    refused = run(tools.search("flooding"))
    assert (refused.status, refused.reason) == ("unavailable", "unauthorized")


def test_a_fenced_run_is_ended_not_unauthorized_even_with_a_valid_stored_grant(runtime):
    user = make_user("renew-fence@cit.edu")
    store, row, claim, first = _begin(runtime, user, "request-scope-6")
    tools = ResearchTools(runtime, claim.grant, row["id"], claim.fence + 1, claim.scope_record_id,
                          follow_stored_grant=True)
    assert run(tools.search("flooding")).reason == "run_ended"
