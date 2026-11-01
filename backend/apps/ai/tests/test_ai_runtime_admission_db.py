"""Every AI-runtime provider attempt admitted against the shared ledger (IR-725).

Real PostgreSQL, the restricted `iris_ai_runtime` login, Django's own
`ProviderCampaign`/`ProviderReservation` tables and the recording provider.
A deterministic provider proves the contract, never paid capacity.
"""

import asyncio
import json
import subprocess
import sys
import time
from datetime import timedelta
from types import SimpleNamespace

import asyncpg
import pytest
from django.db import connection
from django.utils import timezone

# First: it puts the repository root on sys.path.
from . import test_ai_runtime_runs_db as runs_db
from .test_ai_runtime_runs_db import service, session
from ai.admission import limits as ai_limits  # noqa: E402
from ai.admission.errors import AdmissionDenied  # noqa: E402
from ai.admission.guard import SendGuard  # noqa: E402
from ai.admission.ledger import Ledger, Request  # noqa: E402
from ai.admission.report import run_report  # noqa: E402
from ai.admission.scope import RunBinding, bound  # noqa: E402
from ai.admission.transport import AdmittedAgentProvider  # noqa: E402
from ai.agent.dialect import ChatCompletions  # noqa: E402
from ai.agent.executor import AgentExecutor  # noqa: E402
from ai.agent.protocol import (  # noqa: E402
    AgentRequest, ModelTurn, Pin, StopReason, ToolCall, ToolGroup, ToolResult, User,
)
from ai.domain.ports import TransientProviderError  # noqa: E402
from ai.infrastructure.recording_adapter import HANG, RecordingAgentProvider  # noqa: E402
from ai.runs import config as runs_config  # noqa: E402
from ai.runs.store import RunStore, Unauthorized  # noqa: E402
from apps.ai.models.admission import ProviderCampaign, ProviderReservation
from .corpus import make_user  # noqa: E402

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

runtime = runs_db.runtime

PIN = Pin(
    model="scripted-model", endpoint="scripted", adapter="recording", dialect=ChatCompletions.name,
    prompt_version="agent-direct-1", tool_version="none-1", public_version=runs_config.PROTOCOL,
    state_version=runs_config.SCHEMA, data_policy="no-training",
)
# Test bounds only; no production value is implied.
ADMISSION = dict(
    AI_ADMISSION_CAMPAIGN="ir725-test",
    AI_ADMISSION_CAMPAIGN_MAX_ATTEMPTS=100,
    AI_ADMISSION_CAMPAIGN_MAX_INPUT_TOKENS=1_000_000,
    AI_ADMISSION_CAMPAIGN_MAX_OUTPUT_TOKENS=1_000_000,
    AI_ADMISSION_CAMPAIGN_MAX_COST_USD=100,
    AI_ADMISSION_CAMPAIGN_MAX_ACTIVE_MINUTES=600,
    AI_ADMISSION_RESERVE_FRACTION=0.1,
    AI_ADMISSION_LANE_CONCURRENCY=json.dumps({"research": 4}),
    AI_ADMISSION_ACCOUNT_CONCURRENCY=4,
    AI_ADMISSION_PRICES=json.dumps({"scripted-model": {"input": 1.0, "output": 2.0}}),
    AI_ADMISSION_MAX_OUTPUT_TOKENS=100,
    AI_ADMISSION_LEASE_GRACE_SECONDS=5,
)


def run(coro):
    return asyncio.run(coro)


def reply(content="An answer.", prompt_tokens=9, completion_tokens=3):
    body = {"choices": [{"message": {"role": "assistant", "content": content},
                         "finish_reason": "stop"}]}
    if prompt_tokens is not None:
        body["usage"] = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}
    return body


def limits(**overrides):
    return ai_limits.read(SimpleNamespace(**{**ADMISSION, **overrides}))


def admitted(dsn, *responses, retries=0, **overrides):
    provider = RecordingAgentProvider(responses=list(responses))
    return provider, AdmittedAgentProvider(provider, Ledger(dsn, limits(**overrides)), retries=retries)


