"""Long-context continuity across compactions and incompatible native state (IR-736, ADR-049 §19, §20).

Cross-feature integration over the executor with the recording provider and
the in-memory research stand-ins of IR-728, IR-733 and IR-735. The feature
tests are IR-732 to IR-735's; this proves they hold together. A deterministic
provider proves contracts, never a vendor's summary quality or paid capacity.
PostgreSQL, fencing and the restricted runtime role are
`test_ai_runtime_long_context_db.py`'s.
"""

import dataclasses
import json

import pytest

from .test_ai_runtime_agent_loop_contract import (
    ALLOWANCE, PIN, PROFILES, call, context, handle, models, recording, reply, run, tools,
)
from .test_ai_runtime_checkpoint_contract import Killed, first_worker, replacement, saving
from .test_ai_runtime_compaction_contract import EAGER, Handoffs, handoff_of
from .test_ai_runtime_context_contract import MILLION, RESERVES
from .test_ai_runtime_manuscript_contract import PAPER, Manuscript, at
from ai.agent import executor as executing
from ai.agent import tools as toolset
from ai.agent.compaction import Compaction
from ai.agent.context import CONTEXT_EXHAUSTED, Capacity
from ai.agent.executor import AgentExecutor
from ai.infrastructure.recording_adapter import RecordingAgentProvider
from ai.runs.service import RunService
from ai.runs.store import shown_facts
from ai.research.tools import RecoveredTurn
from ai.runs.executor import PriorTurn, Unavailable

PIN_4 = dataclasses.replace(PIN, prompt_version="agent-research-4", tool_version="research-4")


# --- A changed prefix or tool schema makes saved opaque state incompatible ------------

def reasoning_sent(provider):
    return "reasoning_details" in json.dumps(provider.requests)


def test_an_unchanged_prefix_and_schema_resume_with_the_saved_artifact():
    saved, _ = first_worker()
    _, provider, corpus = replacement(saved, reply("Done."))
    assert reasoning_sent(provider)
    assert ("recovery", {"outcome": "resumed", "step": 1}) in corpus.events


def test_changed_instructions_under_the_same_pin_rebuild_without_the_saved_artifact(monkeypatch):
    saved, _ = first_worker()
    key = (PIN.prompt_version, PIN.tool_version)
    monkeypatch.setitem(executing.PROMPTS, key, executing.PROMPTS[key] + " A new rule.")
    _, provider, corpus = replacement(saved, reply("A general answer."))

    assert [m["role"] for m in provider.requests[0]["messages"]] == ["system", "user"]
    assert not reasoning_sent(provider)
    assert corpus.reauthorized == []
    assert ("recovery", {"outcome": "rebuilt", "reason": "incompatible", "step": 1}) in corpus.events


def test_a_changed_tool_schema_under_the_same_pin_rebuilds_without_the_saved_artifact(monkeypatch):
    saved, _ = first_worker()
    first, *rest = toolset.RESEARCH
    changed = dataclasses.replace(first, parameters={**first.parameters, "additionalProperties": True})
    monkeypatch.setattr(toolset, "RESEARCH", (changed, *rest))
    _, provider, corpus = replacement(saved, reply("A general answer."))

    assert not reasoning_sent(provider)
    assert ("recovery", {"outcome": "rebuilt", "reason": "incompatible", "step": 1}) in corpus.events
    # What was spent and the steps taken are not renewed by the rebuild.
    assert [m["step"] for m in models(corpus)] == [2]


# --- Evicted text is not still shown ------------------------------------------------------

MIDDLE = "The middle finding: soil moisture rose by 42 percent after the first monsoon week."
REVISED = "The closing correction: the 42 percent rise fell to 17 percent once the dry-season baseline applied."


def paper_body():
    body = [f"Section {i} reviews earlier monsoon work and the siting of rain gauges." for i in range(1, 31)]
    body[14] = MIDDLE
    body[29] = REVISED
    return body


