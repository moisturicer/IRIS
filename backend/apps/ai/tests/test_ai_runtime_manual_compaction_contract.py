"""Compact a Conversation on the reader's request (IR-754, ADR-049 §19).

The manual action is its own run: the executor with the recording provider and
IR-728's in-memory research stand-in. It must reuse IR-734's summarizer, handoff
and commit rather than add a second one, ask one summary and no answer, and
leave the preceding context alone whenever the handoff is not committed. A
deterministic provider proves the contract, never a vendor's summary quality.
PostgreSQL, fencing and the run's admission are `test_ai_runtime_manual_compaction_db.py`'s.
"""

import dataclasses
import json

import pytest

from .test_ai_runtime_agent_loop_contract import (
    ALLOWANCE, FLOOD, PIN, PROFILES, Corpus, agent, call, context, handle, models, run, tools,
)
from .test_ai_runtime_context_contract import RESERVES
from .test_ai_runtime_compaction_contract import (
    EAGER, PRIOR, STATE, SUMMARY, Handoffs, reply, windowed,
)
from ai.agent.compaction import NOTE
from ai.agent.context import Capacity
from ai.agent.executor import COMPACT_REQUEST, AgentExecutor
from ai.research.tools import RecoveredTurn
from ai.runs.executor import Compacted, PriorTurn, Unavailable

#: A threshold no history reaches: manual compaction does not wait for one.
LATE = EAGER.__class__(threshold_tokens=7_000, summary_tokens=400, keep_exchanges=1, max_attempts=2)


#: research-4 offers every tool, which the small fixture window above cannot hold beside a summary.
ROOMY = Capacity(context_tokens=60_000, max_output_tokens=2_000, max_reasoning_tokens=None,
                 max_request_bytes=512_000, min_bytes_per_token=1.0, framing_tokens_per_message=4)


def roomy(*responses):
    provider = windowed(*responses)
    provider.capacities = {"scripted-model": ROOMY}
    return provider


def compact(provider, handoffs, *, compaction=LATE, prior=PRIOR, **kw):
    corpus = Corpus()
    ctx = context(prior=prior, state=STATE, commit_handoff=handoffs, **kw)
    return run(agent(provider, compaction=compaction).compact(corpus, ctx)), corpus


# --- The same mechanism, asked for now -----------------------------------------

def test_older_turns_compact_below_the_threshold_into_the_same_handoff():
    handoffs = Handoffs()
    provider = windowed(reply(json.dumps(SUMMARY)))
    result, corpus = compact(provider, handoffs)

    # One summary of the AGENT's, research closed, and no answer asked for.
    [summary] = provider.requests
    assert summary["tool_choice"] == "none" and summary["messages"][-1] == {"role": "user", "content": NOTE}
    assert [m["phase"] for m in models(corpus)] == ["compact"]
    # The only task it serves is a neutral request, never a question the reader did not ask.
    assert {"role": "user", "content": COMPACT_REQUEST} in summary["messages"]

    [committed] = handoffs.committed
    assert (committed.through_ordinal, committed.turns) == (2, (1, 2))
    # What the application records is what IR-734's automatic path records.
    assert committed.body["shown"] == [1, 2] and committed.body["excluded"] == [1]
    assert committed.body["goal"] == SUMMARY["goal"]
    assert result == Compacted(revision=1, turns=2, reported_units=80)
    assert ("compaction", {"outcome": "compacted", "revision": 1, "turns": 2, "exchanges": 0}) in corpus.events


def test_the_summary_is_written_from_the_older_turns_and_keeps_the_newest():
    provider = windowed(reply(json.dumps(SUMMARY)))
    compact(provider, Handoffs())
    text = json.dumps(provider.requests[0]["messages"])
    assert "Which papers study water?" in text and "Leave out the flood one." in text
    # The newest exchange stays whole in the history the next run opens with, so it is not summarized.
    assert "What does the pond paper sample?" not in text