def answer_one(dsn, email, key, transport):
    """Submit one question and drain it through `transport`."""
    built = service(dsn, AgentExecutor(transport, PIN))
    grant = session(make_user(email))
    run_, _ = run(built.submit(grant, key=key, question="What did it find?",
                               conversation_id=None, base_revision=None))
    return grant, run(RunStore(dsn).status(grant, run_["id"]))


def test_an_answered_run_settles_one_ai_reservation_to_reported_usage(runtime):
    provider, transport = admitted(runtime, reply(prompt_tokens=9, completion_tokens=3))
    _, status = answer_one(runtime, "admit-one@cit.edu", "admit-one-0001", transport)

    assert status["state"] == "completed"
    [reservation] = ProviderReservation.objects.all()
    assert (reservation.owner, reservation.purpose, reservation.purpose_version) == (
        "ai", "answer", "agent-direct-1")
    assert (reservation.state, reservation.sent, reservation.usage_reported) == ("settled", True, True)
    assert (reservation.charge_input_tokens, reservation.charge_output_tokens) == (9, 3)
    # 9 x US$1/M + 3 x US$2/M = 15 micro-dollars.
    assert reservation.charge_cost_micros == 15
    assert reservation.lane == "research"
    assert reservation.run_key == f"airun:{status['id'].replace('-', '')}"
    # The cap reserved is the cap the request carried.
    assert provider.requests[0]["max_tokens"] == 100 == reservation.reserved_output_tokens
    campaign = ProviderCampaign.objects.get(key="ir725-test")
    assert (campaign.charged_attempts, campaign.charged_cost_micros) == (1, 15)


# --- Retries, timeouts and worker death --------------------------------------

def test_a_retry_is_a_second_admitted_attempt_within_the_same_allowance(runtime):
    provider, transport = admitted(
        runtime, TransientProviderError("vendor 503"), reply(prompt_tokens=9, completion_tokens=3),
        retries=1)
    _, status = answer_one(runtime, "admit-retry@cit.edu", "admit-retry-01", transport)

    assert status["state"] == "completed"
    assert len(provider.requests) == 2
    report = run(run_report(runtime, status["id"]))
    failed, answered = report["attempts"]
    # The failed send reported nothing, so it stays charged at its reservation.
    assert (failed["state"], failed["sent"], failed["usage_reported"]) == ("settled", True, False)
    assert failed["charge_input_tokens"] == failed["reserved_input_tokens"]
    assert failed["charge_cost_micros"] == failed["reserved_cost_micros"] > 0
    assert (answered["charge_input_tokens"], answered["charge_output_tokens"]) == (9, 3)
    assert report["charged"]["attempts"] == 2
    allowance = runs_db.LIMITS.allowance()
    assert report["remaining"]["attempts"] == allowance["max_attempts"] - 2
    assert report["remaining"]["cost_micros"] == (
        500_000 - failed["charge_cost_micros"] - answered["charge_cost_micros"])
    assert report["unreported"] == 1
    # The operator surface carries no prompt, question or answer.
    assert "What did it find?" not in json.dumps(report, default=str)


def test_an_unanswered_attempt_times_out_and_keeps_its_reservation(runtime):
    provider = RecordingAgentProvider(responses=[HANG])
    transport = AdmittedAgentProvider(provider, Ledger(runtime, limits()), timeout_seconds=0.5)
    _, status = answer_one(runtime, "admit-timeout@cit.edu", "admit-timeout1", transport)

    assert (status["state"], status["end_reason"]) == ("failed", "unavailable")
    [attempt] = run(run_report(runtime, status["id"]))["attempts"]
    assert (attempt["state"], attempt["sent"], attempt["usage_reported"]) == ("settled", True, False)
    assert attempt["charge_output_tokens"] == attempt["reserved_output_tokens"] == 100
    assert attempt["charge_cost_micros"] == attempt["reserved_cost_micros"]


