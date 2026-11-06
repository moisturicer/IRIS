"""Recover original Turns and respect deletion on real PostgreSQL (IR-735, ADR-049 §19, §21).

The store and the research tools under the restricted runtime login and
Django-issued grants: who may recover which Turn, what a revoked or replaced
source does to recovery and to a handoff, and what deletion removes. The
executor's side is `test_ai_runtime_turn_recovery_contract.py`'s. Every limit
here is a test value.
"""

import uuid

import pytest
from django.db import connection

from .corpus import make_user
from .test_ai_runtime_compaction_db import follow_up, handoff, stored
from .test_ai_runtime_research_db import FLOOD, paper, write_source
from .test_ai_runtime_runs_db import ScriptedExecutor, run, service, session
from ai.research.tools import OK, ResearchTools
from ai.runs.executor import Citation, Result
from ai.runs.store import NotFound, RunStore

from . import test_ai_runtime_runs_db as runs_db

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

runtime = runs_db.runtime

CONTENT_TABLES = ("turn", "citation", "conversation_handoff", "research_handle", "run_event", "run_checkpoint")


def revision_of(record):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, extraction_hash FROM public.ai_chunkset WHERE record_id = %s AND is_active",
                       [record.pk])
        chunk_set, extraction = cursor.fetchone()
    return f"{chunk_set}:{extraction}"


class Recovery:
    """One finished Turn that cited a paper, then a follow-up run claimed on its Conversation."""

    def __init__(self, runtime, email, key):
        self.runtime = runtime
        self.flood = paper("Flood forecasting", {4: [("Methods", FLOOD)]})
        self.revision = revision_of(self.flood)
        self.reader = make_user(email)
        self.grant = session(self.reader)
        cited = Citation(record_id=self.flood.pk, quote=FLOOD, page=4, revision=self.revision)
        svc = service(runtime, ScriptedExecutor(Result(answer="It trained on gauges [1].", citations=(cited,))))
        done, _ = run(svc.submit(self.grant, key=f"{key}-0", question="What did it train on?",
                                 conversation_id=None, base_revision=None))
        self.conversation = uuid.UUID(done["conversation_id"])
        self.row, self.claim = follow_up(runtime, self.grant, f"{key}-next", self.conversation, 1)
        self.store = RunStore(runtime)

    def tools(self, claim=None, row=None, scope="claim"):
        claim, row = claim or self.claim, row or self.row
        return ResearchTools(self.runtime, claim.grant, row["id"], claim.fence,
                             claim.scope_record_id if scope == "claim" else scope)

    def count(self, table):
        with connection.cursor() as cursor:
            if table in ("turn", "conversation_handoff"):
                cursor.execute(f"SELECT count(*) FROM iris_ai.{table} WHERE conversation_id = %s", [self.conversation])
            elif table == "citation":
                cursor.execute("SELECT count(*) FROM iris_ai.citation WHERE turn_id IN"
                               " (SELECT id FROM iris_ai.turn WHERE conversation_id = %s)", [self.conversation])
            else:
                cursor.execute(f"SELECT count(*) FROM iris_ai.{table} WHERE run_id IN"
                               " (SELECT id FROM iris_ai.ask_run WHERE conversation_id = %s)", [self.conversation])
            return cursor.fetchone()[0]

    def checkpoint(self):
        """What a running run saves after a step, which holds the text it recovered."""
        run(self.store.save_checkpoint(self.row["id"], self.claim.fence, 1,
                                       {"history": "recovered text", "recovered": {"1": "It trained on gauges."}},
                                       lease_seconds=30))

    def accounting(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM iris_ai.attempt_accounting WHERE run_id IN"
                           " (SELECT id FROM iris_ai.ask_run WHERE conversation_id = %s)", [self.conversation])
            return cursor.fetchone()[0]


# --- Recovery and its authorization ----------------------------------------------------

def test_the_owner_recovers_the_original_turn_and_its_passage_by_a_fresh_handle(runtime):
    case = Recovery(runtime, "recover-owner@cit.edu", "recover-owner")
    tools = case.tools()

    result = run(tools.recover_turn(1))
    assert result.status == OK
    [passage] = result.passages
    # The original answer, with its [1] marker bound to this run's handle for the stored passage.
    assert result.turn.question == "What did it train on?"
    assert result.turn.answer == f"It trained on gauges [{passage.handle}]."
    assert (passage.record_id, passage.page, passage.text, passage.source.revision) == (
        case.flood.pk, 4, FLOOD, case.revision)
    # The handle is the ordinary kind: it reads the same passage again.
    again = run(tools.open_passage(passage.handle))
    assert again.status == OK and again.passages[0].text == FLOOD