def test_a_handoff_from_an_earlier_compaction_is_carried_into_the_next():
    handoffs = Handoffs()
    first = windowed(reply(json.dumps(SUMMARY)))
    compact(first, handoffs)
    [earlier] = handoffs.committed
    later = windowed(reply(json.dumps({**SUMMARY, "goal": "Compare the pond papers."})))
    ctx = context(prior=(PriorTurn("Which pond?", "The brackish one.", "answer", ordinal=4),
                         PriorTurn("And its depth?", "One metre.", "answer", ordinal=5)),
                  state=STATE, commit_handoff=handoffs,
                  handoff={"revision": 1, "through_ordinal": 2, "body": earlier.body})
    result = run(agent(later, compaction=LATE).compact(Corpus(), ctx))
    assert result.revision == 2
    assert handoffs.committed[1].body["turns"] == [1, 2, 4]


# --- Nothing to do is not a failure --------------------------------------------

def test_a_conversation_with_nothing_older_than_the_newest_exchange_sends_nothing():
    provider = windowed()
    result, corpus = compact(provider, Handoffs(), prior=PRIOR[:1])
    assert provider.requests == [] and models(corpus) == []
    assert result == Compacted(revision=None, turns=0, reported_units=0)
    assert ("compaction", {"outcome": "kept", "reason": "nothing_to_compact"}) in corpus.events


# --- Failure and staleness preserve the preceding context ----------------------

@pytest.mark.parametrize("summary", [reply("not json at all"), reply(json.dumps({"goal": ""})),
                                     reply("", finish="length")])
def test_a_failed_summary_commits_nothing_and_ends_unavailable(summary):
    handoffs = Handoffs()
    provider = windowed(summary)
    with pytest.raises(Unavailable) as refused:
        compact(provider, handoffs)
    assert refused.value.code == "invalid_summary" and handoffs.committed == []
    assert len(provider.requests) == 1


def test_a_handoff_the_store_calls_stale_is_not_activated():
    handoffs = Handoffs("stale")
    with pytest.raises(Unavailable) as refused:
        compact(windowed(reply(json.dumps(SUMMARY))), handoffs)
    assert refused.value.code == "stale" and handoffs.committed == []


def test_a_fenced_worker_stops():
    with pytest.raises(Unavailable) as refused:
        compact(windowed(reply(json.dumps(SUMMARY))), Handoffs("fenced"))
    assert refused.value.code == "run_ended"


def test_a_stopped_run_sends_no_summary():
    provider = windowed(reply(json.dumps(SUMMARY)))
    corpus = Corpus()
    corpus.ended = True
    with pytest.raises(Unavailable) as refused:
        run(agent(provider, compaction=LATE).compact(
            corpus, context(prior=PRIOR, state=STATE, commit_handoff=Handoffs())))
    assert refused.value.code == "run_ended" and provider.requests == []


# --- One bounded attempt, inside the run's own allowance -----------------------

def test_a_replacement_worker_does_not_summarize_again_after_a_failed_attempt():
    provider = windowed(reply(json.dumps(SUMMARY)))
    with pytest.raises(Unavailable) as refused:
        compact(provider, Handoffs(), compactions=1)
    assert refused.value.code == "attempts_exhausted" and provider.requests == []


def test_a_replacement_worker_finishes_a_handoff_an_earlier_fence_committed():
    provider = windowed()
    handoffs = Handoffs()
    result, corpus = compact(provider, handoffs, compactions=1, committed=frozenset({3}))
    assert result.revision == 3 and provider.requests == [] and handoffs.committed == []
    assert ("compaction", {"outcome": "compacted", "revision": 3, "turns": 0, "exchanges": 0}) in corpus.events


def test_the_run_pays_for_its_summary_alone_from_its_own_allowance():
    # Enough for one summary, not for a final answer and a repair beside it: no answer is owed here.
    tight = {**ALLOWANCE, "max_output_tokens": 500}
    result, _ = compact(windowed(reply(json.dumps(SUMMARY))), Handoffs(), allowance=tight)
    assert result.revision == 1


def test_a_summary_the_allowance_cannot_pay_for_is_not_sent():
    broke = {**ALLOWANCE, "max_output_tokens": 100}
    provider = windowed(reply(json.dumps(SUMMARY)))
    with pytest.raises(Unavailable) as refused:
        compact(provider, Handoffs(), allowance=broke)
    assert refused.value.code == "allowance" and provider.requests == []