def test_a_dead_workers_reservation_is_abandoned_at_its_full_charge(runtime):
    ledger = Ledger(runtime, limits(AI_ADMISSION_LEASE_GRACE_SECONDS=0))
    first = claimed(runtime, "admit-dead-1@cit.edu", "admit-dead-01")
    ticket = run(ledger.admit(request(timeout_seconds=0.2), first))
    # The worker dies: no settlement ever comes.
    time.sleep(0.5)
    second = claimed(runtime, "admit-dead-2@cit.edu", "admit-dead-02")
    run(ledger.admit(request(), second))

    dead = ProviderReservation.objects.get(pk=ticket.pk)
    assert dead.state == "abandoned"
    assert dead.charge_cost_micros == dead.reserved_cost_micros > 0
    assert dead.charge_attempts == 1


# --- Nothing is sent when admission or the guard refuses ----------------------

def refused(runtime, email, key, transport, provider):
    _, status = answer_one(runtime, email, key, transport)
    assert (status["state"], status["end_reason"]) == ("failed", "unavailable")
    assert provider.requests == []
    return status


def test_missing_limits_refuse_before_anything_is_sent(runtime):
    provider = RecordingAgentProvider(responses=[reply()])
    transport = AdmittedAgentProvider(provider, Ledger.from_settings(runtime, SimpleNamespace()))
    refused(runtime, "admit-unset@cit.edu", "admit-unset-1", transport, provider)
    assert not ProviderReservation.objects.exists()


def test_an_unadmitted_paid_provider_is_never_called(runtime):
    class Paid(RecordingAgentProvider):
        paid = True

    provider = Paid(responses=[reply()])
    refused(runtime, "admit-paid@cit.edu", "admit-paid-01", provider, provider)


def test_the_run_allowance_stops_further_retries(runtime):
    # LIMITS allows two attempts per run.
    provider, transport = admitted(
        runtime, *(TransientProviderError("503") for _ in range(3)), reply(), retries=5)
    _, status = answer_one(runtime, "admit-allow@cit.edu", "admit-allow-1", transport)

    assert (status["state"], status["end_reason"]) == ("failed", "unavailable")
    assert len(provider.requests) == 2
    assert run(run_report(runtime, status["id"]))["remaining"]["attempts"] == 0


def test_the_protected_reserve_is_not_spent(runtime):
    # Two attempts, half of them reserved: one spendable, and Django spent it.
    ProviderCampaign.objects.create(key="ir725-test", charged_attempts=1)
    provider, transport = admitted(runtime, reply(), AI_ADMISSION_CAMPAIGN_MAX_ATTEMPTS=2,
                                   AI_ADMISSION_RESERVE_FRACTION=0.5)
    refused(runtime, "admit-reserve@cit.edu", "admit-reserve", transport, provider)


def test_a_django_attempt_in_flight_holds_the_shared_lane(runtime):
    campaign = ProviderCampaign.objects.create(key="ir725-test")
    now = timezone.now()
    ProviderReservation.objects.create(
        campaign=campaign, lane="research", account="django-account", operation="llm",
        model="scripted-model", created_at=now, lease_expires_at=now + timedelta(minutes=5),
        reserved_input_tokens=1, reserved_output_tokens=1, reserved_cost_micros=1,
        reserved_active_ms=1, charge_input_tokens=1, charge_output_tokens=1,
        charge_cost_micros=1, charge_active_ms=1,
    )
    provider, transport = admitted(runtime, reply(),
                                   AI_ADMISSION_LANE_CONCURRENCY=json.dumps({"research": 1}))
    refused(runtime, "admit-lane@cit.edu", "admit-lane-01", transport, provider)


def interrupt_before_send(transport, interrupt):
    """Run ``interrupt(run_id)`` after admission and before the guard's check."""
    guard = transport.guard

    class Late:
        async def check(self, binding, pin, dependencies=()):
            await interrupt(binding.run_id)
            await guard.check(binding, pin, dependencies)

    transport.guard = Late()


