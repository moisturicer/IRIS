"""Recover original details after compaction (IR-735, ADR-049 §19, §21).

The executor with the recording provider and IR-728's in-memory research
stand-in. A deterministic provider proves the contract; who may recover
what, against real PostgreSQL, is `test_ai_runtime_turn_recovery_db.py`'s.
"""

import dataclasses
import json

import pytest

from .test_ai_runtime_agent_loop_contract import (
    FLOOD, PIN, PROFILES, Corpus, call, context, handle, recording, reply, run, tools,
)
from .test_ai_runtime_context_contract import RESERVES
from ai.agent import checkpoint
from ai.agent.assurance import QUALIFIER  # noqa: E402
from ai.agent.executor import AgentExecutor
from ai.agent.tools import Investigation
from ai.research.tools import RecoveredTurn
from ai.runs import public
from ai.runs.executor import PriorTurn, Unavailable

PIN_4 = dataclasses.replace(PIN, prompt_version="agent-research-4", tool_version="research-4")
SAVED = {"goal": "Water papers.", "preferences": [], "findings": [], "limitations": ["Only titles."],
         "plan": [], "shown": [1, 2], "selected": [], "excluded": [1], "turns": [1, 2, 3],
         "sources": ["11:e1"], "format": "agent-handoff-1", "derived": True}
HANDOFF = {"revision": 1, "through_ordinal": 3, "body": SAVED}
LATER = (PriorTurn("And its method?", "Weekly sampling.", "answer", ordinal=4),)
ORIGINAL = handle("P", 1)
OPEN = {"shown": [1, 2], "selected": [], "excluded": []}
EXCLUDED = {"shown": [1, 2], "selected": [], "excluded": [1]}


def agent4(provider):
    return AgentExecutor(provider, PIN_4, RESERVES, profiles=PROFILES)


def corpus_with_turn():
    corpus = Corpus()
    # The original Turn 2, its citation marker already replaced by this run's handle.
    corpus.turns[2] = (RecoveredTurn(2, "How many floods did it predict?",
                                     f"The network predicted 87 floods [{ORIGINAL}].", "answer"),
                       [corpus.papers[1][2]])
    return corpus


def ask(provider, corpus, state=OPEN, **kw):
    ctx = context(prior=LATER, state=state, handoff=HANDOFF, **kw)
    return run(agent4(provider).answer("Exactly how many floods was it?", corpus, ctx))


def tool_messages(request):
    return [json.loads(m["content"]) for m in request["messages"] if m["role"] == "tool"]


# --- Recovery ----------------------------------------------------------------------

def test_only_the_recovery_pin_offers_the_tool():
    def names(inv):
        return {s.name for s in inv.specs()}

    assert "recover_turn" not in names(Investigation(None, metadata=True, manuscripts=True))
    assert "recover_turn" in names(Investigation(None, metadata=True, manuscripts=True, recovery=True))


def test_an_exact_detail_is_read_from_the_original_turn_and_cited_from_its_source():
    corpus = corpus_with_turn()
    provider = recording(tools(call("c1", "recover_turn", turn=2)),
                         reply(f"Earlier it predicted 87 floods [{ORIGINAL}]."))
    result = ask(provider, corpus)

    [body] = tool_messages(provider.requests[1])
    # The original words come back with this run's handle for the passage they cited.
    assert body["turn"] == {"turn": 2, "question": "How many floods did it predict?",
                            "answer": f"The network predicted 87 floods [{ORIGINAL}].",
                            "kind": "answer", "truncated": False}
    assert [(p["passage"], p["text"]) for p in body["passages"]] == [(ORIGINAL, FLOOD)]
    # The summary was never the source: the citation is the stored passage.
    assert [(c.record_id, c.page, c.quote) for c in result.citations] == [(1, 4, FLOOD)]
    assert result.answer == "Earlier it predicted 87 floods [1]."
    assert ("recover_turn", 2) in corpus.calls


def test_recovery_does_not_make_an_excluded_paper_citable_again():
    corpus = corpus_with_turn()
    answer = f"Earlier it predicted 87 floods [{ORIGINAL}]."
    provider = recording(tools(call("c1", "recover_turn", turn=2)), reply(answer), reply(answer), reply(answer))
    result = ask(provider, corpus, state=EXCLUDED)
    assert result.citations == ()
    # The recovered Turn still states the number, so only the excluded citation goes.
    assert result.answer == "Earlier it predicted 87 floods."


def test_a_number_nobody_recovered_or_read_is_marked_as_not_established():
    corpus = corpus_with_turn()
    invented = reply(f"It predicted 99 floods [{ORIGINAL}].")
    provider = recording(tools(call("c1", "recover_turn", turn=2)), invented, invented, invented)
    result = ask(provider, corpus)
    assert result.answer == f"It predicted 99 floods [1]. {QUALIFIER}"


