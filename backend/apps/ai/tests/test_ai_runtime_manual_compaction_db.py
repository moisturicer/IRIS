"""Compact a Conversation on the reader's request, on real PostgreSQL (IR-754, ADR-049 §19, §21).

The reader's request is a run of its own, so everything an Ask relies on is
proved for it under the restricted runtime login: one active run per
Conversation, the revision the reader saw, one run per click, Stop, a lapsed
grant, failure and scope. The executor's side is
`test_ai_runtime_manual_compaction_contract.py`'s; the recording provider
proves the contract, never a vendor's summary. Every limit here is a test value.
"""

import json
import uuid

import pytest
from django.db import connection

from .corpus import make_user
from .test_ai_runtime_agent_loop_db import agent_service, recording, reply
from .test_ai_runtime_compaction_db import follow_up, stored, turn_count
from .test_ai_runtime_research_db import POND, paper
from .test_ai_runtime_runs_db import ScriptedExecutor, run, service, session
from . import test_ai_runtime_runs_db as runs_db
from ai.agent.compaction import Compaction  # noqa: E402
from ai.runs import public  # noqa: E402
from ai.runs.dispatch import PollingNotifier  # noqa: E402
from ai.runs.executor import Result  # noqa: E402
from ai.runs.store import Conflict, NotFound, RunStore  # noqa: E402
from apps.ai.grants import issue  # noqa: E402

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

runtime = runs_db.runtime
#: Fixture values only; no production value is implied.
RULE = Compaction(threshold_tokens=1_000, summary_tokens=400, keep_exchanges=1, max_attempts=2)
SUMMARY = {"goal": "Understand the water-quality papers.", "preferences": [],
           "findings": [{"text": "Two papers study water.", "turns": [1]}], "limitations": []}


def asked(dsn, grant, key, turns):
    """A Conversation with `turns` completed Turns; its id."""
    svc = service(dsn, ScriptedExecutor(Result(answer="Answered.")))
    first, _ = run(svc.submit(grant, key=f"{key}-0", question="First?", conversation_id=None,
                              base_revision=None))
    conversation = uuid.UUID(first["conversation_id"])
    for n in range(1, turns):
        run(svc.submit(grant, key=f"{key}-{n}", question=f"Question {n + 1}?", conversation_id=conversation,
                       base_revision=n))
    return conversation


def compacting(dsn, *responses, queued=False):
    """A service whose executor can compact; `queued` leaves submissions for a worker to claim."""
    svc = agent_service(dsn, recording(*responses), compaction=RULE)
    if queued:
        svc.notifier = PollingNotifier()
    return svc


def revision_of(conversation):
    with connection.cursor() as cursor:
        cursor.execute("SELECT revision FROM iris_ai.conversation WHERE id = %s", [conversation])
        return cursor.fetchone()[0]


def runs_of(conversation):
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM iris_ai.ask_run WHERE conversation_id = %s", [conversation])
        return cursor.fetchone()[0]


def test_a_manual_compaction_condenses_older_turns_and_the_next_ask_opens_with_it(runtime):
    reader = make_user("compact-manual@cit.edu")
    grant = session(reader)
    conversation = asked(runtime, grant, "manual", 3)
    svc = compacting(runtime, reply(json.dumps(SUMMARY)))
    assert svc.can_compact

    done, created = run(svc.submit_compaction(grant, key="compact-0001", conversation_id=conversation,
                                              base_revision=3))
    assert created and done["state"] == "completed" and done["end_reason"] == "compacted"
    # A run of its own: it asks nothing and writes no Turn or revision.
    assert done["question"] is None and done["turn_id"] is None and done["pinned"]["kind"] == "compact"
    assert turn_count(conversation) == 3 and revision_of(conversation) == 3
    assert stored(conversation) == [(1, 2)]
    [summary] = svc.executor.provider.requests
    assert summary["tool_choice"] == "none"

    # What a reconnecting or reopening reader sees: one coherent compacted outcome.
    seen = public.run(run(svc.store.status(grant, done["id"], reader_projection=True)), manual_compaction=True)
    assert seen["kind"] == "compact" and seen["state"] == "completed" and seen["question"] == ""
    assert seen["compaction"] == {"compactions": 1, "turns_compacted": 2, "last": "compacted"}
    assert seen["context"]["estimated"] is True
    reopened = public.conversation(run(svc.store.reopen(grant, conversation, include_runs=True)))
    assert [t["ordinal"] for t in reopened["turns"]] == [1, 2, 3]
    assert reopened["runs"][-1]["kind"] == "compact" and reopened["runs"][0]["kind"] == "ask"

    # The next run opens with the handoff and only the Turns after it; the originals stay.
    _, later = follow_up(runtime, grant, "manual-next", conversation, 3)
    assert later.handoff["revision"] == 1 and later.handoff["through_ordinal"] == 2
    assert [t.ordinal for t in later.prior] == [3]