async def as_admin(sql, run_id):
    conn = await asyncpg.connect(runs_db.admin_dsn())
    try:
        await conn.execute(sql, run_id)
    finally:
        await conn.close()


def test_stop_between_admission_and_send_releases_the_attempt(runtime):
    provider, transport = admitted(runtime, reply())
    interrupt_before_send(transport, lambda run_id: as_admin(
        "UPDATE iris_ai.ask_run SET state = 'cancelled', fence = fence + 1 WHERE id = $1", run_id))
    _, status = answer_one(runtime, "admit-stop@cit.edu", "admit-stop-01", transport)

    assert status["state"] == "cancelled"
    assert provider.requests == []
    [attempt] = run(run_report(runtime, status["id"]))["attempts"]
    assert (attempt["state"], attempt["sent"], attempt["charge_attempts"]) == ("released", False, 0)


def test_revoked_access_between_admission_and_send_sends_nothing(runtime):
    provider, transport = admitted(runtime, reply())
    revoked = []

    async def deactivate(run_id):
        revoked.append(run_id)
        await as_admin("""UPDATE accounts_user SET is_active = false
                           WHERE id = (SELECT reader_id FROM iris_ai.ask_run WHERE id = $1)""", run_id)

    interrupt_before_send(transport, deactivate)
    built = service(runtime, AgentExecutor(transport, PIN))
    # The drained submission's projection is refused: its reader is gone.
    with pytest.raises(Unauthorized):
        run(built.submit(session(make_user("admit-revoked@cit.edu")), key="admit-revoke1",
                         question="Q?", conversation_id=None, base_revision=None))

    # Look as an operator instead.
    [run_id] = revoked
    assert provider.requests == []
    assert ProviderReservation.objects.get().state == "released"
    with connection.cursor() as cursor:
        cursor.execute("SELECT state, end_reason FROM iris_ai.ask_run WHERE id = %s", [run_id])
        assert cursor.fetchone() == ("failed", "unavailable")


def test_a_provider_without_a_no_training_policy_is_refused(runtime):
    pin = Pin(**{**PIN.as_dict(), "requires": (), "data_policy": "vendor-default"})
    with pytest.raises(AdmissionDenied) as denied:
        run(SendGuard(runtime).check(None, pin))
    assert denied.value.reason == "provider_refused"


def test_evidence_the_runtime_cannot_authorize_is_withheld(runtime):
    with pytest.raises(AdmissionDenied) as denied:
        run(SendGuard(runtime).check(None, PIN, dependencies=[("passage", 1)]))
    assert denied.value.reason == "source_unavailable"


def test_tool_results_in_the_request_are_withheld_by_the_transport(runtime):
    provider, transport = admitted(runtime, reply())
    binding = claimed(runtime, "admit-evidence@cit.edu", "admit-evidence")
    request = AgentRequest(pin=PIN, instructions="I", history=(
        User("Q?"), ModelTurn(items=(ToolGroup((ToolCall("c1", "search"),)),), stop=StopReason.TOOLS),
        ToolResult("c1", "a passage"),
    ))
    with bound(binding), pytest.raises(AdmissionDenied) as denied:
        run(transport.converse(request))
    assert denied.value.reason == "source_unavailable"
    assert provider.requests == []
    assert ProviderReservation.objects.get().state == "released"


def test_redelivery_never_renews_the_run_allowance(runtime):
    ledger = Ledger(runtime, limits())
    first = claimed(runtime, "admit-redeliver@cit.edu", "admit-redeliver")
    run(ledger.admit(request(), first))
    # The worker's lease runs out; another worker claims the run under a new fence.
    with connection.cursor() as cursor:
        cursor.execute("UPDATE iris_ai.ask_run SET lease_expires_at = now() - interval '1 second'"
                       " WHERE id = %s", [first.run_id])
    claim = run(RunStore(runtime).claim(first.run_id, worker="w2", lease_seconds=30,
                                        executor="x", reserved_units=0))
    second = RunBinding(claim.run_id, claim.fence)
    assert second.fence > first.fence
    with pytest.raises(AdmissionDenied) as stale:
        run(ledger.admit(request(), first))
    assert stale.value.reason == "run_cancelled"
    # LIMITS allows two attempts; the first fence's attempt still counts.
    run(ledger.admit(request(), second))
    with pytest.raises(AdmissionDenied) as spent:
        run(ledger.admit(request(), second))
    assert spent.value.reason == "run_budget_exhausted"


