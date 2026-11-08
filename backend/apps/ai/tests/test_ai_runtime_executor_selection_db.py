"""Workers answer each run with the executor its pin names (IR-862, ADR-049).

Real PostgreSQL under the restricted runtime login, the real admission
ledger and guard, and services built by `ai.runs.worker.build` from
settings, as `python -m ai.runs.worker` builds them. The vendor is the
recording provider; it proves the contract, never paid capacity. Every
bound here is a test value, not a production one.
"""

import asyncio
import json
import subprocess
import sys
import time
from dataclasses import asdict, replace
from types import SimpleNamespace

import asyncpg
import pytest
from django.db import connection

from apps.ai.grants import issue
from apps.ai.models.admission import ProviderReservation

# Importing the run suite puts the repo root, and so `ai`, on the path.
from . import test_ai_runtime_runs_db as runs_db
from .corpus import make_user
from .test_ai_runtime_context_contract import MILLION
from .test_ai_runtime_runs_db import DISPATCH, REPO, admin_dsn, run, session
from ai.domain.ports import ProviderRejected  # noqa: E402
from ai.infrastructure.recording_adapter import HANG, RecordingAgentProvider  # noqa: E402
from ai.runs import config as runs_config  # noqa: E402
from ai.runs.store import RunStore  # noqa: E402
from ai.runs.worker import build  # noqa: E402

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

runtime = runs_db.runtime

ENDPOINT = "https://llm.example.test/v1"
MODEL = "model-a"
LIMITS = runs_config.RunLimits(
    deadline_seconds=120, deep_deadline_seconds=600, lease_seconds=30, max_attempts=3,
    max_input_tokens=1_000_000, max_output_tokens=50_000, max_cost_usd=0.5,
)
BOUNDS = dict(max_steps=4, max_tool_calls=6, max_no_progress=2, final_seconds=5, history_turns=4)
AGENT = dict(
    RUNS_AGENT_MODEL=MODEL,
    RUNS_AGENT_RESERVES=json.dumps(dict(output_tokens=60, reasoning_tokens=40, next_result_tokens=300,
                                        repair_tokens=100)),
    AGENT_LLM_ENDPOINT=ENDPOINT,
    AGENT_LLM_API_KEY="sk-test-never-sent",
    AGENT_LLM_MODELS=MODEL,
    AGENT_LLM_CAPABILITIES="tools",
    AGENT_LLM_DATA_POLICY="no-training",
    AGENT_LLM_CAPACITIES=json.dumps({MODEL: asdict(MILLION)}),
    AI_ADMISSION_CAMPAIGN="ir862-test",
    AI_ADMISSION_CAMPAIGN_MAX_ATTEMPTS="100",
    AI_ADMISSION_CAMPAIGN_MAX_INPUT_TOKENS="10000000",
    AI_ADMISSION_CAMPAIGN_MAX_OUTPUT_TOKENS="1000000",
    AI_ADMISSION_CAMPAIGN_MAX_COST_USD="100",
    AI_ADMISSION_CAMPAIGN_MAX_ACTIVE_MINUTES="600",
    AI_ADMISSION_RESERVE_FRACTION="0.1",
    AI_ADMISSION_LANE_CONCURRENCY=json.dumps({"research": 8}),
    AI_ADMISSION_ACCOUNT_CONCURRENCY="8",
    AI_ADMISSION_PRICES=json.dumps({MODEL: {"input": 1.0, "output": 2.0}}),
    AI_ADMISSION_MAX_OUTPUT_TOKENS="100",
    AI_ADMISSION_LEASE_GRACE_SECONDS="1",
)