def test_a_second_click_is_the_same_run_and_one_summary(runtime):
    grant = session(make_user("compact-twice@cit.edu"))
    conversation = asked(runtime, grant, "twice", 3)
    svc = compacting(runtime, reply(json.dumps(SUMMARY)))

    first, created = run(svc.submit_compaction(grant, key="compact-0002", conversation_id=conversation,
                                               base_revision=3))
    again, created_again = run(svc.submit_compaction(grant, key="compact-0002", conversation_id=conversation,
                                                     base_revision=3))
    assert created and not created_again and again["id"] == first["id"]
    assert len(svc.executor.provider.requests) == 1 and runs_of(conversation) == 4

    # The same key can never replay as a different request.
    with pytest.raises(Conflict) as mismatch:
        run(svc.submit_compaction(grant, key="compact-0002", conversation_id=conversation, base_revision=2))
    assert mismatch.value.code == "request_mismatch"

    # A new request with nothing newer to condense is harmless: no summary, no second handoff.
    nothing, _ = run(svc.submit_compaction(grant, key="compact-0003", conversation_id=conversation,
                                           base_revision=3))
    assert nothing["state"] == "completed" and nothing["end_reason"] == "nothing_to_compact"
    assert len(svc.executor.provider.requests) == 1 and stored(conversation) == [(1, 2)]
    shown = public.run(run(svc.store.status(grant, nothing["id"], reader_projection=True)))
    assert shown["compaction"] == {"compactions": 0, "turns_compacted": 0, "last": "kept"}


def test_a_conversation_with_one_turn_has_nothing_to_condense(runtime):
    grant = session(make_user("compact-short@cit.edu"))
    conversation = asked(runtime, grant, "short", 1)
    svc = compacting(runtime)
    done, _ = run(svc.submit_compaction(grant, key="compact-0004", conversation_id=conversation,
                                        base_revision=1))
    assert done["state"] == "completed" and done["end_reason"] == "nothing_to_compact"
    assert svc.executor.provider.requests == [] and stored(conversation) == []


# --- One active run, and the revision the reader saw ---------------------------

def test_a_compaction_never_runs_beside_an_active_run_and_neither_does_an_ask(runtime):
    grant = session(make_user("compact-active@cit.edu"))
    conversation = asked(runtime, grant, "active", 3)
    svc = compacting(runtime, reply(json.dumps(SUMMARY)), queued=True)

    live, _ = run(svc.submit(grant, key="active-ask", question="Still researching?", conversation_id=conversation,
                             base_revision=3))
    assert live["state"] == "queued"
    with pytest.raises(Conflict) as busy:
        run(svc.submit_compaction(grant, key="compact-0005", conversation_id=conversation, base_revision=3))
    # The investigation's budget is not shared, extended or interrupted.
    assert busy.value.code == "run_in_progress" and busy.value.detail["run_id"] == str(live["id"])
    assert svc.executor.provider.requests == []

    run(svc.store.cancel(grant, live["id"]))
    queued, _ = run(svc.submit_compaction(grant, key="compact-0006", conversation_id=conversation,
                                          base_revision=3))
    assert queued["state"] == "queued"
    with pytest.raises(Conflict) as ask_busy:
        run(svc.submit(grant, key="active-ask-2", question="Another?", conversation_id=conversation,
                       base_revision=3))
    assert ask_busy.value.code == "run_in_progress"
    # A second click with another key joins nothing and starts nothing.
    with pytest.raises(Conflict) as double:
        run(svc.submit_compaction(grant, key="compact-0007", conversation_id=conversation, base_revision=3))
    assert double.value.code == "run_in_progress" and double.value.detail["run_id"] == str(queued["id"])


