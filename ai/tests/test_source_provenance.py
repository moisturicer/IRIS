"""Source revisions stay attached to local evidence without entering the wire payload."""

import json

from ai.agent import checkpoint, compaction
from ai.agent.dialect import ChatCompletions
from ai.agent.protocol import AgentRequest, ModelTurn, Pin, StopReason, Text, ToolCall, ToolResult, User
from ai.agent.tools import Investigation
from ai.research.tools import OK, PassageRef, Source, ToolResult as Evidence


SOURCE = Source(7, 31, "revision-a")


class Research:
    async def search(self, query, limit=10):
        return Evidence(OK, passages=(PassageRef("P" + "1" * 20, 7, 2, "Methods", "Finding", SOURCE),),
                        dependencies=frozenset({SOURCE}))


def test_search_result_carries_revision_without_serializing_it():
    operation = Investigation(Research()).execute(
        ToolCall("call", "search", json.dumps({"query": "finding"})))
    try:
        operation.send(None)
    except StopIteration as finished:
        outcome = finished.value
    assert outcome.dependencies == frozenset({SOURCE})
    assert "revision-a" not in outcome.content


def test_derived_turn_keeps_source_when_original_tool_result_is_gone():
    pin = Pin(model="scripted", endpoint="local", adapter="recording",
              dialect="chat-completions-1", prompt_version="agent-research-1",
              tool_version="research-1", public_version="public-1", state_version="1",
              data_policy="no-training")
    derived = ModelTurn((Text("A finding"),), StopReason.END, dependencies=frozenset({SOURCE}))
    request = AgentRequest(pin, "instruction", (derived,))
    assert request.history[0].dependencies == frozenset({SOURCE})
    assert "revision-a" not in json.dumps(ChatCompletions.encode(request))


def test_unverified_prior_turn_is_marked_without_a_fake_source():
    prior = ModelTurn((Text("An earlier answer"),), StopReason.END,
                      unverified_provenance=True)
    assert prior.unverified_provenance
    assert prior.dependencies == frozenset()


def test_checkpoint_round_trips_source_manifests_and_refuses_old_format():
    entries = (User("state", frozenset({SOURCE})),
               ToolResult("call", "Public passage", frozenset({SOURCE})),
               ModelTurn((Text("Finding"),), StopReason.END, dependencies=frozenset({SOURCE})))
    for entry in entries:
        restored = checkpoint._load_entry(checkpoint._entry(entry))
        assert restored.dependencies == frozenset({SOURCE})
    damaged = checkpoint._entry(entries[1])
    del damaged["sources"]
    try:
        checkpoint._load_entry(damaged)
    except KeyError:
        pass
    else:
        raise AssertionError("checkpoint without a source manifest was accepted")
    assert checkpoint.FORMAT == "agent-checkpoint-4"


def test_compacted_handoff_keeps_source_and_unverified_prior_status():
    summary = {"goal": "Answer", "findings": [], "preferences": [], "limitations": []}
    state = {"shown": [], "selected": [], "excluded": []}
    evidence = ToolResult("call", "Public passage", frozenset({SOURCE}))
    body = compaction.build(summary, previous=None, compacted=[], passages={}, plan=[],
                            state=state, entries=(evidence,))
    handoff = compaction.render(body, {}, passages=False)
    assert handoff.dependencies == frozenset({SOURCE})
    assert not handoff.unverified_provenance
    legacy = ModelTurn((Text("Unknown earlier answer"),), StopReason.END,
                       unverified_provenance=True)
    body = compaction.build(summary, previous=None, compacted=[], passages={}, plan=[],
                            state=state, entries=(evidence, legacy))
    assert compaction.render(body, {}, passages=False).unverified_provenance