def summary_of(*findings, goal="Understand the long monsoon study."):
    return reply(json.dumps({"goal": goal, "preferences": [], "findings": list(findings),
                             "limitations": ["Figures and formulas were not interpreted."]}))


def investigate(provider, handoffs, corpus=None, *, question="What does the long monsoon study find?", **kw):
    corpus = corpus or Manuscript(paper_body())
    agent = AgentExecutor(provider, PIN_4, RESERVES, profiles=PROFILES, compaction=EAGER)
    return run(agent.answer(question, corpus, context(commit_handoff=handoffs, **kw))), corpus


def coverage(result):
    [fact] = [f for f in result.facts if f["kind"] == "reading_coverage"]
    return fact


def test_passages_read_before_a_compaction_are_reported_as_no_longer_in_the_models_context():
    handoffs = Handoffs()
    provider = recording(
        tools(call("r", "read_manuscript", paper=PAPER)),
        tools(call("s", "search", query="flood")),
        summary_of({"text": "Soil moisture rose 42 percent.", "passages": [at(15)]}),
        reply(f"Soil moisture first rose by 42 percent [{at(15)}]. Only a summary of the paper remained in "
              f"context when this was written, so I cannot confirm the corrected figure."),
    )
    result, _ = investigate(provider, handoffs)

    # The exchange that held the paper's text is gone from the final request.
    final = provider.requests[-1]
    assert MIDDLE not in json.dumps(final["messages"])
    assert [m["phase"] for m in models(_)] == ["gather", "gather", "compact", "gather"]
    # It was read whole, but nothing of it is claimed to be shown any more.
    assert coverage(result)["read"] == 30 and coverage(result)["complete"] is True
    assert coverage(result)["not_in_context"] == 30
    # The evidence binding survives: the citation is still the canonical passage.
    [citation] = result.citations
    assert (citation.quote, citation.page, citation.revision) == (MIDDLE, 5, "77:e7")


# --- A Conversation across repeated compactions ------------------------------------------

FLOOD_HANDLE = handle("R", 1)
Q1 = "What does the long monsoon study find, and which flood paper can we drop?"
Q3 = "Was the first figure you gave me final? Quote it exactly and say what the paper later says."


class Thread:
    """What the store keeps for one Conversation between runs: Turns, state and the newest handoff.

    A claim carries the Turns after the handoff's `through_ordinal`, the
    Conversation's state and the handoff; every Turn stays stored.
    """

    def __init__(self, corpus=None):
        self.corpus = corpus or Manuscript(paper_body())
        self.turns: list[PriorTurn] = []
        self.state = None
        self.handoffs = Handoffs()
        self.agents: list[AgentExecutor] = []

    @property
    def handoff(self):
        if not self.handoffs.committed:
            return None
        newest = self.handoffs.committed[-1]
        return {"revision": len(self.handoffs.committed), "through_ordinal": newest.through_ordinal,
                "body": newest.body}

    def context(self, **kw):
        through = (self.handoff or {}).get("through_ordinal", 0)
        carried = tuple(t for t in self.turns if t.ordinal > through)
        return context(prior=carried, state=self.state, handoff=self.handoff, commit_handoff=self.handoffs, **kw)

    def agent(self, provider, compaction, pin=PIN_4):
        agent = AgentExecutor(provider, pin, RESERVES, profiles=PROFILES, compaction=compaction)
        self.agents.append(agent)
        return agent

    def ask(self, provider, question, *, compaction=EAGER, **kw):
        result = run(self.agent(provider, compaction).answer(question, self.corpus, self.context(**kw)))
        self.turns.append(PriorTurn(question, result.answer, "answer", ordinal=len(self.turns) + 1))
        self.state = result.state
        return result

    def compact(self, provider, *, compaction=EAGER, **kw):
        return run(self.agent(provider, compaction).compact(self.corpus, self.context(**kw)))


def rule(keep):
    return Compaction(threshold_tokens=1, summary_tokens=400, keep_exchanges=keep, max_attempts=2)


