"""Compact handoffs on real PostgreSQL under the restricted runtime login (IR-734, ADR-049 §19, §21).

The store alone: commit under the run's fence, a concurrent Turn, a revoked
source, a later run's claim and deletion. The executor's side is
`test_ai_runtime_compaction_contract.py`'s. Every limit here is a test value.
"""

import asyncio
import uuid

import asyncpg
import pytest
from django.db import connection

from .corpus import make_user
from .test_ai_runtime_research_db import paper, write_source
from .test_ai_runtime_runs_db import LIMITS, ScriptedExecutor, run, service, session
from ai.agent.compaction import FORMAT, Handoff  # noqa: E402
from ai.runs.executor import Result  # noqa: E402
from ai.runs.store import RunStore  # noqa: E402

from . import test_ai_runtime_runs_db as runs_db

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

runtime = runs_db.runtime


def conversation_of(runtime, grant, key, turns):
    """A Conversation with `turns` completed Turns, then a follow-up run claimed on it."""
    svc = service(runtime, ScriptedExecutor(Result(answer="Answered.")))
    done, _ = run(svc.submit(grant, key=f"{key}-0", question="First?", conversation_id=None,
                             base_revision=None))
    conversation = uuid.UUID(done["conversation_id"])
    for n in range(1, turns):
        run(svc.submit(grant, key=f"{key}-{n}", question=f"Question {n + 1}?", conversation_id=conversation,
                       base_revision=n))
    return conversation, follow_up(runtime, grant, f"{key}-next", conversation, turns)


def follow_up(runtime, grant, key, conversation, revision):
    store = RunStore(runtime)
    row, _ = run(store.admit(grant, key=key, question="Tell me about the second paper.",
                             conversation_id=conversation, base_revision=revision, deadline_seconds=60,
                             # Room for the takeovers some tests make.
                             allowance={**LIMITS.allowance(), "max_attempts": 5}, pinned={}))
    return row, run(store.claim(row["id"], worker="w", lease_seconds=30, executor="x", reserved_units=1))


def handoff(*, through=2, turns=(1, 2), sources=()):
    body = {"format": FORMAT, "derived": True, "goal": "Water papers.", "preferences": [], "findings": [],
            "limitations": [], "plan": [], "shown": [1, 2], "selected": [], "excluded": [1],
            "turns": list(turns), "sources": list(sources)}
    return Handoff(body=body, through_ordinal=through, turns=tuple(turns), sources=tuple(sources),
                   binding=("scripted", "scripted-model", "chat-completions-1", "p", "t"),
                   usage={"input_tokens": 50, "output_tokens": 20})


def stored(conversation):
    with connection.cursor() as cursor:
        cursor.execute("SELECT revision, through_ordinal FROM iris_ai.conversation_handoff"
                       " WHERE conversation_id = %s ORDER BY revision", [conversation])
        return cursor.fetchall()


def turn_count(conversation):
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM iris_ai.turn WHERE conversation_id = %s", [conversation])
        return cursor.fetchone()[0]


def test_a_committed_handoff_opens_the_next_run_and_the_original_turns_stay(runtime):
    grant = session(make_user("compact-next@cit.edu"))
    conversation, (row, claim) = conversation_of(runtime, grant, "compact-next", 3)
    store = RunStore(runtime)

    assert run(store.commit_handoff(row["id"], claim.fence, handoff())) == ("committed", 1)
    run(store.commit_final(row["id"], claim.fence, Result(answer="The pond paper.")))
    assert stored(conversation) == [(1, 2)]
    # Compaction removes nothing from the Conversation's own history.
    assert turn_count(conversation) == 4

    _, later = follow_up(runtime, grant, "compact-next-2", conversation, 4)
    assert later.handoff["revision"] == 1 and later.handoff["through_ordinal"] == 2
    assert later.handoff["body"]["excluded"] == [1]
    # Only the Turns after it are carried whole, with their places in the Conversation.
    assert [(t.ordinal, t.question) for t in later.prior] == [
        (3, "Question 3?"), (4, "Tell me about the second paper.")]


def test_a_concurrent_turn_leaves_the_handoff_uncommitted(runtime):
    grant = session(make_user("compact-concurrent@cit.edu"))
    conversation, (row, claim) = conversation_of(runtime, grant, "compact-concurrent", 2)
    store = RunStore(runtime)
    # Another run commits a Turn after this one started from revision 2.
    with connection.cursor() as cursor:
        cursor.execute("UPDATE iris_ai.conversation SET revision = revision + 1 WHERE id = %s", [conversation])

    assert run(store.commit_handoff(row["id"], claim.fence, handoff())) == ("stale", None)
    assert stored(conversation) == []


