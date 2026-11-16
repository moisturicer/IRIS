"""research-9: one coherent instruction text in place of nine appended ones (IR-1166).

The recording provider throughout; no vendor is called.
"""

import dataclasses
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.agent import assurance  # noqa: E402
from ai.agent.compaction import PREFIX  # noqa: E402
from ai.agent.executor import AgentExecutor  # noqa: E402
from ai.agent.prompts import (  # noqa: E402
    COHERENT_INSTRUCTIONS, COHERENT_PROMPT_VERSION, COHERENT_TOOL_VERSION, EVIDENCE_INSTRUCTIONS,
    PAPER_CHAT_PREFIX, PROMPTS,
)
from .test_ai_runtime_agent_loop_contract import (  # noqa: E402
    PROFILES, RESERVES, Corpus, call, context, handle, models, reply, run, tools,
)
from .test_ai_runtime_compaction_contract import (  # noqa: E402
    EAGER, PRIOR, STATE, SUMMARY, WINDOW, Handoffs, windowed,
)
from .test_ai_runtime_followups_contract import screened, sent_text  # noqa: E402
from .test_ai_runtime_ir995_contract import BAD, GOOD, Chat, Searchable, answer  # noqa: E402
from .test_ai_runtime_ir1004_contract import PIN_8  # noqa: E402

PIN_9 = dataclasses.replace(PIN_8, prompt_version="agent-research-9", tool_version="research-9")

#: Each rule the text keeps, by a phrase that states it; each must appear exactly once.
RULES = {
    "repository answers come from the tools": "answered only from what the tools returned",
    "general background is labelled": "general background is not a finding from the repository",
    "decline rather than use general knowledge": "do not answer from general knowledge",
    "search again before declining": "search again with different wording",
    "cite in the stating sentence": "in the sentence that states it",
    "counts need no handle": "give them without passage handles",
    "titles are marked": "Mark paper titles as «title»",
    "a search is a sample": "never the whole repository",
    "meaning search outage": "say that the search matched keywords only",
    "counts are of what the reader can see": "of the records they can see",
    "use the clear match": "use the one that is clearly meant",
    "clarify only when search cannot settle it": "ask a clarifying question only when searching cannot settle it",
    "paper chat refers to its paper": "answer from it without asking which paper",
    "formulas are described as read": "describe them as read",
    "figures are not interpreted": "that figures were not interpreted",
    "listings are of what the reader can see": "names the matching papers this reader can see",
    "a summary is not evidence": "A summary is not evidence",
    "prose after a compaction": "answer the reader in prose",
    "short paragraphs": "Write short paragraphs",
    "lists and tables for parallel items": "a list or a table only for parallel items",
    "no heading on one paragraph": "no heading on a one-paragraph answer",
    "never mention the draft": "never mention or correct an earlier draft",
}
#: Rules a later version replaced; none may survive into research-9.
SUPERSEDED = (
    "ask which one they mean",
    "figures and formulas were not interpreted",
    "Ask a clarifying question only when ambiguity blocks useful research",
)


def test_research_9_is_a_new_pin_written_whole_and_research_8_keeps_its_text():
    assert (COHERENT_PROMPT_VERSION, COHERENT_TOOL_VERSION) == ("agent-research-9", "research-9")
    assert PROMPTS[("agent-research-9", "research-9")] is COHERENT_INSTRUCTIONS
    assert PROMPTS[("agent-research-8", "research-8")] is EVIDENCE_INSTRUCTIONS
    assert not COHERENT_INSTRUCTIONS.startswith(EVIDENCE_INSTRUCTIONS[:200])


@pytest.mark.parametrize("rule", sorted(RULES))
def test_each_rule_appears_exactly_once(rule):
    assert COHERENT_INSTRUCTIONS.count(RULES[rule]) == 1


@pytest.mark.parametrize("old", SUPERSEDED)
def test_no_superseded_rule_survives(old):
    assert old.lower() not in COHERENT_INSTRUCTIONS.lower()


def test_formulas_are_no_longer_said_to_be_uninterpreted():
    assert "formulas were not interpreted" not in COHERENT_INSTRUCTIONS
    assert "Formulas in the text were transcribed" in COHERENT_INSTRUCTIONS


def test_research_9_sends_its_text_and_research_8_sends_its_own():
    provider = screened(reply("General background."))
    answer(provider, PIN_9)
    assert provider.requests[0]["messages"][0]["content"] == COHERENT_INSTRUCTIONS
    provider = screened(reply("General background."))
    answer(provider, PIN_8)
    assert provider.requests[0]["messages"][0]["content"] == EVIDENCE_INSTRUCTIONS


def test_a_run_after_a_compaction_is_sent_the_prose_instruction():
    handoffs = Handoffs()
    provider = windowed(reply(json.dumps(SUMMARY)), reply("The second paper sampled brackish ponds weekly."))
    # A larger fixture window, for research-9's tools and text.
    provider.capacities = {"scripted-model": dataclasses.replace(WINDOW, context_tokens=32_000)}
    agent = AgentExecutor(provider, PIN_9, RESERVES, profiles=PROFILES, compaction=EAGER)
    corpus = Corpus()
    result = run(agent.answer("Tell me about the second paper.", corpus,
                              context(prior=PRIOR, state=STATE, commit_handoff=handoffs)))

    assert [m["phase"] for m in models(corpus)] == ["compact", "gather"]
    assert handoffs.committed
    answered = provider.requests[-1]
    # The request that answers carries both the summary handoff and the instruction about it.
    assert answered["messages"][1]["content"].startswith(PREFIX)
    assert RULES["prose after a compaction"] in answered["messages"][0]["content"]
    assert result.answer == "The second paper sampled brackish ponds weekly."


# --- research-9 keeps research-8's behaviour ----------------------------------

def test_research_9_offers_research_8s_tools():
    eight, nine = screened(reply("General background.")), screened(reply("General background."))
    answer(eight, PIN_8)
    answer(nine, PIN_9)
    assert eight.requests[0]["tools"] == nine.requests[0]["tools"]


def test_research_9_repair_says_the_reader_never_saw_the_draft():
    provider = screened(tools(call("s", "search", query="flood")), reply(BAD), reply(GOOD))
    result, _ = answer(provider, PIN_9, Searchable())
    assert result.answer == "It predicted 87 floods [1]."
    assert assurance.UNSEEN_DRAFT in sent_text(provider.requests[-1])


def test_research_9_repairs_twice_and_names_a_paper_chats_paper():
    replies = [tools(call("s", "search", query="flood")), reply(BAD), reply(BAD), reply(GOOD)]
    result, corpus = answer(screened(*replies), PIN_9, Searchable())
    assert result.answer == "It predicted 87 floods [1]." and handle("P", 1) not in result.answer
    assert [m["phase"] for m in models(corpus)] == ["gather", "gather", "repair", "repair"]
    provider = screened(reply("General background."))
    answer(provider, PIN_9, Chat(), "How does this approach treat floods?")
    assert PAPER_CHAT_PREFIX in sent_text(provider.requests[0])
