"""A replacement worker resumes an interrupted investigation, on real PostgreSQL (IR-724, ADR-049 §12, §14).

The first worker is an independent process (`ai.tests.agent_worker`) built
from settings, killed outright at one point of a step; its replacement is
built the same way in-process, so its requests can be read. Restricted
runtime login and Django-issued grants throughout.

IR-725's guard withholds every request carrying a tool result from a paid
provider, so an admitted run never sends after a completed step. Resuming
and continuing to an answer is therefore proven unadmitted (`unadmitted`);
the real ledger and guard prove what a takeover keeps at the step-1 kill
point, and that an admitted run resumed today is withheld at its next
request. The recording vendor proves the contract, never paid capacity;
every bound and limit here is a test value.
"""

import asyncio
import json
import subprocess
import sys
import uuid
from dataclasses import replace
from types import SimpleNamespace
from urllib.parse import unquote, urlparse

import asyncpg
import pytest
from django.db import connection

from . import test_ai_runtime_runs_db as runs_db
from .corpus import make_user
from .test_ai_runtime_admission_db import limits as admission_limits, request as admission_request
from .test_ai_runtime_executor_selection_db import (
    LIMITS, Vendor, accounted, ended, queue, values, worker,
)
from .test_ai_runtime_research_db import paper, write_source
from .test_ai_runtime_runs_db import REPO, admin_dsn, run, session
from ai.admission import errors  # noqa: E402
from ai.admission.errors import AdmissionDenied  # noqa: E402
from ai.admission.ledger import Ledger  # noqa: E402
from ai.admission.scope import RunBinding, run_key  # noqa: E402
from ai.runs.executor import Result  # noqa: E402
from ai.runs.store import Fenced, RunStore  # noqa: E402
from ai.tests.agent_worker import KILLED, unadmitted  # noqa: E402
from apps.ai.models.admission import ProviderReservation  # noqa: E402
from apps.records.models import Record  # noqa: E402

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

runtime = runs_db.runtime

FLOOD = "rainfall gauges and river water levels trained a network to forecast floods"
POND = "brackish water ponds were sampled weekly for tilapia growth"
# Each physical attempt is counted against the run's allowance over every fence.
ROOMY = replace(LIMITS, max_attempts=6)


def call(id_, name, **arguments):
    return {"id": id_, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def tools(*calls):
    return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": list(calls)},
                         "finish_reason": "tool_calls"}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 5}}


