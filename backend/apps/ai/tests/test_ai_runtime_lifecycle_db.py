"""Stop, reconnect and Retry of an AI-owned investigation, on real PostgreSQL (IR-726, ADR-049 §2, §11, §21).

The reader's lifecycle through the authenticated routes and the worker seam,
under the restricted `iris_ai_runtime` login with Django-issued grants. Races
run in independent processes (`ai.tests.race_worker`). A deterministic
provider proves these contracts, never paid capacity or answer quality.
Registered with the IR-608 harness as the `ai_runtime_lifecycle` suite.
"""

import asyncio
import json
import uuid
from dataclasses import replace

import pytest
from django.db import connection

from . import test_ai_runtime_runs_db as runs_db
from .test_ai_runtime_runs_db import (
    DISPATCH, _admit_and_claim, _race, as_reader, run, service, session,
)
from .test_ai_runtime_admission_db import (
    PIN, RESERVES, limits, request, reply as direct_reply,
)
from .test_ai_runtime_agent_loop_db import agent_service, call, recording, reply, tools
from .corpus import make_user
from .test_ai_runtime_context_contract import MILLION
from ai.admission.errors import AdmissionDenied  # noqa: E402
from ai.admission.ledger import Ledger  # noqa: E402
from ai.admission.scope import RunBinding, current  # noqa: E402
from ai.admission.transport import AdmittedAgentProvider  # noqa: E402
from ai.agent.executor import AgentExecutor  # noqa: E402
from ai.domain.ports import TransientProviderError  # noqa: E402
from ai.infrastructure.recording_adapter import RecordingAgentProvider  # noqa: E402
from ai.runs.dispatch import PollingNotifier  # noqa: E402
from ai.runs.store import RunStore  # noqa: E402
from apps.ai.grants import issue  # noqa: E402
from apps.ai.models.admission import ProviderReservation  # noqa: E402
from apps.records.models import PipelineStatus, Record  # noqa: E402

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

api = runs_db.api
runtime = runs_db.runtime

PUBLIC = {"X-IRIS-Protocol": "runs-reader-1"}
TERMINAL = ("completed", "cancelled", "failed", "expired", "conflict", "deleted")


def reader(email):
    """A reader and the headers of their authenticated protocol requests."""
    user = make_user(email)
    return user, {**as_reader(session(user)), **PUBLIC}


def queue(holder, svc):
    """Submissions are committed and left for a worker; nothing wakes one."""
    svc.notifier = PollingNotifier()
    holder["service"] = svc
    return svc


def ask(client, headers, key, question="What did the paper find?", **body):
    return client.post("/api/v1/ai/runs", headers={**headers, "Idempotency-Key": key},
                       json={"question": question, **body})


def retry(client, headers, run_id, key):
    return client.post(f"/api/v1/ai/runs/{run_id}/retry", headers={**headers, "Idempotency-Key": key})


def stop(client, headers, run_id):
    return client.post(f"/api/v1/ai/runs/{run_id}/cancel", headers=headers)


def reconnect(client, headers, run_id, after=None):
    url = f"/api/v1/ai/runs/{run_id}" + ("" if after is None else f"?after={after}")
    return client.get(url, headers=headers)


def rows(sql, *params):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def events_of(run_id):
    return [name for (name,) in rows(
        "SELECT name FROM iris_ai.run_event WHERE run_id = %s ORDER BY sequence", run_id)]


def turns_of(conversation_id):
    return rows("SELECT run_id FROM iris_ai.turn WHERE conversation_id = %s", conversation_id)


def terminal_events(run_id):
    return [name for name in events_of(run_id) if name in TERMINAL]


# --- Reconnect ---------------------------------------------------------------