def test_the_runtime_cannot_rewrite_a_reservation(runtime):
    binding = claimed(runtime, "admit-rewrite@cit.edu", "admit-rewrite")
    ticket = run(Ledger(runtime, limits()).admit(request(), binding))

    async def rewrite():
        conn = await asyncpg.connect(runtime)
        try:
            await conn.execute("UPDATE public.ai_providerreservation SET reserved_cost_micros = 0"
                               " WHERE id = $1", ticket.pk)
        finally:
            await conn.close()

    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        run(rewrite())


# --- Independent processes ---------------------------------------------------

def test_two_processes_racing_for_the_last_attempt_admit_exactly_one(runtime):
    # Four attempts, half reserved: two spendable, one already spent.
    settings = {**ADMISSION, "AI_ADMISSION_CAMPAIGN_MAX_ATTEMPTS": 4,
                "AI_ADMISSION_RESERVE_FRACTION": 0.5}
    first = claimed(runtime, "admit-race-0@cit.edu", "admit-race-00")
    run(Ledger(runtime, ai_limits.read(SimpleNamespace(**settings))).admit(request(), first))
    racers = [claimed(runtime, f"admit-race-{n}@cit.edu", f"admit-race-0{n}") for n in (1, 2)]

    outputs = race(runtime, [[str(b.run_id), str(b.fence), json.dumps(settings)] for b in racers])

    assert sorted(outputs) == ["admitted", "campaign_exhausted"]
    campaign = ProviderCampaign.objects.get(key="ir725-test")
    assert campaign.charged_attempts == 2 == ProviderReservation.objects.count()


# --- Helpers -----------------------------------------------------------------

class Quiet:
    async def notify(self):
        pass

    async def wait(self, timeout):
        pass


def claimed(dsn, email, key) -> RunBinding:
    """A run submitted and claimed, as a worker holds it."""
    built = service(dsn, notifier=Quiet())
    run_, _ = run(built.submit(session(make_user(email)), key=key, question="Q?",
                               conversation_id=None, base_revision=None))
    claim = run(built.store.claim(run_["id"], worker="w", lease_seconds=30, executor="x",
                                  reserved_units=0))
    return RunBinding(claim.run_id, claim.fence)


def request(**overrides):
    return Request(**{**dict(
        operation="llm", purpose="answer", purpose_version="test", lane="research",
        account="test-account", models=("scripted-model",), input_tokens=10, output_tokens=10,
    ), **overrides})


def race(dsn, commands):
    """Start every worker blocked on one lock, release them together, collect outputs."""
    loop = asyncio.new_event_loop()
    holder = loop.run_until_complete(asyncpg.connect(runs_db.admin_dsn()))
    try:
        loop.run_until_complete(holder.execute("SELECT pg_advisory_lock(725)"))
        procs = [subprocess.Popen(
            [sys.executable, "-m", "ai.tests.admission_race_worker", dsn, *cmd],
            cwd=runs_db.REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ) for cmd in commands]
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            waiting = loop.run_until_complete(holder.fetchval(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'"
                " AND objid = 725 AND NOT granted"))
            if waiting == len(commands):
                break
            time.sleep(0.05)
        else:
            pytest.fail("racers never all reached the barrier")
        loop.run_until_complete(holder.execute("SELECT pg_advisory_unlock(725)"))
        outputs = []
        for proc in procs:
            out, err = proc.communicate(timeout=60)
            assert proc.returncode == 0, err
            outputs.append(out.strip())
        return outputs
    finally:
        loop.run_until_complete(holder.close())
        loop.close()
