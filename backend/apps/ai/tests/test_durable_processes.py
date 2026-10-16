"""Durability fences across independent Python interpreters (IR-597).

Each child boots its own Django and connects to the real shared test Postgres.
Stdin gates make the winning commit explicit; no clock delays choose the race.
Only generation is scripted, so these are correctness evidence, not throughput.
"""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import pytest
from django.db import connections
from django.utils import timezone

from apps.ai import durable
from apps.ai.admission.tests.support import CAMPAIGN, enforce
from apps.ai.models import AskRun, Conversation, ConversationState, ProviderReservation, Turn

from .corpus import make_user

pytestmark = [
    pytest.mark.db_required,
    pytest.mark.django_db(transaction=True, databases=["default", "admission"]),
]
BACKEND = Path(__file__).resolve().parents[3]


def _environment():
    env = {**os.environ, **CAMPAIGN}
    database = connections["default"].settings_dict
    env.update(
        AI_PROVIDER_ADMISSION="enforce", AI_EVIDENCE_DECISION="off",
        AI_RESEARCH_LANE="off", AI_JEV_ROUTING_ENABLED="False",
        DB_NAME=str(database["NAME"]), DB_USER=str(database["USER"]),
        DB_PASSWORD=str(database["PASSWORD"]), DB_HOST=str(database["HOST"]),
        DB_PORT=str(database["PORT"]),
        DJANGO_SETTINGS_MODULE="config.settings.development",
    )
    return env


@contextmanager
def _probe(mode, run):
    process = subprocess.Popen(
        [sys.executable, "-m", "apps.ai.tests.durable_probe", mode, str(run.pk)],
        cwd=BACKEND, env=_environment(), stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        yield process
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=15)


def _result(process, *, resume=False, expected_code=0):
    out, err = process.communicate("continue\n" if resume else None, timeout=60)
    assert process.returncode == expected_code, err[-3000:]
    lines = [json.loads(line) for line in out.splitlines() if line.startswith("{")]
    assert lines, f"No probe result; stderr: {err[-3000:]}"
    return lines[-1]


def _ready(process):
    # readline itself blocks; the bounded future ensures startup failures cannot
    # hang pytest. Kill first on timeout so executor cleanup also completes.
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(process.stdout.readline)
        try:
            line = pending.result(timeout=60)
        except TimeoutError:
            process.kill()
            raise
    assert line.startswith("{"), "Probe exited before its ready handshake"
    result = json.loads(line)
    assert "ready" in result, result
    return result


@pytest.fixture
def run(settings):
    enforce(settings)
    user = make_user("independent-worker@cit.edu")
    conversation = Conversation.objects.create(user=user)
    return AskRun.objects.create(
        user=user, conversation=conversation,
        request={"question": "probe question", "top_k": 1, "context_revision": 0},
        deadline_at=timezone.now() + timedelta(minutes=5),
    )


def _assert_fenced(result):
    assert result["refusal"] is not None, result
    assert result["sent"] == 1, "only the call sent before the winning commit was admitted"
    assert result["writes"] == {"append": "fenced", "finish": "fenced", "turn": "fenced"}


def _reservations(run):
    return ProviderReservation.objects.using("admission").filter(run_key=f"ask:{run.pk}")


def test_superseded_process_cannot_admit_append_finish_or_write_a_turn(run):
    with _probe("hold", run) as old:
        ready = _ready(old)
        with _probe("deliver", run) as replacement:
            _result(replacement)
        result = _result(old, resume=True)

    _assert_fenced(result)
    run.refresh_from_db()
    assert run.state == "succeeded"
    assert list(run.attempts.values_list("state", flat=True)) == ["superseded", "finished"]
    assert str(run.attempts.first().pk) == ready["ready"]
    assert Turn.objects.filter(conversation=run.conversation).count() == 1
    assert run.events.filter(name="done").count() == 1
    assert not run.events.filter(data__text="stale").exists()
    assert _reservations(run).count() == 1


def test_cancel_in_another_process_fences_new_paid_calls_and_all_writes(run):
    with _probe("hold", run) as worker:
        _ready(worker)
        durable.cancel(run.pk, run.user)
        journal_count = run.events.count()
        result = _result(worker, resume=True)

    _assert_fenced(result)
    assert result["refusal"] == "run_cancelled"
    run.refresh_from_db()
    assert run.state == "cancelled" and run.turn_id is None
    assert run.events.count() == journal_count
    assert not Turn.objects.filter(conversation=run.conversation).exists()
    assert not ConversationState.objects.filter(conversation=run.conversation).exists()
    reservation = _reservations(run).get()
    assert reservation.charge_cost_micros > 0, "already sent work remains charged"


def test_crash_redelivery_and_duplicate_delivery_commit_exactly_one_final_turn(run):
    deadline = run.deadline_at
    with _probe("crash", run) as crashed:
        _result(crashed, expected_code=23)
    assert not Turn.objects.filter(conversation=run.conversation).exists()
    with _probe("deliver", run) as redelivered:
        _result(redelivered)
    event_count = run.events.count()
    with _probe("deliver", run) as duplicate:
        _result(duplicate)

    run.refresh_from_db()
    assert run.deadline_at == deadline
    assert run.state == "succeeded"
    assert list(run.attempts.values_list("state", flat=True)) == ["superseded", "finished"]
    assert Turn.objects.filter(conversation=run.conversation).count() == 1
    assert run.events.count() == event_count
    assert run.events.filter(name="done").count() == 1
    assert list(run.events.values_list("sequence", flat=True)) == list(range(1, event_count + 1))
    assert ConversationState.objects.get(conversation=run.conversation).revision == 1


def test_real_controller_crash_retains_shared_spend_and_rebuilds_evidence(run, budget, settings):
    from apps.ai.controller.durable_budget import prepare_request
    from apps.ai.controller.versions import CONTROLLER_ENGINE, pin

    settings.AI_CONTROLLER_MAX_ROUNDS = 2
    run.request = prepare_request({**run.request, "conversation_id": run.conversation_id,
                                   "pin": pin(CONTROLLER_ENGINE)})
    run.save(update_fields=["request"])
    deadline = run.deadline_at
    with _probe("controller_crash", run) as crashed:
        result = _result(crashed, expected_code=23)
        assert result["controller_crashed"]
    run.refresh_from_db()
    spent = run.request["controller_budget"]["spent"]
    assert spent["rounds"] == 2 and spent["tool_calls"] == 1
    assert spent["prompt_tokens"] > 0
    assert _reservations(run).count() == 2
    assert _reservations(run).filter(state="open").count() == 1
    assert not Turn.objects.filter(conversation=run.conversation).exists()

    with _probe("controller_deliver", run) as recovered:
        assert _result(recovered)["planner_calls"] == 0
    with _probe("controller_deliver", run) as duplicate:
        assert _result(duplicate)["planner_calls"] == 0
    run.refresh_from_db()
    assert run.deadline_at == deadline
    assert run.request["controller_budget"]["spent"] == spent
    assert _reservations(run).count() == 2
    assert Turn.objects.filter(conversation=run.conversation).count() == 1
    assert run.turn.state == "unavailable"
    assert run.events.filter(name="done").count() == 1
    assert not run.turn.reasoning_summary