def first_turn(thread):
    """Turn 1: the whole paper is read, an automatic compaction condenses that read, the middle is cited."""
    provider = recording(
        tools(call("r", "read_manuscript", paper=PAPER)),
        tools(call("s", "search", query="flood"), call("f", "update_focus", excluded=[FLOOD_HANDLE])),
        summary_of({"text": "Soil moisture rose 42 percent.", "passages": [at(15)]}),
        reply(f"Soil moisture rose by 42 percent after the first monsoon week [{at(15)}]. "
              "I have set the flood paper aside."),
    )
    return thread.ask(provider, Q1), provider


def second_turn(thread):
    return thread.ask(recording(reply("A monsoon is a seasonal shift in prevailing winds.")),
                      "Thanks. In a sentence, what is a monsoon?")


def manual_compaction(thread):
    provider = recording(summary_of(
        {"text": "The first answer put the middle finding at 42 percent.", "turns": [1]},
        goal="Understand the long monsoon study, leaving the flood paper out."))
    return thread.compact(provider, compaction=rule(1)), provider


def original_turn_one(thread):
    """What recover_turn would return for Turn 1: the stored words, with this run's passage handle."""
    first = thread.turns[0]
    answer = first.answer.replace("[1]", f"[{at(15)}]")
    thread.corpus.turns[1] = (RecoveredTurn(1, first.question, answer, "answer"), [thread.corpus.long[14]])


def contradiction_turn(thread):
    original_turn_one(thread)
    provider = recording(
        tools(call("t", "recover_turn", turn=1)),
        tools(call("o", "open_passage", passage=at(30))),
        summary_of({"text": "The first figure was later corrected.", "passages": [at(30)], "turns": [1]}),
        reply(f"Your first answer gave 42 percent [{at(15)}], but the paper's closing section corrects "
              f"it: the rise fell to 17 percent once the dry-season baseline applied [{at(30)}]."),
    )
    return thread.ask(provider, Q3, compaction=rule(2)), provider


def test_two_automatic_compactions_and_a_manual_one_keep_the_task_the_order_and_the_exclusion():
    thread = Thread()
    first, _ = first_turn(thread)
    assert first.state == {"shown": [7], "selected": [], "excluded": [1]}
    second_turn(thread)

    compacted, provider = manual_compaction(thread)
    assert (compacted.revision, compacted.turns) == (2, 1)
    summary = json.dumps(provider.requests[0]["messages"])
    # The summary is written from the older Turn; the newest stays whole.
    assert Q1 in summary and "what is a monsoon" not in summary

    third, provider = contradiction_turn(thread)
    # Reopened: the run opens with the handoff and only the Turn after it, never the compacted Turn's words.
    opening = provider.requests[0]["messages"]
    handoff = handoff_of(opening[1])
    assert handoff["derived"] is True and handoff["turns"] == [1]
    assert [(s["position"], s["title"]) for s in handoff["shown"]] == [(1, "Long monsoon study")]
    assert handoff["excluded"] == [FLOOD_HANDLE]
    assert all(f["passages"] == [] for f in handoff["findings"])
    assert Q1 not in json.dumps(opening) and "In a sentence, what is a monsoon?" in json.dumps(opening)

    # The exact old value came from the original Turn, and the late correction from the paper.
    recovered = next(json.loads(m["content"]) for m in provider.requests[1]["messages"] if m["role"] == "tool")
    assert recovered["turn"]["answer"].startswith("Soil moisture rose by 42 percent")
    assert [(c.page, c.quote) for c in third.citations] == [(5, MIDDLE), (10, REVISED)]
    assert third.answer.count("[") == 2 and third.answer.endswith("applied [2].")
    # The third compaction built on the second: every compacted Turn is still named.
    newest = thread.handoffs.committed[-1]
    assert (newest.through_ordinal, newest.turns) == (2, (1, 2))
    assert newest.body["excluded"] == [1] and newest.body["shown"] == [7]
    # Compaction never removed an original.
    assert [t.ordinal for t in thread.turns] == [1, 2, 3]
    assert thread.turns[0].question == Q1