def values(dsn, executor="agent", *, limits=LIMITS, dispatch=DISPATCH, bounds=None):
    """The worker's settings, as `ai.infrastructure.settings` would hold them."""
    bounds = bounds or {"ordinary": BOUNDS, "deep": BOUNDS}
    return {
        "RUNS_DATABASE_URL": dsn, "RUNS_EXECUTOR": executor, "RUNS_REDIS_URL": "",
        **{f"RUNS_{k.upper()}": v for k, v in asdict(limits).items()},
        **{f"RUNS_{k.upper()}": v for k, v in asdict(dispatch).items()},
        **AGENT, "RUNS_AGENT_BOUNDS": json.dumps(bounds),
    }


class Vendor(RecordingAgentProvider):
    """The recording provider standing in for the configured chat-completions adapter."""

    adapter = "openai-compatible"

    def __init__(self, *responses, after_first=None, delay=0.0):
        super().__init__(responses=list(responses), endpoint=ENDPOINT, models=(MODEL,),
                         capabilities=("tools",), capacities={MODEL: MILLION})
        #: Awaited once, after the first turn comes back: "between steps".
        self.after_first = after_first
        self.delay = delay

    async def converse(self, request):
        turn = await super().converse(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.after_first is not None:
            hook, self.after_first = self.after_first, None
            await hook()
        return turn


def worker(dsn, provider=None, executor="agent", **kw):
    return build(SimpleNamespace(**values(dsn, executor, **kw)), agent_provider=provider)


def reply(content):
    return {"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 60, "completion_tokens": 20}}


def tool_call():
    return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
        {"id": "s1", "type": "function", "function": {"name": "search", "arguments": '{"query": "water"}'}},
    ]}, "finish_reason": "tool_calls"}], "usage": {"prompt_tokens": 50, "completion_tokens": 5}}


def queue(svc, grant, key, question="What does IRIS keep?", depth="ordinary"):
    queued, created = run(svc.submit(grant, key=key, question=question, conversation_id=None,
                                     base_revision=None, depth=depth))
    assert created and queued["state"] == "queued"
    return queued


