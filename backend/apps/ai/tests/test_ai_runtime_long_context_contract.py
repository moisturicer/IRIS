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
    PIN, PROFILES, call, context, handle, models, recording, reply, run, tools,
)
from .test_ai_runtime_checkpoint_contract import first_worker, replacement
from .test_ai_runtime_compaction_contract import EAGER, Handoffs, handoff_of
from .test_ai_runtime_context_contract import RESERVES
from .test_ai_runtime_manuscript_contract import PAPER, Manuscript, at
from ai.agent import executor as executing
from ai.agent import tools as toolset
from ai.agent.executor import AgentExecutor

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
