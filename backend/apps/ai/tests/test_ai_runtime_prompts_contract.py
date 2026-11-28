"""Every text the AGENT is sent, defined in one module and unchanged by the move (IR-1158, ADR-049 §14).

The digests below were recorded from the code before the texts moved into
`ai.agent.prompts`. A pinned version must keep its exact bytes: a checkpoint
binds its history to the digest of the instructions and tool schemas.
"""

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from .test_ai_runtime_agent_loop_contract import PIN, PROFILES, Corpus, context
from .test_ai_runtime_checkpoint_contract import CITED, replacement
from .test_ai_runtime_context_contract import RESERVES
from ai.agent import assurance, checkpoint, compaction, prompts, tools as toolset
from ai.agent import executor as executing
from ai.agent.executor import AgentExecutor, _Run
from ai.agent.tools import Investigation
from ai.infrastructure.recording_adapter import RecordingAgentProvider

#: checkpoint.prefix_digest of each pinned version's instructions and tool schemas, before the move.
PREFIXES = {
    ("agent-direct-1", "none-1"): "5f3968d44b9b7799a8f4e0634b6db4ae30bb2f3ee641c081073276670dda1fef",
    ("agent-research-1", "research-1"): "ff1b589b576f7e5f9179249717508afea0a3f912156baa43da75a740ebaa3637",
    ("agent-research-2", "research-2"): "03d750db0844f02f808f895bcb6c8522b9e2c7f98297686bf4bf0f761801c842",
    ("agent-research-3", "research-3"): "dcc8097643e3999e787997b7d18dc35e45f799730faeeb17301c31aafaf76794",
    ("agent-research-4", "research-4"): "4be11cba8b952313decdd87f0668356289f1a6c830bf52ce86c30b84487d6071",
    ("agent-research-5", "research-5"): "9f9bcfc056392948cf6f5f695bf09d0b29b558366fd0c3cf9aa0551263d4fbfc",
    ("agent-research-6", "research-6"): "e0671d785429b53a6c5bac9b4fb15e27cc879d27ab2cdcf6879e2a19dcb2448e",
    ("agent-research-7", "research-7"): "5066cba368de644c242875266c85051ddf32c6af295fbe0bffbfcb003088791b",
    ("agent-research-8", "research-8"): "fd35528d31fd95aebfaff7d3763a1931f3351bcbd48feec99586f36a91b54e85",
    # Recorded when research-9 was written (IR-1166); its bytes are pinned from here on.
    ("agent-research-9", "research-9"): "c6dd733fe29458bea04f63ae016c3dbc02fcd4563a99182ff4b744fd196431b9",
    # Recorded when research-10 was written (IR-1168).
    ("agent-research-10", "research-10"): "09baf9f1e5a50e461da883b9d0d0399dcbb83f15620a7013d07714f49a6c6a18",
    # Recorded when research-11 was written (IR-1196).
    ("agent-research-11", "research-11"): "daa38f5380498eb0195ae28b17a01a4ef51554ae35a6f844c9a97414554958b1",
    # Recorded when research-12 was written (IR-581).
    ("agent-research-12", "research-12"): "dcca426d6f8810400fb0efaadbf90f3b6ffb9d4793871b47d7e128e789ee85a5",
    # Recorded when research-13 was written (IR-1278).
    ("agent-research-13", "research-13"): "0793152083bbf43448f97ad802a7291ac8adc5f18c4973bcc8efbe7702400227",
    # Recorded when research-14 was written (IR-1300): research-13's tools, its own text.
    ("agent-research-14", "research-13"): "76e8902b7ff32c437b141a19ee13949bc395dcd22207e48c38fdd8dd5f3bb99e",
    # Recorded when agent-research-15 was written (IR-1316).
    ("agent-research-15", "research-14"): "24abdd97386a5fc6aaa3600d77874b89bb9245471d07c9fcffb6ad868e4f9db1",
}
#: The notes, prefixes and repair texts every research version sends, before the move.
NOTES = "74d1d448eb110799d49624570b4ca686e8ddca28adf6cb0d53b647db008f27d2"
#: A step saved by research-1 before the move (`first_worker` of the checkpoint suite).
SAVED = Path(__file__).parent / "fixtures" / "ir1158_checkpoint.json"


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def prefix(prompt_version, tool_version):
    pin = dataclasses.replace(PIN, prompt_version=prompt_version, tool_version=tool_version)
    agent = AgentExecutor(RecordingAgentProvider(responses=[]), pin, RESERVES, profiles=PROFILES)
    if not agent.researches:
        return checkpoint.prefix_digest(executing.PROMPTS[(prompt_version, tool_version)], ())
    return _Run(agent, "q", Corpus(), context())._prefix()


def notes():
    found = {code: [f"{code}-item"] for code in assurance._FEEDBACK}
    return {
        "final": executing.FINAL_NOTE, "paper_chat": executing.PAPER_CHAT_PREFIX,
        "compact_request": executing.COMPACT_REQUEST,
        "repair": assurance.feedback(found), "repair_unseen": assurance.feedback(found, unseen=True),
        "summary_request": compaction.NOTE, "derived": compaction.DERIVED,
        "handoff_prefix": compaction.PREFIX, "state_prefix": compaction.STATE_PREFIX,
    }


@pytest.mark.parametrize("version", sorted(PREFIXES))
def test_each_pinned_version_sends_the_same_instructions_and_tool_schemas(version):
    assert prefix(*version) == PREFIXES[version]


def test_every_pinned_version_is_recorded():
    assert set(executing.PROMPTS) == set(PREFIXES)


def test_the_notes_and_repair_texts_are_unchanged():
    assert digest(notes()) == NOTES


def test_a_checkpoint_saved_before_the_move_resumes_after_it():
    saved = json.loads(SAVED.read_text(encoding="utf-8"))
    result, provider, corpus = replacement(saved, {
        "choices": [{"message": {"role": "assistant", "content": CITED}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 60, "completion_tokens": 20}})

    assert ("recovery", {"outcome": "resumed", "step": 1}) in corpus.events
    assert provider.requests[0]["messages"][-2]["tool_calls"][0]["id"] == "c-1"
    assert result.answer.endswith("[1].")


def test_the_texts_are_defined_in_the_prompts_module():
    assert executing.PROMPTS is prompts.PROMPTS
    assert executing.FINAL_NOTE is prompts.FINAL_NOTE
    assert executing.PAPER_CHAT_PREFIX is prompts.PAPER_CHAT_PREFIX
    assert executing.COMPACT_REQUEST is prompts.COMPACT_REQUEST
    assert assurance.REPAIR_NOTE is prompts.REPAIR_NOTE
    assert assurance.UNSEEN_DRAFT is prompts.UNSEEN_DRAFT
    assert assurance._FEEDBACK is prompts.REPAIR_FEEDBACK
    assert compaction.NOTE is prompts.SUMMARY_REQUEST
    assert compaction.DERIVED is prompts.DERIVED
    assert compaction.PREFIX is prompts.HANDOFF_PREFIX
    assert compaction.STATE_PREFIX is prompts.STATE_PREFIX
    assert compaction.reader(prompts.STATE_PREFIX) == "(reader) " + prompts.STATE_PREFIX
    every = Investigation(None, clarify=True, metadata=True, manuscripts=True, recovery=True, hybrid=True,
                          listing=True, details=True).specs() + toolset.RESEARCH[:1] + (
        toolset.DATED_SEARCH, toolset.DATED_COUNT, toolset.DATED_LIST, toolset.DATED_DETAILS)
    assert {spec.description for spec in every} == set(prompts.TOOL_DESCRIPTIONS.values())