# --- Incompatible native state after compactions: rebuild portably or stop -----------------

class Library(Manuscript):
    """The long paper's corpus where every recovered handle is still readable."""

    async def reauthorize(self, handles, counted=(), turns=()):
        return None


def conversation_with_handoff():
    thread = Thread(Library(paper_body()))
    first_turn(thread)
    second_turn(thread)
    manual_compaction(thread)
    original_turn_one(thread)
    return thread


def killed_after_recovery(thread):
    """A worker recovers Turn 1, saves that step with a signed artifact, then dies."""
    saved, save = saving()
    provider = recording(
        tools(call("t", "recover_turn", turn=1), reasoning_details={"sig": "opaque-9"}), Killed("worker killed"))
    with pytest.raises(Killed):
        run(thread.agent(provider, rule(2)).answer(Q3, thread.corpus, thread.context(save=save)))
    assert [s["step"] for s in saved] == [1]
    return saved[-1]


def takeover(thread, saved, *responses):
    provider = recording(*responses)
    result = run(thread.agent(provider, rule(2)).answer(Q3, thread.corpus, thread.context(checkpoint=saved)))
    return result, provider


RESUMED_SUMMARY = summary_of({"text": "The first figure was later corrected.", "turns": [1]})
ANSWER = (f"Your first answer gave 42 percent [{at(15)}], but the closing section corrects it to 17 percent "
          f"[{at(30)}].")


def test_a_takeover_after_a_manual_compaction_resumes_the_saved_step_with_its_artifact():
    thread = conversation_with_handoff()
    saved = killed_after_recovery(thread)
    thread.corpus.events.clear()
    _, provider = takeover(thread, saved, tools(call("o", "open_passage", passage=at(30))), RESUMED_SUMMARY,
                           reply(ANSWER))

    assert reasoning_sent(provider)
    assert ("recovery", {"outcome": "resumed", "step": 1}) in thread.corpus.events


@pytest.mark.parametrize("change", ["instructions", "tool_schema", "tool_version"])
def test_a_takeover_under_a_changed_prefix_or_schema_continues_portably_from_the_handoff(monkeypatch, change):
    thread = conversation_with_handoff()
    saved = killed_after_recovery(thread)
    thread.corpus.events.clear()
    if change == "instructions":
        key = (PIN_4.prompt_version, PIN_4.tool_version)
        monkeypatch.setitem(executing.PROMPTS, key, executing.PROMPTS[key] + " A new rule.")
    elif change == "tool_schema":
        first, *rest = toolset.RECOVERY
        monkeypatch.setattr(toolset, "RECOVERY",
                            (dataclasses.replace(first, description=first.description + " Changed."), *rest))
    else:
        # Another pin entirely: this is research-3, which offers no recover_turn.
        monkeypatch.setattr(thread, "agent", lambda provider, compaction, pin=PIN_4: AgentExecutor(
            provider, dataclasses.replace(PIN_4, prompt_version="agent-research-3", tool_version="research-3"),
            RESERVES, profiles=PROFILES, compaction=compaction))
    result, provider = takeover(thread, saved, tools(call("o", "open_passage", passage=at(30))),
                                tools(call("p", "open_passage", passage=at(15))), RESUMED_SUMMARY, reply(ANSWER))

    # Rebuilt from the originals the run may still read: the handoff, the later Turn and the question.
    opening = provider.requests[0]["messages"]
    assert [m["role"] for m in opening] == ["system", "user", "user", "assistant", "user", "user"]
    assert handoff_of(opening[1])["turns"] == [1]
    assert opening[-1] == {"role": "user", "content": Q3}
    assert not reasoning_sent(provider)
    assert ("recovery", {"outcome": "rebuilt", "reason": "incompatible", "step": 1}) in thread.corpus.events
    # The rebuild renewed nothing: the step it had taken stays taken.
    assert [m["step"] for m in models(thread.corpus) if m["phase"] == "gather"] == [2, 3, 4]
    # And the answer still binds to the canonical passages.
    assert [(c.page, c.quote) for c in result.citations] == [(5, MIDDLE), (10, REVISED)]