def test_a_reader_who_left_a_queued_run_reconnects_with_a_cursor_and_is_replayed_in_order(api, runtime):
    client, holder = api
    svc = queue(holder, agent_service(runtime, recording(
        tools(call("plan-1", "update_plan", steps=[
            {"id": "compare", "title": "Compare the findings", "status": "in_progress"}])),
        reply("General background."))))
    _, headers = reader("life-reconnect@cit.edu")
    queued = ask(client, headers, "life-reconnect-1").json()
    assert queued["state"] == "queued" and queued["cursor"] == 1 and "journal" not in queued
    allowance = rows("SELECT allowance FROM iris_ai.ask_run WHERE id = %s", queued["id"])

    # The browser went away; reconnecting changes nothing about the run.
    waiting = reconnect(client, headers, queued["id"], after=queued["cursor"]).json()
    assert waiting["state"] == "queued" and waiting["journal"] == [] and waiting["cursor"] == 1

    assert run(svc.run_next()) is True
    replay = reconnect(client, headers, queued["id"], after=queued["cursor"]).json()
    assert replay["state"] == "completed"
    positions = [entry["position"] for entry in replay["journal"]]
    assert positions == sorted(positions) and positions[0] > queued["cursor"]
    names = [entry["name"] for entry in replay["journal"]]
    assert names[0] == "started" and names[-1] == "completed" and "plan" in names and "context" in names
    assert replay["cursor"] == positions[-1]

    full = reconnect(client, headers, queued["id"], after=0).json()["journal"]
    assert [entry["name"] for entry in full][:1] == ["admitted"]
    assert reconnect(client, headers, queued["id"], after=replay["cursor"]).json()["journal"] == []

    # No reconnect renewed the allowance or added an attempt.
    assert rows("SELECT allowance FROM iris_ai.ask_run WHERE id = %s", queued["id"]) == allowance
    assert rows("SELECT count(*) FROM iris_ai.attempt_accounting WHERE run_id = %s", queued["id"]) == [(1,)]
    assert len(turns_of(queued["conversation_id"])) == 1


def test_a_replay_carries_no_private_trace(api, runtime):
    client, holder = api
    svc = queue(holder, agent_service(runtime, recording(
        tools(call("s", "search", query="a private tool query")), reply("General background."))))
    _, headers = reader("life-trace@cit.edu")
    started = ask(client, headers, "life-trace-01").json()
    assert run(svc.run_next()) is True
    replay = reconnect(client, headers, started["id"], after=0).json()
    text = json.dumps(replay)
    for private in ("private tool query", "scripted-model", "search", "arguments", "pinned", "end_reason",
                    "answered", "attempt", "events", "tool_calls"):
        assert private not in text
    # The run still happened: the operator's journal has what the reader's lacks.
    assert "tool" in events_of(started["id"])