def test_a_stale_revision_is_refused_and_admits_nothing(runtime):
    grant = session(make_user("compact-stale@cit.edu"))
    conversation = asked(runtime, grant, "stale", 3)
    svc = compacting(runtime, reply(json.dumps(SUMMARY)))
    before = runs_of(conversation)
    with pytest.raises(Conflict) as moved:
        run(svc.submit_compaction(grant, key="compact-0008", conversation_id=conversation, base_revision=2))
    assert moved.value.code == "revision_conflict" and moved.value.detail == {"revision": 3}
    assert runs_of(conversation) == before and svc.executor.provider.requests == []


def test_a_moved_conversation_ends_the_run_conflicted_and_its_handoff_is_never_used(runtime):
    grant = session(make_user("compact-moved@cit.edu"))
    conversation = asked(runtime, grant, "moved", 3)
    svc = compacting(runtime, reply(json.dumps(SUMMARY)), queued=True)
    queued, _ = run(svc.submit_compaction(grant, key="compact-0009", conversation_id=conversation,
                                          base_revision=3))
    # A Turn lands after the reader asked, as a second tab's answer would.
    with connection.cursor() as cursor:
        cursor.execute("UPDATE iris_ai.conversation SET revision = revision + 1 WHERE id = %s", [conversation])
    assert run(svc.run_next())
    ended = run(svc.store.status(grant, queued["id"]))
    # The summary no longer covers the whole history, so it is not committed, and the run did not complete.
    assert stored(conversation) == [] and ended["state"] == "failed"
    _, later = follow_up(runtime, grant, "moved-next", conversation, 4)
    assert later.handoff is None


# --- Failure, Stop and a lapsed grant keep the preceding context ---------------

def test_a_failed_summary_ends_unavailable_and_changes_nothing(runtime):
    grant = session(make_user("compact-failed@cit.edu"))
    conversation = asked(runtime, grant, "failed", 3)
    svc = compacting(runtime, reply("not json at all"))
    done, _ = run(svc.submit_compaction(grant, key="compact-0010", conversation_id=conversation,
                                        base_revision=3))
    assert done["state"] == "failed" and stored(conversation) == []
    assert turn_count(conversation) == 3 and revision_of(conversation) == 3
    # A failed run's handoff never opens a later run, and the Conversation carries on whole.
    _, later = follow_up(runtime, grant, "failed-next", conversation, 3)
    assert later.handoff is None and [t.ordinal for t in later.prior] == [1, 2, 3]
    # The reader can try again: the failure is not remembered against them.
    svc = compacting(runtime, reply(json.dumps(SUMMARY)))
    retry, created = run(svc.submit_compaction(grant, key="compact-0011", conversation_id=conversation,
                                               base_revision=3))
    assert created and retry["state"] == "completed" and stored(conversation) == [(1, 2)]


def test_stop_ends_a_queued_compaction_before_anything_is_sent(runtime):
    grant = session(make_user("compact-stop@cit.edu"))
    conversation = asked(runtime, grant, "stop", 3)
    svc = compacting(runtime, reply(json.dumps(SUMMARY)), queued=True)
    queued, _ = run(svc.submit_compaction(grant, key="compact-0012", conversation_id=conversation,
                                          base_revision=3))
    stopped = run(svc.store.cancel(grant, queued["id"], reader_projection=True))
    assert public.run(stopped)["state"] == "cancelled"
    assert run(svc.run_next()) is False
    assert svc.executor.provider.requests == [] and stored(conversation) == []
    # Stopping again is the same outcome, and the Conversation takes new work.
    assert public.run(run(svc.store.cancel(grant, queued["id"], reader_projection=True)))["state"] == "cancelled"
    _, later = follow_up(runtime, grant, "stop-next", conversation, 3)
    assert later.handoff is None