def test_a_withdrawn_capability_stops_before_anything_is_sent():
    thread = conversation_with_handoff()
    provider = recording(reply("Never sent."))
    provider.capabilities = frozenset()
    with pytest.raises(Unavailable) as refused:
        run(thread.agent(provider, rule(2)).answer(Q3, thread.corpus, thread.context()))
    assert refused.value.code == "unsupported_pin" and provider.requests == []


def test_without_native_support_the_portable_path_still_compacts_and_continues():
    portable = dataclasses.replace(PIN_4, requires=())
    thread = Thread()
    provider = recording(
        tools(call("r", "read_manuscript", paper=PAPER)), tools(call("s", "search", query="flood")),
        summary_of({"text": "Soil moisture rose 42 percent.", "passages": [at(15)]}),
        reply(f"Soil moisture rose by 42 percent after the first monsoon week [{at(15)}]."))
    provider.capabilities = frozenset()
    run(thread.agent(provider, EAGER, pin=portable).answer(Q1, thread.corpus, thread.context()))

    [committed] = thread.handoffs.committed
    assert committed.body["findings"][0]["passages"] == [at(15)]
    assert not reasoning_sent(provider)


# --- A model change is explicit, reauthorized and fitted; never silent ------------------

SMALL = Capacity(context_tokens=3_000, max_output_tokens=600, max_reasoning_tokens=None,
                 max_request_bytes=256_000, min_bytes_per_token=1.0, framing_tokens_per_message=4)
FOLLOW_UP = "What did the first answer say about the middle of the paper?"
NO_FIGURES = "The closing section corrects the earlier finding, so I would reread it before quoting."


def other_model(name, capacity, *responses):
    provider = RecordingAgentProvider(responses=list(responses), models=(name,), capabilities=("continuation",),
                                      capacities={name: capacity} if capacity else {})
    provider.paid = False
    return provider, dataclasses.replace(PIN_4, model=name)


def follow_up_on(thread, provider, pin):
    return run(thread.agent(provider, rule(2), pin=pin).answer(FOLLOW_UP, thread.corpus, thread.context()))


def test_a_model_whose_window_cannot_hold_the_conversation_refuses_before_sending():
    thread = conversation_with_handoff()
    provider, pin = other_model("small-model", SMALL, reply("Never sent."))
    with pytest.raises(Unavailable) as refused:
        follow_up_on(thread, provider, pin)
    assert refused.value.code == CONTEXT_EXHAUSTED and provider.requests == []


def test_a_model_with_no_verified_capacity_is_not_used():
    thread = conversation_with_handoff()
    provider, pin = other_model("new-model", None, reply("Never sent."))
    with pytest.raises(Unavailable) as refused:
        follow_up_on(thread, provider, pin)
    assert refused.value.code == "unsupported_pin" and provider.requests == []


def test_a_model_with_verified_capacity_continues_from_the_handoff_after_reauthorization():
    thread = conversation_with_handoff()
    provider, pin = other_model("large-model", MILLION, reply(NO_FIGURES))
    thread.corpus.handoff_checks.clear()
    result = follow_up_on(thread, provider, pin)

    [request] = provider.requests
    assert request["model"] == "large-model"
    # The summary is portable text and travels; no artifact signed for another model does.
    assert handoff_of(request["messages"][1])["turns"] == [1] and "reasoning_details" not in json.dumps(request)
    # Its Turns and sources were rechecked under the reader's access before it was sent.
    assert thread.corpus.handoff_checks[0] == ((1,), ("11:e1", "77:e7"))
    assert result.answer == NO_FIGURES


