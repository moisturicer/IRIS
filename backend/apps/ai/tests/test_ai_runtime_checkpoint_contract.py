"""Resume an AGENT investigation from its completed steps (IR-724, ADR-049 §12, §14, §20).

The executor with the recording provider and the in-memory research
stand-in of IR-728's contract suite. A "worker" is one executor; it is
killed by an exception out of its provider, and its replacement is a fresh
executor given the last step the first saved. PostgreSQL, fencing and
independent processes are `test_ai_runtime_recovery_db.py`'s.
"""

import copy
import dataclasses
import json

import pytest

from .test_ai_runtime_agent_loop_contract import (
    ALLOWANCE, FLOOD, ORDINARY, PIN, Corpus, agent, call, context, handle, models, recording, reply, run, tools,
)
from ai.agent import checkpoint  # noqa: E402
from ai.agent.tools import Investigation  # noqa: E402
from ai.research.tools import Count  # noqa: E402
from ai.runs.executor import Unavailable  # noqa: E402

QUESTION = "Which paper predicts floods, and how?"
CITED = f"«Flood forecasting» predicted 87 floods from rainfall gauges [{handle('P', 1)}]."


class Killed(Exception):
    """The worker process died: nothing after this point ran."""


class Recovering(Corpus):
    """Reauthorizes a handle only while its paper is readable on the same source."""

    def __init__(self):
        super().__init__()
        self.reauthorized = []

    async def reauthorize(self, handles, counted=(), turns=()):
        self.reauthorized.append(list(handles))
        live = {h for rid, (_, _, passage) in self.papers.items() if rid not in self.replaced
                for h in (passage.handle, handle("R", rid))}
        return None if set(handles) <= live else "stale"


def saving():
    saved = []

    async def save(step, body):
        # As PostgreSQL would return it.
        saved.append({"step": step, "body": json.loads(json.dumps(body))})
        return True

    return saved, save


def first_worker():
    """Searches once, saves that step, then dies before its next turn returns."""
    saved, save = saving()
    provider = recording(
        tools(call("c-1", "search", query="flood rainfall"), reasoning_details={"sig": "opaque-1"}),
        Killed("worker killed"),
    )
    with pytest.raises(Killed):
        run(agent(provider).answer(QUESTION, Corpus(), context(save=save)))
    assert [s["step"] for s in saved] == [1]
    return saved[-1], provider


def replacement(saved, *responses, corpus=None, **kw):
    corpus = corpus or Recovering()
    provider = recording(*responses)
    result = run(agent(provider).answer(QUESTION, corpus, context(checkpoint=saved, **kw)))
    return result, provider, corpus


def test_a_replacement_continues_from_the_completed_step_with_its_call_group_and_evidence():
    saved, dead = first_worker()
    result, provider, corpus = replacement(saved, reply(CITED))

    # The restored Conversation is the one the first worker sent its second turn with.
    [resumed] = provider.requests
    assert resumed["messages"] == dead.requests[1]["messages"]
    assistant, result_message = resumed["messages"][-2:]
    assert assistant["tool_calls"][0]["id"] == "c-1"
    assert assistant["reasoning_details"] == {"sig": "opaque-1"}
    assert result_message["tool_call_id"] == "c-1" and FLOOD in result_message["content"]
    # Nothing was searched again: the evidence was reauthorized, and the cited
    # passage rechecked just before delivery, as any answer's is.
    assert set(corpus.reauthorized[0]) == {handle("P", 1), handle("R", 1)}
    assert corpus.calls == [("open_passage", handle("P", 1))]
    assert result.answer.endswith("[1].")
    [citation] = result.citations
    assert (citation.record_id, citation.quote, citation.revision) == (1, FLOOD, "11:e1")
    # Steps continue: the bounds were not renewed.
    assert ("recovery", {"outcome": "resumed", "step": 1}) in corpus.events
    assert [m["step"] for m in models(corpus)] == [2]


def test_what_was_spent_before_the_takeover_stays_spent():
    saved, _ = first_worker()
    # The ledger charged the dead worker's uncertain attempt at its reservation.
    spent = {"input_tokens": ALLOWANCE["max_input_tokens"], "output_tokens": 0}
    provider = recording(reply("Never sent."))
    with pytest.raises(Unavailable) as refused:
        run(agent(provider).answer(QUESTION, Recovering(), context(checkpoint=saved, spent=spent)))
    assert refused.value.code == "allowance_exhausted"
    assert provider.requests == []


def test_a_fresh_run_with_the_same_spending_is_refused_too():
    # No checkpoint at all (killed before its first step completed): the ledger still counts.
    spent = {"input_tokens": ALLOWANCE["max_input_tokens"], "output_tokens": 0}
    provider = recording(reply("Never sent."))
    with pytest.raises(Unavailable):
        run(agent(provider).answer(QUESTION, Recovering(), context(spent=spent)))
    assert provider.requests == []