def test_a_lapsed_grant_waits_for_the_reader_and_a_reconnect_resumes_it(runtime):
    reader = make_user("compact-lapsed@cit.edu")
    grant = session(reader)
    conversation = asked(runtime, grant, "lapsed", 3)
    svc = compacting(runtime, reply(json.dumps(SUMMARY)), queued=True)
    queued, _ = run(svc.submit_compaction(grant, key="compact-0013", conversation_id=conversation,
                                          base_revision=3))
    with connection.cursor() as cursor:
        cursor.execute("UPDATE iris_ai.ask_run SET grant_expires_at = now() - interval '1 second' WHERE id = %s",
                       [queued["id"]])
    # A lapsed grant waits for its reader rather than running unauthorised.
    assert run(svc.run_next()) is False
    assert svc.executor.provider.requests == []
    with connection.cursor() as cursor:
        cursor.execute("SELECT state, grant_expires_at <= now() FROM iris_ai.ask_run WHERE id = %s", [queued["id"]])
        assert cursor.fetchone() == ("queued", True)

    # Reconnecting with a fresh grant renews it; the same run goes on, once.
    fresh = session(reader)
    assert run(svc.store.status(fresh, queued["id"]))["state"] == "queued"
    assert run(svc.run_next()) is True
    assert run(svc.store.status(fresh, queued["id"]))["state"] == "completed"
    assert stored(conversation) == [(1, 2)] and len(svc.executor.provider.requests) == 1


# --- Whose Conversation, and which scope ---------------------------------------

def test_only_the_owner_can_compact_and_a_deleted_conversation_is_gone(runtime):
    owner = session(make_user("compact-owner@cit.edu"))
    other = session(make_user("compact-other@cit.edu"))
    conversation = asked(runtime, owner, "owner", 3)
    svc = compacting(runtime, reply(json.dumps(SUMMARY)))
    with pytest.raises(NotFound):
        run(svc.submit_compaction(other, key="compact-0014", conversation_id=conversation, base_revision=3))
    with pytest.raises(NotFound):
        run(svc.submit_compaction(owner, key="compact-0015", conversation_id=uuid.uuid4(), base_revision=0))
    run(RunStore(runtime).delete_conversation(owner, conversation))
    with pytest.raises(NotFound):
        run(svc.submit_compaction(owner, key="compact-0016", conversation_id=conversation, base_revision=3))
    assert svc.executor.provider.requests == []


def test_a_paper_chat_grant_cannot_compact_a_wider_conversation_and_the_reverse(runtime):
    reader = make_user("compact-scope@cit.edu")
    chosen = paper("Pond sampling", {2: [("Methods", POND)]})
    general = session(reader)
    scoped = issue.reader_session_grant(reader, chosen.pk).token
    conversation = asked(runtime, general, "scope", 3)
    svc = compacting(runtime, reply(json.dumps(SUMMARY)))
    # Compaction never widens or narrows a Conversation's Record scope.
    with pytest.raises(Conflict) as widened:
        run(svc.submit_compaction(scoped, key="compact-0017", conversation_id=conversation, base_revision=3))
    assert widened.value.code == "scope_mismatch"
    with pytest.raises(Conflict) as narrowed:
        run(svc.submit_compaction(general, key="compact-0018",
                                  conversation_id=run(RunStore(runtime).admit(
                                      scoped, key="chat-open", question="About this paper?",
                                      conversation_id=None, base_revision=None, deadline_seconds=60,
                                      allowance=runs_db.LIMITS.allowance(), pinned={}))[0]["conversation_id"],
                                  base_revision=0))
    assert narrowed.value.code == "scope_mismatch"


# --- The reader's capability follows the deployment ----------------------------

def test_a_deployment_without_a_compaction_rule_offers_no_manual_compaction(runtime):
    assert not agent_service(runtime, recording(), compaction=None).can_compact
    assert not service(runtime, ScriptedExecutor()).can_compact
    assert compacting(runtime).can_compact