def test_a_run_pinned_to_one_model_is_not_answered_by_a_worker_serving_another():
    pinned_to = RunService(None, None, AgentExecutor(recording(), PIN_4, RESERVES, profiles=PROFILES))
    pinned = pinned_to.pinned()
    smaller = AgentExecutor(other_model("small-model", SMALL)[0], other_model("small-model", SMALL)[1], RESERVES,
                            profiles=PROFILES)
    other = RunService(None, None, smaller)

    assert pinned_to._executor_for(pinned) is pinned_to.executor
    assert other._executor_for(pinned) is None

    failed = []

    class Store:
        async def fail(self, run_id, fence, reason):
            failed.append((run_id, reason))

    other.store = Store()
    claim = type("Claim", (), {"run_id": "run-1", "fence": 1, "pinned": pinned})()
    run(other.execute(claim))
    # Ended safely, with nothing sent to the other model.
    assert failed == [("run-1", "unavailable")]


# --- Atomic revision and the original allowance ---------------------------------------------

def test_a_handoff_the_store_refuses_leaves_the_text_in_front_of_the_model_and_the_next_run_whole():
    thread = Thread()
    thread.handoffs = Handoffs("stale")
    first, provider = first_turn(thread)

    # The refused summary changed nothing: the paper's text is still in the final request.
    assert MIDDLE in json.dumps(provider.requests[-1]["messages"])
    assert ("compaction", {"outcome": "kept", "reason": "stale"}) in thread.corpus.events
    assert "not_in_context" not in coverage(first)
    assert thread.handoff is None
    second_turn(thread)
    # With nothing active, the next run carries the earlier Turn whole.
    assert thread.turns[0].question == Q1 and thread.context().prior == tuple(thread.turns)


def test_compaction_inside_a_tight_allowance_is_skipped_never_given_a_new_one():
    thread = Thread()
    tight = {**ALLOWANCE, "max_output_tokens": 1_000}
    provider = recording(
        tools(call("r", "read_manuscript", paper=PAPER)),
        tools(call("s", "search", query="flood")),
        reply(f"Soil moisture rose by 42 percent after the first monsoon week [{at(15)}]."),
    )
    result = run(thread.agent(provider, EAGER).answer(Q1, thread.corpus, thread.context(allowance=tight)))

    assert ("compaction", {"outcome": "kept", "reason": "allowance"}) in thread.corpus.events
    assert [m["phase"] for m in models(thread.corpus)] == ["gather", "gather", "gather"]
    assert thread.handoff is None and result.citations


# --- The complete request fit every time ------------------------------------------------------

def every_request_fit(thread):
    """Each request sent fit its model's verified capacity with every reserve held back."""
    statuses = [s for a in thread.agents for sender in (a.sender, a.summarizer) if sender for s in sender.statuses]
    assert statuses
    return all(s.outcome == "fits" and s.request_bytes <= s.max_request_bytes
               and s.occupancy_tokens + s.reserved_tokens <= s.context_tokens for s in statuses)


def test_every_request_across_the_compactions_fit_the_verified_capacity():
    thread = Thread()
    first_turn(thread)
    second_turn(thread)
    manual_compaction(thread)
    contradiction_turn(thread)
    assert every_request_fit(thread)


def test_a_reopened_turn_says_how_much_was_read_but_not_in_context_only_when_it_happened():
    thread = Thread()
    compacted, _ = first_turn(thread)
    [shown] = [f for f in shown_facts(compacted.facts) if f["kind"] == "reading_coverage"]
    assert shown["read"] == 30 and shown["not_in_context"] == 30
    assert shown["visual_interpretation"] is False and shown["exhaustive"] is False

    plain = {"kind": "reading_coverage", "title": "T", "passages": 3, "read": 3, "complete": True, "pages": 1,
             "pages_no_passage_starts_on": 0, "formula_passages": 0, "caption_passages": 0}
    assert "not_in_context" not in shown_facts([plain])[0]