def test_spending_already_charged_to_the_run_is_not_renewed():
    spent = {"input_tokens": ALLOWANCE["max_input_tokens"], "output_tokens": 0, "attempts": 1}
    provider = windowed(reply(json.dumps(SUMMARY)))
    with pytest.raises(Unavailable) as refused:
        compact(provider, Handoffs(), spent=spent)
    assert refused.value.code == "allowance" and provider.requests == []


# --- Only a configured, supported, admitted rule compacts ----------------------

def test_without_a_compaction_rule_nothing_is_compacted():
    provider = windowed(reply(json.dumps(SUMMARY)))
    with pytest.raises(Unavailable) as refused:
        compact(provider, Handoffs(), compaction=None)
    assert refused.value.code == "unsupported_pin" and provider.requests == []


def test_a_run_without_a_way_to_commit_cannot_compact():
    provider = windowed(reply(json.dumps(SUMMARY)))
    with pytest.raises(Unavailable) as refused:
        compact(provider, None)
    assert refused.value.code == "unsupported_pin" and provider.requests == []


def test_a_paid_provider_that_is_not_admitted_is_never_reached():
    provider = windowed(reply(json.dumps(SUMMARY)))
    provider.paid = True
    with pytest.raises(Unavailable) as refused:
        compact(provider, Handoffs())
    assert refused.value.code == "not_admitted" and provider.requests == []


# --- Compact, then ask for an exact earlier detail -----------------------------

def test_after_a_manual_compaction_an_exact_detail_is_recovered_from_the_original_not_the_summary():
    pin = dataclasses.replace(PIN, prompt_version="agent-research-4", tool_version="research-4")
    original = handle("P", 1)
    prior = (
        PriorTurn("How many floods did the network predict?", f"It predicted 87 floods [{original}].", "answer",
                  ordinal=1),
        PriorTurn("Which papers study water?", "Two papers.", "answer", ordinal=2),
        PriorTurn("What does the pond paper sample?", "Brackish ponds, weekly.", "answer", ordinal=3),
    )
    state = {"shown": [1, 2], "selected": [], "excluded": []}
    # A summary that states a wrong number: it is never evidence for one.
    summary = {"goal": "Understand the water papers.", "preferences": [], "limitations": [],
               "findings": [{"text": "The network predicted 90 floods.", "turns": [1]}]}

    handoffs = Handoffs()
    compacting = AgentExecutor(roomy(reply(json.dumps(summary))), pin, RESERVES, profiles=PROFILES,
                               compaction=LATE)
    done = run(compacting.compact(Corpus(), context(prior=prior, state=state, commit_handoff=handoffs)))
    [committed] = handoffs.committed
    assert done.revision == 1 and committed.turns == (1, 2)

    # The next run opens with the handoff and only Turn 3; the original Turn 1 is recoverable, not carried.
    corpus = Corpus()
    corpus.turns[1] = (RecoveredTurn(1, prior[0].question, prior[0].answer, "answer"),
                       [corpus.papers[1][2]])
    provider = roomy(tools(call("r1", "recover_turn", turn=1)),
                     reply(f"Earlier it predicted 87 floods [{original}]."))
    asking = AgentExecutor(provider, pin, RESERVES, profiles=PROFILES)
    result = run(asking.answer("Exactly how many floods was it?", corpus, context(
        prior=prior[2:], state=state,
        handoff={"revision": 1, "through_ordinal": committed.through_ordinal, "body": committed.body})))

    first, second = provider.requests
    opening = json.dumps(first["messages"])
    assert "[IRIS compacted context]" in opening and "predicted 90 floods" in opening
    assert prior[0].answer not in opening and prior[0].question not in opening
    # The original comes back from the store, with a fresh handle for the passage it cited.
    [body] = [json.loads(m["content"]) for m in second["messages"] if m["role"] == "tool"]
    assert body["turn"]["answer"] == prior[0].answer and body["passages"][0]["text"] == FLOOD
    assert ("recover_turn", 1) in corpus.calls
    # The answer cites the stored passage and its number is the original's, not the summary's.
    assert [(c.record_id, c.quote) for c in result.citations] == [(1, FLOOD)]
    assert "87" in result.answer and "90" not in result.answer