def test_a_source_that_changed_is_rebuilt_from_the_question_and_its_steps_stay_taken():
    saved, _ = first_worker()
    corpus = Recovering()
    corpus.replaced.add(1)
    result, provider, corpus = replacement(saved, reply("A general answer with no repository finding."),
                                           corpus=corpus)
    [rebuilt] = provider.requests
    # Nothing recovered reaches the model: no restored call group, no restored result.
    assert [m["role"] for m in rebuilt["messages"]] == ["system", "user"]
    assert FLOOD not in json.dumps(rebuilt)
    assert ("recovery", {"outcome": "rebuilt", "reason": "stale", "step": 1}) in corpus.events
    assert [m["step"] for m in models(corpus)] == [2]
    assert result.citations == ()


def test_a_run_that_lost_its_fence_saves_nothing_and_sends_nothing_more():
    async def lost(step, body):
        return False

    provider = recording(tools(call("c-1", "search", query="flood")), reply("Never sent."))
    corpus = Corpus()
    with pytest.raises(Unavailable) as refused:
        run(agent(provider).answer(QUESTION, corpus, context(save=lost)))
    assert refused.value.code == "run_ended"
    assert len(provider.requests) == 1


def _mutated(body, change):
    body = copy.deepcopy(body)
    change(body)
    return body


def _drop_last_result(body):
    body["history"].pop()


def _foreign_artifact(body):
    for entry in body["history"]:
        for item in entry.get("items", ()):
            if item["t"] == "opaque":
                item["binding"][1] = "another-model"


INCOMPATIBLE = {
    "format": lambda b: b.update(format="agent-checkpoint-0"),
    "pin": lambda b: b["pin"].update(model="another-model"),
    "bounds": lambda b: b["bounds"].update(max_steps=99),
    "task": lambda b: b.update(task="0" * 64),
    "unanswered_call": _drop_last_result,
    "foreign_artifact": _foreign_artifact,
    "malformed": lambda b: b["investigation"].pop("passages"),
}


@pytest.mark.parametrize("change", INCOMPATIBLE.values(), ids=list(INCOMPATIBLE))
def test_a_checkpoint_that_is_not_this_runs_to_continue_is_refused(change):
    saved, _ = first_worker()
    task = checkpoint.task_key(QUESTION, (), {})
    assert checkpoint.load(saved["body"], pin=PIN, bounds=ORDINARY, task=task) is not None
    assert checkpoint.load(_mutated(saved["body"], change), pin=PIN, bounds=ORDINARY, task=task) is None


def test_an_incompatible_checkpoint_is_rebuilt_never_continued():
    saved, _ = first_worker()
    foreign = {**saved, "body": _mutated(saved["body"], INCOMPATIBLE["pin"])}
    _, provider, corpus = replacement(foreign, reply("A general answer."))
    assert [m["role"] for m in provider.requests[0]["messages"]] == ["system", "user"]
    assert corpus.reauthorized == []
    assert ("recovery", {"outcome": "rebuilt", "reason": "incompatible", "step": 1}) in corpus.events


def test_counts_focus_plan_and_seen_evidence_survive_the_round_trip():
    found = Investigation(None, metadata=True)
    found.counts = [Count(total=3, filters=(("classification", "Engineering"), ("year_from", 2020)),
                          group_by="year", groups=((2021, 2), (2022, 1)), population=frozenset({4, 5, 6}))]
    found.exact, found.figures, found.terms = {"3"}, {"3", "2021"}, {"engineering"}
    found.papers = {4: (handle("R", 4), "Bridges")}
    found.selected, found.excluded = (4,), ()
    found.plan, found.plan_revision = ({"id": "a", "title": "Count", "status": "done"},), 1
    found.seen = {("count", found.counts[0].filters, "year"), ("paper", 4)}
    found.tool_calls, found.reads, found.searched = 2, 1, True
    found.outages = ["search"]

    class Spent:
        input, output, reported, attempts = 10, 5, 15, 2

    body = json.loads(json.dumps(checkpoint.dump(
        pin=PIN, bounds=ORDINARY, task="t", history=[], investigation=found, budget=Spent, steps=1, stale=0)))
    restored = checkpoint.load(body, pin=PIN, bounds=ORDINARY, task="t")
    again = Investigation(None, metadata=True)
    restored.apply(again)
    for name in ("counts", "exact", "figures", "terms", "papers", "selected", "excluded", "plan",
                 "plan_revision", "seen", "tool_calls", "reads", "searched", "outages"):
        assert getattr(again, name) == getattr(found, name), name
    assert restored.counted() == [4, 5, 6]
    assert restored.budget == {"input": 10, "output": 5, "reported": 15, "attempts": 2}
    assert dataclasses.asdict(ORDINARY) == body["bounds"]