def test_a_superseded_fence_cannot_commit_a_handoff(runtime):
    grant = session(make_user("compact-fenced@cit.edu"))
    conversation, (row, claim) = conversation_of(runtime, grant, "compact-fenced", 2)
    store = RunStore(runtime)
    with connection.cursor() as cursor:
        cursor.execute("UPDATE iris_ai.ask_run SET lease_expires_at = now() WHERE id = %s", [row["id"]])
    taken = run(store.claim(row["id"], worker="w2", lease_seconds=30, executor="x", reserved_units=1))

    assert run(store.commit_handoff(row["id"], claim.fence, handoff())) == ("fenced", None)
    assert run(store.commit_handoff(row["id"], taken.fence, handoff())) == ("committed", 1)
    # The replacement is told which revision its fence committed.
    with connection.cursor() as cursor:
        cursor.execute("UPDATE iris_ai.ask_run SET lease_expires_at = now() WHERE id = %s", [row["id"]])
    again = run(store.claim(row["id"], worker="w3", lease_seconds=30, executor="x", reserved_units=1))
    assert again.committed == frozenset({1})


def test_a_handoff_on_a_replaced_source_is_never_activated(runtime):
    flood = paper("Flood forecasting", {4: [("Methods", "rainfall gauges")]})
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, extraction_hash FROM public.ai_chunkset WHERE record_id = %s AND is_active",
                       [flood.pk])
        chunk_set, extraction = cursor.fetchone()
    current = f"{chunk_set}:{extraction}"
    grant = session(make_user("compact-source@cit.edu"))
    conversation, (row, claim) = conversation_of(runtime, grant, "compact-source", 3)
    store = RunStore(runtime)

    assert run(store.commit_handoff(row["id"], claim.fence, handoff(sources=("999:gone",)))) == ("stale", None)
    assert run(store.commit_handoff(row["id"], claim.fence, handoff(sources=(current,)))) == ("committed", 1)
    run(store.commit_final(row["id"], claim.fence, Result(answer="Answered.")))

    # The paper is replaced: the summary written from the old one no longer opens the Conversation.
    write_source(flood, {4: [("Methods", "replaced text")]}, "2")
    _, later = follow_up(runtime, grant, "compact-source-2", conversation, 4)
    assert later.handoff is None
    assert [t.ordinal for t in later.prior] == [1, 2, 3, 4]


def test_a_failed_runs_handoff_never_opens_a_later_run(runtime):
    grant = session(make_user("compact-failed@cit.edu"))
    conversation, (row, claim) = conversation_of(runtime, grant, "compact-failed", 2)
    store = RunStore(runtime)
    assert run(store.commit_handoff(row["id"], claim.fence, handoff())) == ("committed", 1)
    run(store.fail(row["id"], claim.fence, "unavailable"))

    _, later = follow_up(runtime, grant, "compact-failed-2", conversation, 2)
    assert later.handoff is None and [t.ordinal for t in later.prior] == [1, 2]


def test_summary_attempts_are_counted_from_the_journal_across_claims(runtime):
    grant = session(make_user("compact-count@cit.edu"))
    _, (row, claim) = conversation_of(runtime, grant, "compact-count", 2)
    with connection.cursor() as cursor:
        cursor.execute("""INSERT INTO iris_ai.run_event (run_id, sequence, name, data)
                          SELECT %s, max(sequence) + 1, 'model', '{"phase": "compact"}'
                            FROM iris_ai.run_event WHERE run_id = %s""", [row["id"], row["id"]])
        cursor.execute("UPDATE iris_ai.ask_run SET lease_expires_at = now() WHERE id = %s", [row["id"]])
    again = run(RunStore(runtime).claim(row["id"], worker="w2", lease_seconds=30, executor="x", reserved_units=1))
    assert again.compactions == 1


def test_deleting_the_conversation_removes_its_handoffs(runtime):
    grant = session(make_user("compact-delete@cit.edu"))
    conversation, (row, claim) = conversation_of(runtime, grant, "compact-delete", 2)
    store = RunStore(runtime)
    assert run(store.commit_handoff(row["id"], claim.fence, handoff()))[0] == "committed"

    run(store.delete_conversation(grant, conversation))
    assert stored(conversation) == []


def test_the_runtime_may_write_a_handoff_but_never_rewrite_one(runtime):
    grant = session(make_user("compact-grants@cit.edu"))
    conversation, (row, claim) = conversation_of(runtime, grant, "compact-grants", 2)
    assert run(RunStore(runtime).commit_handoff(row["id"], claim.fence, handoff()))[0] == "committed"

    async def rewrite():
        conn = await asyncpg.connect(runtime)
        try:
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await conn.execute("UPDATE iris_ai.conversation_handoff SET through_ordinal = 0")
        finally:
            await conn.close()

    asyncio.run(rewrite())
    with connection.cursor() as cursor:
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            cursor.execute("SELECT has_table_privilege('iris_django_runtime', 'iris_ai.conversation_handoff', %s)",
                           [privilege])
            assert cursor.fetchone()[0] is False