def test_a_turn_the_reader_may_not_recover_is_the_same_refusal_as_a_missing_one():
    corpus = corpus_with_turn()
    del corpus.turns[2]
    provider = recording(tools(call("c1", "recover_turn", turn=2), call("c2", "recover_turn", turn=99)),
                         reply("I can't confirm that detail."))
    result = ask(provider, corpus)

    first, second = tool_messages(provider.requests[1])
    assert first == second
    assert first["status"] == "unavailable" and first["reason"] == "unknown_turn"
    assert result.citations == ()


@pytest.mark.parametrize("arguments", [{"turn": "2"}, {"turn": True}, {}, {"turn": 2, "reader": 5}])
def test_recovery_arguments_are_strictly_the_turn_number(arguments):
    corpus = corpus_with_turn()
    provider = recording(tools(call("c1", "recover_turn", **arguments)), reply("Done."))
    ask(provider, corpus)
    assert tool_messages(provider.requests[1]) == [{"error": "invalid_arguments"}]
    assert not [c for c in corpus.calls if c[0] == "recover_turn"]


def test_a_recovered_turn_survives_a_checkpoint_round_trip():
    inv = Investigation(None, recovery=True)
    inv.recovered[2] = "It predicted 87 floods."
    restored = Investigation(None, recovery=True)
    checkpoint._restore_investigation(restored, json.loads(json.dumps(checkpoint._investigation(inv))))
    assert restored.recovered == {2: "It predicted 87 floods."}


# --- Revocation ----------------------------------------------------------------------

def test_a_handoff_whose_source_was_revoked_is_not_sent():
    corpus = corpus_with_turn()
    corpus.handoff_reason = "stale"
    provider = recording(reply("From the summary alone."))
    with pytest.raises(Unavailable) as refused:
        ask(provider, corpus)
    assert refused.value.code == "source_changed"
    # Nothing carrying the summary reached the model.
    assert provider.requests == []
    assert corpus.handoff_checks == [((1, 2, 3), ("11:e1",))]


def test_a_handoff_revoked_after_the_last_send_is_not_delivered():
    corpus = corpus_with_turn()
    corpus.handoff_reason = lambda n: None if n == 1 else "stale"
    provider = recording(reply("The second paper is the pond study."))
    with pytest.raises(Unavailable) as refused:
        ask(provider, corpus)
    assert refused.value.code == "source_changed"
    assert len(provider.requests) == 1


def test_a_run_that_ended_stops_rather_than_continue_on_a_handoff():
    corpus = corpus_with_turn()
    corpus.handoff_reason = "run_ended"
    with pytest.raises(Unavailable) as refused:
        ask(recording(reply("x")), corpus)
    assert refused.value.code == "run_ended"


def test_without_a_handoff_nothing_is_rechecked():
    corpus = corpus_with_turn()
    corpus.handoff_reason = "stale"
    run(agent4(recording(reply("A direct answer."))).answer("Hello?", corpus, context()))
    assert corpus.handoff_checks == []


# --- Context status --------------------------------------------------------------------

def event(name, **data):
    return {"name": name, "data": data}


def test_compaction_state_is_published_as_outcomes_and_counts_only():
    shown = public.progress([
        event("compaction", outcome="kept", reason="summary_exceeds_context"),
        event("compaction", outcome="compacted", revision=3, turns=2, exchanges=1),
        event("compaction", outcome="compacted", revision=4, turns=1, exchanges=0),
        event("compaction", outcome="kept", reason="allowance"),
    ])["compaction"]
    assert shown == {"compactions": 2, "turns_compacted": 3, "last": "kept"}


def test_no_compaction_is_null_and_malformed_events_are_ignored():
    assert public.progress([])["compaction"] is None
    assert public.progress([event("compaction", outcome="surprise", turns=2),
                            event("compaction", outcome="compacted", turns="2"),
                            event("compaction", outcome="compacted", turns=-1)])["compaction"] is None


def test_the_run_projection_carries_it_beside_the_context_estimate():
    snapshot = {k: None for k in ("id", "conversation_id", "state", "question", "base_revision", "version",
                                  "turn_id", "depth", "awaiting_reader", "created_at", "finished_at")}
    snapshot["events"] = [event("context", used_tokens=10, capacity_tokens=100),
                          event("compaction", outcome="compacted", revision=1, turns=2, exchanges=0)]
    shown = public.run(snapshot)
    assert shown["context"] == {"estimated": True, "used_tokens": 10, "capacity_tokens": 100}
    assert shown["compaction"] == {"compactions": 1, "turns_compacted": 2, "last": "compacted"}
    # A run whose sources are gone publishes neither.
    gone = public.run({**snapshot, "sources_available": False})
    assert gone["compaction"] is None and gone["context"] is None
