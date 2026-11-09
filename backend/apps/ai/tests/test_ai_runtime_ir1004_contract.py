"""research-8: repository questions are answered from the repository or declined (IR-1004).

IR-995's F12 run: reader b was answered from general knowledge where the papers it
can see say nothing, repairs mentioned the draft the reader never saw, and one run
ended `invalid_draft` instead of saying it had no supported answer.
"""

import dataclasses
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.agent import assurance  # noqa: E402
from ai.agent.executor import (  # noqa: E402
    EVIDENCE_PROMPT_VERSION, EVIDENCE_TOOL_VERSION, NO_SUPPORTED_ANSWER, PAPER_CHAT_PREFIX, PROMPTS,
)
from ai.runs.executor import Unavailable  # noqa: E402
from .test_ai_runtime_agent_loop_contract import PIN, call, handle, models, reply, tools  # noqa: E402
from .test_ai_runtime_followups_contract import screened, sent_text  # noqa: E402
from .test_ai_runtime_ir995_contract import BAD, GOOD, PIN_7, Chat, Searchable, answer  # noqa: E402

PIN_8 = dataclasses.replace(PIN, prompt_version="agent-research-8", tool_version="research-8")


def test_research_8_is_a_new_pin_and_research_7_keeps_its_prompt():
    assert (EVIDENCE_PROMPT_VERSION, EVIDENCE_TOOL_VERSION) == ("agent-research-8", "research-8")
    seven = PROMPTS[("agent-research-7", "research-7")]
    eight = PROMPTS[("agent-research-8", "research-8")]
    assert eight.startswith(seven) and eight != seven


def test_research_8_tells_the_model_to_decline_rather_than_answer_from_general_knowledge():
    provider = screened(reply("The papers you can read do not say."))
    answer(provider, PIN_8, question="Where can the ClusterCAD toolkit be accessed?")
    sent = sent_text(provider.requests[0])
    assert "do not answer from general knowledge" in sent
    provider = screened(reply("General background."))
    answer(provider, PIN_7)
    assert "do not answer from general knowledge" not in sent_text(provider.requests[0])


def test_research_8_repair_says_the_reader_never_saw_the_draft():
    provider = screened(tools(call("s", "search", query="flood")), reply(BAD), reply(GOOD))
    result, _ = answer(provider, PIN_8, Searchable())
    assert result.answer == "It predicted 87 floods [1]."
    assert assurance.UNSEEN_DRAFT in sent_text(provider.requests[-1])
    provider = screened(tools(call("s", "search", query="flood")), reply(BAD), reply(GOOD))
    answer(provider, PIN_7, Searchable())
    assert assurance.UNSEEN_DRAFT not in sent_text(provider.requests[-1])


def test_research_8_says_it_has_no_supported_answer_when_no_sentence_stands():
    provider = screened(tools(call("s", "search", query="flood")), reply(BAD), reply(BAD), reply(BAD))
    result, corpus = answer(provider, PIN_8, Searchable())
    assert result.answer == NO_SUPPORTED_ANSWER
    assert result.citations == () or not result.citations
    assert [m["phase"] for m in models(corpus)] == ["gather", "gather", "repair", "repair"]


def test_research_7_still_ends_invalid_draft_when_no_sentence_stands():
    provider = screened(tools(call("s", "search", query="flood")), reply(BAD), reply(BAD), reply(BAD))
    with pytest.raises(Unavailable) as refused:
        answer(provider, PIN_7, Searchable())
    assert refused.value.code == "invalid_draft"


def test_research_8_keeps_what_research_7_added():
    provider = screened(reply("General background."))
    answer(provider, PIN_8, Chat(), "How does this approach treat floods?")
    assert PAPER_CHAT_PREFIX in sent_text(provider.requests[0])
    provider = screened(tools(call("s", "search", query="flood")), reply(BAD), reply(BAD), reply(GOOD))
    result, _ = answer(provider, PIN_8, Searchable())
    assert result.answer == "It predicted 87 floods [1]." and handle("P", 1) not in result.answer