def reply(content):
    return {"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 60, "completion_tokens": 20}}


STEP_1 = tools(call("s1", "search", query="rainfall"))
STEP_2 = tools(call("s2", "search", query="tilapia"))


def doomed(dsn, die, *, limits=ROOMY, admitted=False):
    """The first worker: two search steps, killed at `die`, never answering."""
    spec = json.dumps({"values": values(dsn, limits=limits), "responses": [STEP_1, STEP_2, "Never sent."],
                       "idle_seconds": 30, "die": die, "admitted": admitted})
    proc = subprocess.Popen([sys.executable, "-m", "ai.tests.agent_worker", dsn, spec],
                            cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _, err = proc.communicate(timeout=120)
    assert proc.returncode == KILLED, err


def replacement(dsn, vendor, *, limits=ROOMY):
    """The worker that takes the run over, sending without admission."""
    return unadmitted(SimpleNamespace(**values(dsn, limits=limits)), vendor)


def lease_lapses(run_id):
    """The dead worker's lease runs out (its length is a test value, not waited for)."""
    with connection.cursor() as cursor:
        cursor.execute("UPDATE iris_ai.ask_run SET lease_expires_at = now() WHERE id = %s", [run_id])


def events(run_id, name):
    with connection.cursor() as cursor:
        cursor.execute("SELECT data FROM iris_ai.run_event WHERE run_id = %s AND name = %s ORDER BY sequence",
                       [run_id, name])
        return [json.loads(row[0]) if isinstance(row[0], str) else row[0] for row in cursor.fetchall()]


def checkpoints(run_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT step FROM iris_ai.run_checkpoint WHERE run_id = %s", [run_id])
        return [row[0] for row in cursor.fetchall()]


def turns(conversation_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM iris_ai.turn WHERE conversation_id = %s", [conversation_id])
        return cursor.fetchone()[0]


def reservations(run_id):
    return list(ProviderReservation.objects.filter(run_key=run_key(run_id)).order_by("id"))


def tool_messages(payload):
    return {m["tool_call_id"]: json.loads(m["content"]) for m in payload["messages"] if m["role"] == "tool"}


def call_ids(payload):
    return [c["id"] for m in payload["messages"] if m["role"] == "assistant" for c in m.get("tool_calls") or ()]


class Watching(Vendor):
    """The replacement's vendor, counting the runtime login's open connections at each inference."""

    def __init__(self, dsn, *responses):
        super().__init__(*responses)
        self.login = unquote(urlparse(dsn).username)
        self.open_connections = []

    async def converse(self, request):
        conn = await asyncpg.connect(admin_dsn())
        try:
            self.open_connections.append(await conn.fetchval(
                "SELECT count(*) FROM pg_stat_activity WHERE usename = $1", self.login))
        finally:
            await conn.close()
        return await super().converse(request)


def resumed(payload):
    # The completed first step comes back whole, with its own call id; the second does not.
    assert call_ids(payload) == ["s1"], call_ids(payload)
    assert "Flood forecasting" in json.dumps(tool_messages(payload)["s1"])
    return tools(call("s2", "search", query="tilapia"))


def answered(payload):
    flood = tool_messages(payload)["s1"]
    passage = flood["passages"][0]["passage"]
    return reply(f"«Flood forecasting» forecasts floods from rainfall gauges [{passage}].")


DIE_POINTS = {
    # Its second model turn came back; nothing after it ran or was settled.
    "after_a_provider_response": {"at": "response", "after": 2},
    # Its second tool result was journalled; that step was never saved.
    "after_a_tool_result": {"at": "tool", "after": 2},
    "before_a_checkpoint_commit": {"at": "before_checkpoint", "after": 2},
    "after_a_checkpoint_commit": {"at": "after_checkpoint", "after": 1},
}


@pytest.mark.parametrize("die", DIE_POINTS.values(), ids=list(DIE_POINTS))
def test_a_replacement_worker_resumes_the_completed_step_with_one_final_answer(runtime, die):
    paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    paper("Pond sampling", {2: [("Methods", POND)]})
    grant = session(make_user(f"recover-{die['at']}@cit.edu"))
    queued = queue(worker(runtime, limits=ROOMY), grant, f"recover-{die['at']}")

    doomed(runtime, die)
    assert checkpoints(queued["id"]) == [1]
    dead_models = [m["step"] for m in events(queued["id"], "model")]
    lease_lapses(queued["id"])

    vendor = Watching(runtime, resumed, answered)
    assert run(replacement(runtime, vendor).run_next())

    state, reason, turn_id = ended(queued["id"])
    assert (state, reason) == ("completed", "answered") and turn_id is not None
    assert turns(queued["conversation_id"]) == 1
    status = run(RunStore(runtime).status(grant, queued["id"]))
    # The run keeps what it was admitted with: deadline, allowance and pin.
    assert (status["deadline_at"], status["allowance"], status["pinned"]) == (
        queued["deadline_at"], queued["allowance"], queued["pinned"])

    # Restored from step 1 and continued: steps are not renewed.
    assert events(queued["id"], "recovery") == [{"outcome": "resumed", "step": 1}]
    assert [m["step"] for m in events(queued["id"], "model")] == [*dead_models, 2, 3]
    assert len(vendor.requests) == 2
    # No live database connection across any inference.
    assert vendor.open_connections == [0, 0]

    # Two claims, each accounted to the AGENT.
    assert accounted(queued["id"]) == ["agent", "agent"]
    # A finished run keeps no checkpoint.
    assert checkpoints(queued["id"]) == []


def test_a_takeover_does_not_renew_the_runs_allowance(runtime):
    """On the real ledger, at the one kill point an admitted run reaches: its first response."""
    paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    tight = replace(LIMITS, max_attempts=2)
    grant = session(make_user("recover-allowance@cit.edu"))
    queued = queue(worker(runtime, limits=tight), grant, "recover-allowance")

    # One attempt spent, its outcome never learned and nothing saved.
    doomed(runtime, {"at": "response", "after": 1}, limits=tight, admitted=True)
    assert checkpoints(queued["id"]) == []
    lease_lapses(queued["id"])

    vendor = Vendor(STEP_1, "Never sent.")
    assert run(worker(runtime, vendor, limits=tight).run_next())
    # The second attempt is the allowance's last; a third is refused before it is reserved.
    assert len(vendor.requests) == 1
    assert ended(queued["id"]) == ("failed", "unavailable", None)
    assert turns(queued["conversation_id"]) == 0
    held = reservations(queued["id"])
    assert len(held) == 2
    assert "released" not in {r.state for r in held}
    # The attempt whose outcome the dead worker never learned keeps its reservation.
    assert (held[0].state, held[0].charge_attempts) == ("open", 1)


def resumed_whole(payload):
    # IR-996: the restored step reaches the model whole; nothing is checked at send time.
    assert call_ids(payload) == ["s1"], call_ids(payload)
    assert "Flood forecasting" in json.dumps(tool_messages(payload)["s1"])
    return reply("The flood paper answers this.")


def test_an_admitted_run_resumed_today_sends_its_restored_step_whole(runtime):
    paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    grant = session(make_user("recover-withheld@cit.edu"))
    queued = queue(worker(runtime, limits=ROOMY), grant, "recover-withheld")

    doomed(runtime, {"at": "after_checkpoint", "after": 1}, admitted=True)
    assert checkpoints(queued["id"]) == [1]
    dead = [r.id for r in reservations(queued["id"])]
    lease_lapses(queued["id"])

    vendor = Vendor(resumed_whole)
    assert run(worker(runtime, vendor, limits=ROOMY).run_next())
    assert events(queued["id"], "recovery") == [{"outcome": "resumed", "step": 1}]
    assert len(vendor.requests) == 1
    assert ended(queued["id"])[:2] == ("completed", "answered")
    assert turns(queued["conversation_id"]) == 1
    # The dead worker's attempt stays charged; the resumed one was reserved and sent.
    held = reservations(queued["id"])
    assert [r.id for r in held[:len(dead)]] == dead
    assert held[0].charge_attempts == 1
    assert [r.sent for r in held[len(dead):]] == [True]


def test_recovered_evidence_whose_source_changed_is_rebuilt_from_the_question(runtime):
    flood = paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    paper("Pond sampling", {2: [("Methods", POND)]})
    grant = session(make_user("recover-stale@cit.edu"))
    queued = queue(worker(runtime, limits=ROOMY), grant, "recover-stale")

    doomed(runtime, {"at": "after_checkpoint", "after": 1})
    revised = "a revised methods section: rainfall gauges forecast floods"
    write_source(flood, {4: [("Methods", revised)]}, "2")
    lease_lapses(queued["id"])

    def fresh(payload):
        # Nothing recovered reaches the model: no call group, no result, no old passage.
        assert call_ids(payload) == [] and FLOOD not in json.dumps(payload)
        return tools(call("again", "search", query="rainfall"))

    def cite_fresh(payload):
        found = tool_messages(payload)["again"]
        assert found["passages"][0]["text"] == revised
        return reply(f"«Flood forecasting» forecasts floods from rainfall gauges [{found['passages'][0]['passage']}].")

    vendor = Vendor(fresh, cite_fresh)
    assert run(replacement(runtime, vendor).run_next())

    assert ended(queued["id"])[:2] == ("completed", "answered")
    assert events(queued["id"], "recovery") == [{"outcome": "rebuilt", "reason": "stale", "step": 1}]
    # The step the dead worker took stays taken.
    assert [m["step"] for m in events(queued["id"], "model")] == [1, 2, 3]

    # What the rebuild discarded no longer backs the answer: it reopens whole,
    # though the dead worker's read of the replaced source stays in the journal.
    store = RunStore(runtime)
    reopened = run(store.reopen(grant, queued["conversation_id"]))
    [turn] = reopened["turns"]
    assert [c["quote"] for c in turn["citations"]] == [revised]
    assert run(store.status(grant, queued["id"], reader_projection=True))["sources_available"] is True

    # A source the rebuilt answer did read still fences it when it changes.
    write_source(flood, {4: [("Methods", "revised again")]}, "3")
    [turn] = run(store.reopen(grant, queued["conversation_id"]))["turns"]
    assert turn["citations"] == []
    assert run(store.status(grant, queued["id"], reader_projection=True))["sources_available"] is False


def test_recovered_evidence_the_reader_can_no_longer_read_is_never_resent(runtime):
    flood = paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    grant = session(make_user("recover-revoked@cit.edu"))
    queued = queue(worker(runtime, limits=ROOMY), grant, "recover-revoked")

    doomed(runtime, {"at": "after_checkpoint", "after": 1})
    Record.objects.filter(pk=flood.pk).update(is_deleted=True)
    lease_lapses(queued["id"])

    def fresh(payload):
        assert call_ids(payload) == [] and FLOOD not in json.dumps(payload)
        return reply("I could not find a readable paper on that.")

    vendor = Vendor(fresh)
    assert run(replacement(runtime, vendor).run_next())
    assert events(queued["id"], "recovery") == [{"outcome": "rebuilt", "reason": "stale", "step": 1}]
    assert len(vendor.requests) == 1


def test_a_delayed_worker_that_lost_its_lease_can_neither_admit_save_nor_commit(runtime):
    grant = session(make_user("recover-fenced@cit.edu"))
    queued = queue(worker(runtime, limits=ROOMY), grant, "recover-fenced")
    store = RunStore(runtime)
    run_id = uuid.UUID(queued["id"])

    def claim(name):
        return run(store.claim(run_id, worker=name, lease_seconds=30, executor=None,
                               reserved_units={"agent": 0}))

    old = claim("old")
    run(store.save_checkpoint(run_id, old.fence, 1, {"format": "old"}, lease_seconds=30))
    # Still leased: nobody else may take it.
    assert claim("early") is None
    lease_lapses(queued["id"])
    new = claim("new")
    assert new.fence > old.fence
    assert new.checkpoint == {"step": 1, "body": {"format": "old"}}

    with pytest.raises(Fenced):
        run(store.save_checkpoint(run_id, old.fence, 2, {"format": "late"}, lease_seconds=30))
    with pytest.raises(AdmissionDenied) as denied:
        run(Ledger(runtime, admission_limits()).admit(admission_request(), RunBinding(run_id, old.fence)))
    assert denied.value.reason == errors.RUN_CANCELLED
    with pytest.raises(Fenced):
        run(store.commit_final(run_id, old.fence, Result(answer="A late answer.")))
    assert checkpoints(queued["id"]) == [1]
    assert ProviderReservation.objects.filter(run_key=run_key(run_id)).count() == 0

    # The current holder is unaffected: its step saves and its answer commits once.
    run(store.save_checkpoint(run_id, new.fence, 2, {"format": "new"}, lease_seconds=30))
    assert run(store.commit_final(run_id, new.fence, Result(answer="On time."))) == "completed"
    assert turns(queued["conversation_id"]) == 1
    assert checkpoints(queued["id"]) == []


def test_two_replacements_racing_for_one_interrupted_run_answer_it_once(runtime):
    paper("Flood forecasting", {4: [("Methods", FLOOD)]})
    paper("Pond sampling", {2: [("Methods", POND)]})
    grant = session(make_user("recover-race@cit.edu"))
    queued = queue(worker(runtime, limits=ROOMY), grant, "recover-race")
    doomed(runtime, {"at": "after_checkpoint", "after": 1})
    lease_lapses(queued["id"])

    first = replacement(runtime, Vendor(resumed, answered))
    second = replacement(runtime, Vendor(resumed, answered))

    async def both():
        return await asyncio.gather(first.run_next(), second.run_next())

    assert sorted(run(both())) == [False, True]
    assert ended(queued["id"])[:2] == ("completed", "answered")
    assert turns(queued["conversation_id"]) == 1