def ended(run_id):
    """As an operator: a revoked reader may no longer read their own run."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT state, end_reason, turn_id FROM iris_ai.ask_run WHERE id = %s", [run_id])
        return cursor.fetchone()


def accounted(run_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT executor FROM iris_ai.attempt_accounting WHERE run_id = %s ORDER BY id",
                       [run_id])
        return [row[0] for row in cursor.fetchall()]


async def as_admin(sql, *args):
    conn = await asyncpg.connect(admin_dsn())
    try:
        await conn.execute(sql, *args)
    finally:
        await conn.close()


# --- Per-run selection ---------------------------------------------------------

def test_each_run_is_answered_by_the_executor_its_pin_names(runtime):
    grant = session(make_user("select-both@cit.edu"))
    deterministic = queue(worker(runtime, executor="deterministic"), grant, "select-det", "Echo me?")
    agent = queue(worker(runtime), grant, "select-agent")
    assert (deterministic["pinned"]["executor"], agent["pinned"]["executor"]) == ("deterministic", "agent")

    vendor = Vendor(reply("IRIS keeps CIT-U research."))
    svc = worker(runtime, vendor)
    assert run(svc.run_next()) and run(svc.run_next())

    store = RunStore(runtime)
    by_echo = run(store.status(grant, deterministic["id"]))
    by_agent = run(store.status(grant, agent["id"]))
    assert by_echo["state"] == by_agent["state"] == "completed"
    assert len(vendor.requests) == 1
    assert vendor.requests[0]["model"] == MODEL
    assert vendor.requests[0]["messages"][-1] == {"role": "user", "content": "What does IRIS keep?"}
    assert (accounted(deterministic["id"]), accounted(agent["id"])) == (["deterministic"], ["agent"])


def test_an_upgraded_worker_leaves_a_run_pinned_to_another_model_for_a_worker_that_serves_it(runtime):
    grant = session(make_user("select-repinned@cit.edu"))
    queued = queue(worker(runtime), grant, "select-repinned")
    upgraded = {**AGENT, "RUNS_AGENT_MODEL": "model-b", "AGENT_LLM_MODELS": f"{MODEL},model-b",
                "AGENT_LLM_CAPACITIES": json.dumps({MODEL: asdict(MILLION), "model-b": asdict(MILLION)}),
                "AI_ADMISSION_PRICES": json.dumps({m: {"input": 1.0, "output": 2.0} for m in (MODEL, "model-b")})}
    other = Vendor(reply("The wrong interpretation."))
    other.models = frozenset((MODEL, "model-b"))
    svc = build(SimpleNamespace(**{**values(runtime), **upgraded}), agent_provider=other)
    # Never substituted: the run is not even claimed.
    assert run(svc.run_next()) is False
    assert run(RunStore(runtime).status(grant, queued["id"]))["state"] == "queued"

    vendor = Vendor(reply("Answered under its own pin."))
    assert run(worker(runtime, vendor).run_next())
    status = run(RunStore(runtime).status(grant, queued["id"]))
    assert status["state"] == "completed"
    assert status["pinned"]["agent"]["model"] == MODEL
    assert (other.requests, len(vendor.requests)) == ([], 1)
    assert accounted(queued["id"]) == ["agent"]


def test_a_deterministic_worker_leaves_an_agent_run_queued_in_a_mixed_fleet(runtime):
    grant = session(make_user("select-mixed@cit.edu"))
    agent = queue(worker(runtime), grant, "select-mixed-agent")
    echo = queue(worker(runtime, executor="deterministic"), grant, "select-mixed-echo", "Echo me?")
    deterministic = worker(runtime, executor="deterministic")
    assert run(deterministic.run_next()) and run(deterministic.run_next()) is False

    store = RunStore(runtime)
    assert run(store.status(grant, echo["id"]))["state"] == "completed"
    assert run(store.status(grant, agent["id"]))["state"] == "queued"
    assert accounted(agent["id"]) == []

    assert run(worker(runtime, Vendor(reply("Answered by an agent worker."))).run_next())
    assert run(store.status(grant, agent["id"]))["state"] == "completed"


# --- What the run was admitted with, the worker cannot widen ----------------------

def test_a_run_keeps_the_bounds_it_was_admitted_with(runtime):
    grant = session(make_user("select-bounds@cit.edu"))
    # Holding back more time than the run has closes research before the first turn.
    closed = {**BOUNDS, "final_seconds": LIMITS.deadline_seconds * 10}
    queued = queue(worker(runtime, bounds={"ordinary": closed, "deep": BOUNDS}), grant, "select-bounds")
    assert queued["pinned"]["bounds"]["final_seconds"] == closed["final_seconds"]

    vendor = Vendor(reply("A direct answer."))
    assert run(worker(runtime, vendor).run_next())

    assert run(RunStore(runtime).status(grant, queued["id"]))["state"] == "completed"
    # This worker's own bounds would have offered the tools; the run's closed them.
    assert vendor.requests[0]["tool_choice"] == "none"


def test_a_worker_with_a_larger_allowance_cannot_widen_the_runs(runtime):
    grant = session(make_user("select-allowance@cit.edu"))
    queued = queue(worker(runtime, limits=replace(LIMITS, max_input_tokens=50)), grant, "select-allowance")
    vendor = Vendor(reply("Never sent."))
    assert run(worker(runtime, vendor).run_next())

    status = run(RunStore(runtime).status(grant, queued["id"]))
    assert (status["state"], status["end_reason"]) == ("failed", "unavailable")
    assert status["allowance"]["max_input_tokens"] == 50
    assert vendor.requests == []


def test_a_reconnect_renews_the_grant_and_keeps_the_allowance(runtime):
    reader = make_user("select-renew@cit.edu")
    queued = queue(worker(runtime), issue.reader_session_grant(reader, 41).token, "select-renew")
    with connection.cursor() as cursor:
        cursor.execute("UPDATE iris_ai.ask_run SET grant_expires_at = now() - interval '1 second'"
                       " WHERE id = %s", [queued["id"]])
    vendor = Vendor(reply("Answered after the reader came back."))
    svc = worker(runtime, vendor, limits=replace(LIMITS, max_attempts=9, max_cost_usd=9.0))
    assert run(svc.run_next()) is False

    renewed = issue.reader_session_grant(reader, 41).token
    run(RunStore(runtime).status(renewed, queued["id"]))
    assert run(svc.run_next()) is True

    status = run(RunStore(runtime).status(renewed, queued["id"]))
    assert status["state"] == "completed"
    assert status["allowance"] == queued["allowance"] == LIMITS.allowance()
    assert accounted(queued["id"]) == ["agent"]


# --- Every stop ends in an existing public outcome --------------------------------

def test_cancel_between_tool_steps_ends_cancelled_with_no_further_attempt(runtime):
    grant = session(make_user("select-cancel@cit.edu"))
    queued = queue(worker(runtime), grant, "select-cancel")
    store = RunStore(runtime)
    vendor = Vendor(tool_call(), reply("Never sent."),
                    after_first=lambda: store.cancel(grant, queued["id"]))
    assert run(worker(runtime, vendor).run_next())

    assert ended(queued["id"]) == ("cancelled", "stopped", None)
    assert len(vendor.requests) == 1


def test_access_revoked_between_steps_ends_unavailable_and_sends_nothing_more(runtime):
    grant = session(make_user("select-revoked@cit.edu"))
    queued = queue(worker(runtime), grant, "select-revoked")
    vendor = Vendor(tool_call(), reply("Never sent."), after_first=lambda: as_admin(
        """UPDATE accounts_user SET is_active = false
            WHERE id = (SELECT reader_id FROM iris_ai.ask_run WHERE id = $1)""", queued["id"]))
    assert run(worker(runtime, vendor).run_next())

    assert ended(queued["id"]) == ("failed", "unavailable", None)
    assert len(vendor.requests) == 1


def test_the_deadline_ends_a_hung_attempt_with_no_turn(runtime):
    grant = session(make_user("select-deadline@cit.edu"))
    short = replace(LIMITS, deadline_seconds=3)
    queued = queue(worker(runtime, limits=short, bounds={"ordinary": {**BOUNDS, "final_seconds": 1},
                                                         "deep": BOUNDS}), grant, "select-deadline")
    vendor = Vendor(HANG)
    started = time.monotonic()
    assert run(worker(runtime, vendor).run_next())

    assert time.monotonic() - started < 30
    assert ended(queued["id"]) == ("failed", "unavailable", None)


def test_a_refused_provider_ends_unavailable(runtime):
    grant = session(make_user("select-refused@cit.edu"))
    queued = queue(worker(runtime), grant, "select-refused")
    vendor = Vendor(ProviderRejected("status 400"))
    assert run(worker(runtime, vendor).run_next())

    assert ended(queued["id"]) == ("failed", "unavailable", None)
    assert len(vendor.requests) == 1


def test_a_draft_that_fails_validation_is_not_delivered(runtime):
    grant = session(make_user("select-invalid@cit.edu"))
    queued = queue(worker(runtime), grant, "select-invalid")
    vendor = Vendor(reply("It forecast 912 floods [P00000000000000000009]."))
    assert run(worker(runtime, vendor).run_next())

    assert ended(queued["id"]) == ("failed", "unavailable", None)
    reopened = run(RunStore(runtime).reopen(grant, queued["conversation_id"]))
    assert reopened["turns"] == []


# --- Independent workers ------------------------------------------------------------

def spawn(dsn, *responses, delay=0.0, idle=2.0, limits=LIMITS, dispatch=DISPATCH):
    """`python -m ai.tests.agent_worker`: a worker process built from settings."""
    spec = json.dumps({"values": values(dsn, limits=limits, dispatch=dispatch),
                       "responses": list(responses), "delay": delay, "idle_seconds": idle})
    return subprocess.Popen([sys.executable, "-m", "ai.tests.agent_worker", dsn, spec],
                            cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def finish(procs, timeout=120):
    ran = []
    for proc in procs:
        out, err = proc.communicate(timeout=timeout)
        assert proc.returncode == 0, err
        ran.append(int(out.strip().splitlines()[-1]))
    return ran


def wait_for(run_id, predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute("SELECT state, (SELECT count(*) FROM iris_ai.run_event e"
                           " WHERE e.run_id = r.id AND e.name = 'model') FROM iris_ai.ask_run r"
                           " WHERE id = %s", [run_id])
            if predicate(*cursor.fetchone()):
                return
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} never got there")


def test_a_killed_workers_agent_run_is_resumed_by_another_under_the_same_pin_and_allowance(runtime):
    lease = replace(LIMITS, lease_seconds=3)
    grant = session(make_user("select-killed@cit.edu"))
    queued = queue(worker(runtime, limits=lease), grant, "select-killed")

    first = spawn(runtime, "hang", limits=lease)
    # Killed mid-attempt: its model turn was admitted and never answered. The
    # `model` event is journaled before admission, so wait for the reservation too.
    wait_for(queued["id"], lambda state, models: state == "running" and models >= 1)
    deadline = time.monotonic() + 30
    while not ProviderReservation.objects.exists():
        assert time.monotonic() < deadline, "the first worker never admitted its attempt"
        time.sleep(0.05)
    first.kill()
    first.communicate(timeout=30)

    # It idles past the dead worker's lease, then reclaims the run under a new fence.
    [ran] = finish([spawn(runtime, "Resumed under the same pin.", limits=lease, idle=8.0)])
    assert ran == 1
    status = run(RunStore(runtime).status(grant, queued["id"]))
    assert status["state"] == "completed"
    assert status["pinned"] == queued["pinned"]
    assert status["allowance"] == queued["allowance"]
    assert accounted(queued["id"]) == ["agent", "agent"]
    # Both attempts were admitted under the run's pin: the dead one's and the resumed one's.
    assert [(r.owner, r.purpose_version, r.model) for r in ProviderReservation.objects.order_by("id")] == [
        ("ai", "agent-research-6", MODEL)] * 2


def test_two_workers_settle_agent_runs_within_the_deep_and_per_reader_caps(runtime):
    # Two processes of two slots each: four slots, one deep run and one per reader at a time.
    caps = replace(DISPATCH, max_running_per_reader=1, deep_concurrency=1, worker_concurrency=2)
    admit = worker(runtime, dispatch=caps)
    busy = session(make_user("select-busy@cit.edu"))
    queued = [queue(admit, busy, f"select-busy-{i}") for i in range(3)]
    for i in range(3):
        queued.append(queue(admit, session(make_user(f"select-deep-{i}@cit.edu")), f"select-deep-{i}",
                            depth="deep"))

    ran = finish([spawn(runtime, *["Settled."] * 6, delay=0.4, dispatch=caps) for _ in range(2)])
    assert sum(ran) == 6

    with connection.cursor() as cursor:
        cursor.execute("SELECT id::text, depth, state, started_at, finished_at FROM iris_ai.ask_run"
                       " WHERE id = ANY(%s::uuid[])", [[q["id"] for q in queued]])
        rows = cursor.fetchall()
    assert {row[2] for row in rows} == {"completed"}

    def overlapping(group):
        spans = sorted((started, finished) for *_, started, finished in group)
        return any(later[0] < earlier[1] for earlier, later in zip(spans, spans[1:]))

    one_reader = {q["id"] for q in queued[:3]}
    assert not overlapping([r for r in rows if r[0] in one_reader])
    assert not overlapping([r for r in rows if r[1] == "deep"])