def test_only_turns_the_run_started_from_can_be_recovered(runtime):
    case = Recovery(runtime, "recover-bounds@cit.edu", "recover-bounds")
    tools = case.tools()
    missing = run(tools.recover_turn(99))
    # The run's own, not yet committed, Turn is not there to read.
    assert run(tools.recover_turn(2)).reason == missing.reason == "unknown_turn"
    assert run(tools.recover_turn(0)).reason == "invalid_argument"


def test_another_reader_cannot_recover_a_turn_through_this_run(runtime):
    case = Recovery(runtime, "recover-owner2@cit.edu", "recover-owner2")
    other = make_user("recover-other@cit.edu")
    theirs = ResearchTools(runtime, session(other), case.row["id"], case.claim.fence)
    stranger = run(theirs.recover_turn(1))
    assert stranger.status == "unavailable" and stranger.reason == "run_ended" and stranger.turn is None


def test_a_paper_chat_scope_that_is_not_the_conversations_recovers_nothing(runtime):
    case = Recovery(runtime, "recover-scope@cit.edu", "recover-scope")
    widened = case.tools(scope=case.flood.pk)
    assert run(widened.recover_turn(1)).reason == "unknown_turn"


def test_a_replaced_source_makes_the_turn_unrecoverable_like_a_missing_one(runtime):
    case = Recovery(runtime, "recover-replaced@cit.edu", "recover-replaced")
    tools = case.tools()
    assert run(tools.recover_turn(1)).status == OK
    missing = run(tools.recover_turn(99))

    write_source(case.flood, {4: [("Methods", "replaced text")]}, "2")
    gone = run(tools.recover_turn(1))
    assert (gone.status, gone.reason, gone.turn, gone.passages) == (missing.status, missing.reason, None, ())


def test_a_handoff_is_current_only_while_its_turns_and_sources_are(runtime):
    case = Recovery(runtime, "recover-handoff@cit.edu", "recover-handoff")
    tools = case.tools()
    assert run(tools.handoff_current([1], [case.revision])) is None
    assert run(tools.handoff_current([1], ["999:gone"])) == "stale"

    write_source(case.flood, {4: [("Methods", "replaced text")]}, "2")
    # Neither the Turn that cited the old paper nor the source it read stands.
    assert run(tools.handoff_current([1], [])) == "stale"
    assert run(tools.handoff_current([], [case.revision])) == "stale"


def test_a_deleted_conversation_is_not_recoverable_or_current(runtime):
    case = Recovery(runtime, "recover-closed@cit.edu", "recover-closed")
    tools = case.tools()
    run(case.store.delete_conversation(case.grant, case.conversation))
    assert run(tools.recover_turn(1)).status == "unavailable"
    assert run(tools.handoff_current([1], [])) == "run_ended"


# --- Deletion -----------------------------------------------------------------------------

def test_deleting_the_conversation_removes_derived_content_and_keeps_only_spend_accounting(runtime):
    case = Recovery(runtime, "recover-delete@cit.edu", "recover-delete")
    assert run(case.store.commit_handoff(case.row["id"], case.claim.fence,
                                         handoff(through=1, turns=(1,), sources=(case.revision,))))[0] == "committed"
    assert run(case.tools().recover_turn(1)).status == OK
    case.checkpoint()
    before = {table: case.count(table) for table in CONTENT_TABLES}
    spent = case.accounting()
    assert all(before.values()) and spent > 0

    run(case.store.delete_conversation(case.grant, case.conversation))
    assert {table: case.count(table) for table in CONTENT_TABLES} == {table: 0 for table in CONTENT_TABLES}
    assert stored(case.conversation) == []
    # Only the non-content spend audit survives, with no question text.
    assert case.accounting() == spent
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM iris_ai.ask_run WHERE conversation_id = %s AND question IS NOT NULL",
                       [case.conversation])
        assert cursor.fetchone()[0] == 0
    # A second deletion finds nothing and removes nothing further.
    with pytest.raises(NotFound):
        run(case.store.delete_conversation(case.grant, case.conversation))
    assert case.accounting() == spent


def test_account_deletion_purges_the_same_derived_content_once(runtime):
    case = Recovery(runtime, "recover-account@cit.edu", "recover-account")
    assert run(case.store.commit_handoff(case.row["id"], case.claim.fence,
                                         handoff(through=1, turns=(1,), sources=(case.revision,))))[0] == "committed"
    assert run(case.tools().recover_turn(1)).status == OK
    case.checkpoint()
    spent = case.accounting()

    case.reader.delete()
    assert run(case.store.purge_departed()) == 1
    assert {table: case.count(table) for table in CONTENT_TABLES} == {table: 0 for table in CONTENT_TABLES}
    assert case.accounting() == spent
    # Idempotent: a second purge has nothing left to do.
    assert run(case.store.purge_departed()) == 0
    assert case.accounting() == spent