def test_reconnecting_is_refused_to_everyone_but_the_owner_in_scope_while_the_conversation_stands(api, runtime):
    client, holder = api
    queue(holder, agent_service(runtime, recording(reply("Background."))))
    owner, headers = reader("life-owner@cit.edu")
    started = ask(client, headers, "life-owner-01").json()
    path = f"/api/v1/ai/runs/{started['id']}?after=0"

    _, stranger = reader("life-stranger@cit.edu")
    missing = client.get(f"/api/v1/ai/runs/{uuid.uuid4()}?after=0", headers=stranger)
    foreign = client.get(path, headers=stranger)
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json() == {"status": "not_found"}
    assert client.get(path, headers=PUBLIC).status_code == 401

    # A Paper Chat grant never reaches a Conversation of the whole corpus.
    record = Record.objects.create(title="Scope", pipeline_status=PipelineStatus.PUBLISHED)
    scoped = {**as_reader(issue.reader_session_grant(owner, record.pk).token), **PUBLIC}
    assert client.get(path, headers=scoped).status_code == 404

    assert client.get(path, headers=headers).status_code == 200
    # Deleting the Conversation fences it: the same run is now a missing one, and its journal is gone.
    deleted = client.delete(f"/api/v1/ai/conversations/{started['conversation_id']}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(path, headers=headers).status_code == 404
    assert rows("SELECT count(*) FROM iris_ai.run_event WHERE run_id = %s", started["id"]) == [(0,)]


@pytest.mark.parametrize("after, status", [("-1", 422), ("abc", 422)])
def test_a_malformed_cursor_is_refused(api, runtime, after, status):
    client, holder = api
    queue(holder, agent_service(runtime, recording(reply("Background."))))
    _, headers = reader(f"life-cursor{status}{len(after)}@cit.edu")
    started = ask(client, headers, f"life-cursor-{len(after)}").json()
    assert client.get(f"/api/v1/ai/runs/{started['id']}?after={after}", headers=headers).status_code == status


def test_a_cursor_is_part_of_the_reader_protocol_alone(api, runtime):
    client, holder = api
    holder["service"] = service(runtime)
    grant = session(make_user("life-legacy@cit.edu"))
    started = client.post("/api/v1/ai/runs", json={"question": "q"}, headers={
        **as_reader(grant), "Idempotency-Key": "life-legacy-1"}).json()
    refused = client.get(f"/api/v1/ai/runs/{started['id']}?after=0", headers=as_reader(grant))
    assert refused.status_code == 406 and refused.json() == {"status": "unsupported_protocol"}


# --- Retry -------------------------------------------------------------------

def retrying_service(runtime, *responses):
    """An AGENT answering through the admitted ledger, so every attempt is accounted."""
    provider = RecordingAgentProvider(responses=list(responses), capacities={"scripted-model": MILLION})
    transport = AdmittedAgentProvider(provider, Ledger(runtime, limits()))
    return provider, service(runtime, AgentExecutor(transport, PIN, RESERVES), notifier=PollingNotifier())


def test_a_retry_is_a_new_linked_run_with_its_own_original_limits_and_the_first_stays_charged(api, runtime):
    client, holder = api
    provider, svc = retrying_service(runtime, TransientProviderError("503"), direct_reply("Second try."))
    holder["service"] = svc
    _, headers = reader("life-retry@cit.edu")
    first = ask(client, headers, "life-retry-01").json()
    assert run(svc.run_next()) is True
    failed = reconnect(client, headers, first["id"]).json()
    assert failed["state"] == "failed" and failed["retried_by"] is None
    first_charge = rows("SELECT run_key, state, sent, charge_attempts FROM ai_providerreservation")
    assert len(first_charge) == 1 and first_charge[0][2] is True and first_charge[0][3] == 1

    created = retry(client, headers, first["id"], "life-retry-02")
    assert created.status_code == 201
    second = created.json()
    assert second["retry_of"] == first["id"] and second["id"] != first["id"]
    assert second["conversation_id"] == first["conversation_id"]
    assert (second["question"], second["base_revision"], second["state"]) == (
        first["question"], first["base_revision"], "queued")
    assert reconnect(client, headers, first["id"]).json()["retried_by"] == second["id"]
    # The original's limits, admitted afresh: neither run's allowance or deadline is the other's.
    allowances = {run_id: json.loads(allowance)
                  for run_id, allowance in rows("SELECT id::text, allowance FROM iris_ai.ask_run")}
    assert allowances[first["id"]] == allowances[second["id"]] == svc.cfg.limits.allowance()
    assert second["created_at"] > first["created_at"]

    assert run(svc.run_next()) is True
    done = reconnect(client, headers, second["id"], after=0).json()
    assert done["state"] == "completed"
    assert [row[0] for row in turns_of(first["conversation_id"])] == [uuid.UUID(second["id"])]
    # Two runs, two reservations: the first one's charge is exactly what it was.
    charged = rows("SELECT run_key, state, sent, charge_attempts FROM ai_providerreservation ORDER BY id")
    assert len(charged) == 2 and charged[0] == first_charge[0]
    assert charged[0][0] != charged[1][0] and charged[1][3] == 1
    assert rows("SELECT count(*) FROM iris_ai.attempt_accounting WHERE run_id = %s", first["id"]) == [(1,)]
    assert len(provider.requests) == 2

    # Asking again, with the same key or another, finds the run already started.
    same = retry(client, headers, first["id"], "life-retry-02")
    other = retry(client, headers, first["id"], "life-retry-03")
    assert (same.status_code, other.status_code) == (200, 200)
    assert same.json()["id"] == other.json()["id"] == second["id"]
    assert rows("SELECT count(*) FROM iris_ai.ask_run") == [(2,)]


def test_a_retry_is_refused_unless_the_run_ended_without_an_answer_and_the_conversation_stands(api, runtime):
    client, holder = api
    svc = queue(holder, agent_service(runtime, recording(reply("One."), reply("Two."), reply("Three."))))
    _, headers = reader("life-refuse@cit.edu")
    active = ask(client, headers, "life-refuse-01").json()
    # Stop first: a run in progress is not retried beside itself.
    assert retry(client, headers, active["id"], "life-refuse-02").status_code == 409

    stopped = stop(client, headers, active["id"]).json()
    assert stopped["state"] == "cancelled"
    # While another run of the Conversation is active, there is no room for a second.
    follow = ask(client, headers, "life-refuse-03", conversation_id=active["conversation_id"], base_revision=0)
    assert follow.status_code == 201
    assert retry(client, headers, active["id"], "life-refuse-04").status_code == 409
    assert run(svc.run_next()) is True
    # The Conversation has moved past the revision the question was asked against.
    assert retry(client, headers, active["id"], "life-refuse-05").status_code == 409
    # An answered run is never retried.
    assert retry(client, headers, follow.json()["id"], "life-refuse-06").status_code == 409

    _, stranger = reader("life-refuse-stranger@cit.edu")
    assert retry(client, stranger, active["id"], "life-refuse-07").status_code == 404
    assert retry(client, headers, str(uuid.uuid4()), "life-refuse-08").status_code == 404
    assert client.post(f"/api/v1/ai/runs/{active['id']}/retry",
                       headers={**PUBLIC, "Idempotency-Key": "life-refuse-09"}).status_code == 401
    assert rows("SELECT count(*) FROM iris_ai.ask_run WHERE retry_of IS NOT NULL") == [(0,)]


def test_one_key_never_names_two_retries_and_a_deleted_conversation_cannot_be_retried(api, runtime):
    client, holder = api
    queue(holder, agent_service(runtime, recording(reply("One."))))
    _, headers = reader("life-keys@cit.edu")
    a = ask(client, headers, "life-keys-0a").json()
    b = ask(client, headers, "life-keys-0b").json()
    stop(client, headers, a["id"])
    stop(client, headers, b["id"])
    assert retry(client, headers, a["id"], "life-keys-r1").status_code == 201
    # The same key for another run is a mismatch, not a second answer to the first request.
    assert retry(client, headers, b["id"], "life-keys-r1").status_code == 409

    client.delete(f"/api/v1/ai/conversations/{b['conversation_id']}", headers=headers)
    assert retry(client, headers, b["id"], "life-keys-r2").status_code == 404


def test_a_retry_counts_against_the_same_queue_bounds_as_any_new_run(api, runtime):
    client, holder = api
    svc = queue(holder, agent_service(runtime, recording(reply("One."))))
    svc.cfg = replace(svc.cfg, dispatch=replace(DISPATCH, max_active_per_reader=1))
    _, headers = reader("life-bound@cit.edu")
    first = ask(client, headers, "life-bound-01").json()
    stop(client, headers, first["id"])
    assert ask(client, headers, "life-bound-02").status_code == 201
    busy = retry(client, headers, first["id"], "life-bound-03")
    assert busy.status_code == 503 and busy.json() == {"status": "busy"}
    assert rows("SELECT count(*) FROM iris_ai.ask_run WHERE retry_of IS NOT NULL") == [(0,)]


def test_a_retry_of_a_retry_that_also_failed_is_a_further_link_in_the_chain(api, runtime):
    client, holder = api
    _, svc = retrying_service(runtime, TransientProviderError("503"), TransientProviderError("503"),
                              direct_reply("Third time."))
    holder["service"] = svc
    _, headers = reader("life-chain@cit.edu")
    first = ask(client, headers, "life-chain-001").json()
    assert run(svc.run_next()) is True
    second = retry(client, headers, first["id"], "life-chain-002").json()
    assert run(svc.run_next()) is True
    # The original already has its retry; that retry failed too, so the reader retries *it*.
    assert retry(client, headers, first["id"], "life-chain-003").json()["id"] == second["id"]
    third = retry(client, headers, second["id"], "life-chain-004")
    assert third.status_code == 201 and third.json()["retry_of"] == second["id"]
    assert run(svc.run_next()) is True
    assert reconnect(client, headers, third.json()["id"]).json()["state"] == "completed"
    assert rows("SELECT count(*) FROM iris_ai.ask_run") == [(3,)]


def test_a_paper_chat_run_is_retried_only_under_its_own_scope(api, runtime):
    client, holder = api
    queue(holder, agent_service(runtime, recording(reply("One."))))
    owner, general = reader("life-scope@cit.edu")
    record = Record.objects.create(title="Scope", pipeline_status=PipelineStatus.PUBLISHED)
    scoped = {**as_reader(issue.reader_session_grant(owner, record.pk).token), **PUBLIC}
    started = ask(client, scoped, "life-scope-001").json()
    stop(client, scoped, started["id"])
    # A grant of the whole corpus never widens a Paper Chat run, and nothing is written.
    assert retry(client, general, started["id"], "life-scope-002").status_code == 409
    assert rows("SELECT count(*) FROM iris_ai.ask_run") == [(1,)]
    assert retry(client, scoped, started["id"], "life-scope-003").status_code == 201


def test_two_processes_retrying_one_run_start_one_new_run(runtime):
    grant = session(make_user("life-retry-race@cit.edu"))
    for n in range(3):
        store, row, claim = _admit_and_claim(runtime, grant, f"life-rr-claim-{n}")
        assert run(store.cancel(grant, row["id"]))["state"] == "cancelled"
        a, b = _race(runtime, [["retry", str(row["id"]), grant, f"life-rr-a-{n}"],
                               ["retry", str(row["id"]), grant, f"life-rr-b-{n}"]])
        (first_id, first_new), (second_id, second_new) = a.split(), b.split()
        assert first_id == second_id and sorted([first_new, second_new]) == ["False", "True"]
        assert rows("SELECT count(*) FROM iris_ai.ask_run WHERE retry_of = %s", row["id"]) == [(1,)]


# --- Stop --------------------------------------------------------------------

def test_stop_after_the_request_was_sent_lets_it_finish_stays_charged_and_publishes_nothing(runtime):
    user = make_user("life-midflight@cit.edu")
    grant = session(user)
    store = RunStore(runtime)

    class StopsWhileSending(RecordingAgentProvider):
        stopped = None

        async def converse(self, request):
            binding = current()
            self.stopped = (binding, await store.cancel(grant, binding.run_id))
            return await super().converse(request)

    provider = StopsWhileSending(responses=[direct_reply("Late answer.")], capacities={"scripted-model": MILLION})
    ledger = Ledger(runtime, limits())
    svc = service(runtime, AgentExecutor(AdmittedAgentProvider(provider, ledger), PIN, RESERVES))
    submitted, _ = run(svc.submit(grant, key="life-midflight1", question="What did it find?",
                                  conversation_id=None, base_revision=None))

    binding, stopped = provider.stopped
    assert stopped["state"] == "cancelled" and stopped["end_reason"] == "stopped"
    status = run(store.status(grant, submitted["id"]))
    assert (status["state"], status["end_reason"], status["turn_id"]) == ("cancelled", "stopped", None)
    assert turns_of(submitted["conversation_id"]) == []
    assert terminal_events(submitted["id"]) == ["cancelled"]
    # The request had been sent: it finished, and it stays charged.
    [reservation] = ProviderReservation.objects.all()
    assert (reservation.sent, reservation.state, reservation.charge_attempts) == (True, "settled", 1)
    # Nothing further is admitted for the stopped run, by this attempt or any other.
    with pytest.raises(AdmissionDenied) as denied:
        run(ledger.admit(request(), RunBinding(binding.run_id, binding.fence)))
    assert denied.value.reason == "run_cancelled"
    assert len(provider.requests) == 1


def test_stop_racing_a_takeover_and_the_old_holders_final_commit_has_one_outcome(runtime):
    grant = session(make_user("life-takeover@cit.edu"))
    for n in range(5):
        store, row, claim = _admit_and_claim(runtime, grant, f"life-takeover-{n}")
        with connection.cursor() as cursor:
            cursor.execute("UPDATE iris_ai.ask_run SET lease_expires_at = now() WHERE id = %s", [row["id"]])
        commit, takeover, stopped = _race(runtime, [["commit", str(row["id"]), str(claim.fence), "A"],
                                                    ["claim", str(row["id"])],
                                                    ["stop", str(row["id"]), grant]])
        status = run(store.status(grant, row["id"]))
        turns = turns_of(row["conversation_id"])
        # Exactly one terminal outcome, written once, and it is the journal's last word.
        assert terminal_events(row["id"]) == [status["state"]]
        assert events_of(row["id"])[-1] == status["state"]
        if status["state"] == "completed":
            assert (commit, takeover, stopped) == ("completed", "none", "completed")
            assert len(turns) == 1
        else:
            assert status["state"] == "cancelled" and commit in ("cancelled", "fenced")
            assert stopped == "cancelled" and takeover in ("none", "2")
            assert turns == []
        # Whatever won, no worker holds the run any more.
        assert rows("SELECT lease_owner FROM iris_ai.ask_run WHERE id = %s", row["id"]) == [(None,)]
        # A takeover that got in is one more attempt of the same allowance; one that did not left none.
        assert rows("SELECT count(*) FROM iris_ai.attempt_accounting WHERE run_id = %s",
                    row["id"]) == [(2 if takeover == "2" else 1,)]


# --- The request/worker seam, end to end -------------------------------------

def test_a_disconnect_a_lost_wakeup_a_delayed_completion_and_a_deletion_leave_one_coherent_outcome(api, runtime):
    client, holder = api

    class LostWakeup:
        async def notify(self):
            raise ConnectionError("redis unreachable")

        async def wait(self, timeout):
            await asyncio.sleep(timeout)

    class Slow(RecordingAgentProvider):
        """Answers only after the reader's Stop has landed, as a worker slow past it would."""

        stop_now = None

        async def converse(self, request):
            if self.stop_now is not None:
                await self.stop_now()
            return await super().converse(request)

    provider = Slow(responses=[reply("Delayed answer."), reply("Retried answer.")],
                    capacities={"scripted-model": MILLION})
    svc = agent_service(runtime, provider)
    svc.notifier = LostWakeup()
    holder["service"] = svc
    _, headers = reader("life-seam@cit.edu")

    # The wakeup is lost and the browser goes away: the run is committed all the same.
    queued = ask(client, headers, "life-seam-001")
    assert queued.status_code == 201 and queued.json()["state"] == "queued"
    run_id, conversation_id = queued.json()["id"], queued.json()["conversation_id"]

    # A worker (its real loop) takes it; the reader's Stop lands while the answer is still being produced.
    grant = headers["X-IRIS-Reader-Grant"]
    provider.stop_now = lambda: svc.store.cancel(grant, uuid.UUID(run_id))
    assert run(svc.run_next()) is True
    # The delayed worker finished: it published nothing and could not revive the run.
    assert turns_of(conversation_id) == []
    assert reconnect(client, headers, run_id, after=0).json()["state"] == "cancelled"
    assert terminal_events(run_id) == ["cancelled"]

    # Retry: a new run, which a worker answers once even though its wakeup is lost too.
    provider.stop_now = None
    again = retry(client, headers, run_id, "life-seam-002").json()
    assert again["retry_of"] == run_id
    assert run(svc.run_next()) is True and run(svc.run_next()) is False
    assert reconnect(client, headers, again["id"], after=0).json()["state"] == "completed"
    assert [row[0] for row in turns_of(conversation_id)] == [uuid.UUID(again["id"])]

    # The reader deletes the Conversation: nothing of it can be reached, retried or replayed.
    assert client.delete(f"/api/v1/ai/conversations/{conversation_id}", headers=headers).status_code == 204
    for gone in (run_id, again["id"]):
        assert reconnect(client, headers, gone, after=0).status_code == 404
    assert retry(client, headers, run_id, "life-seam-003").status_code == 404
    assert turns_of(conversation_id) == []
