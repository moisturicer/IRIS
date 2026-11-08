"""The guard withholds instead of ending a run; Paper Chat names its paper; two repairs (IR-995).

The executor with a recording model whose transport applies the guard's own
provenance check to every request, as the admitted transport does before a paid send.
"""

import dataclasses
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.agent.assurance import LIMITATION  # noqa: E402
from ai.agent.executor import PAPER_CHAT_PREFIX, AgentExecutor  # noqa: E402
from ai.research.tools import NO_MATCH, Coverage, Match, ToolResult  # noqa: E402
from .test_ai_runtime_agent_loop_contract import (  # noqa: E402
    FLOOD, PIN, PROFILES, Corpus, call, context, handle, models, reply, run, tools,
)
from .test_ai_runtime_context_contract import RESERVES  # noqa: E402
from .test_ai_runtime_followups_contract import FLOOD_SOURCE, PIN_2, PIN_6, screened, sent_text  # noqa: E402

PIN_7 = dataclasses.replace(PIN, prompt_version="agent-research-7", tool_version="research-7")


def answer(provider, pin, corpus=None, question="Which paper predicts floods?"):
    corpus = corpus or Corpus()
    agent = AgentExecutor(provider, pin, RESERVES, profiles=PROFILES)
    return run(agent.answer(question, corpus, context())), corpus


def test_a_search_whose_only_paper_cannot_be_sent_is_withheld_and_the_run_answers():
    provider = screened(tools(call("s", "search", query="flood")), reply("General background."),
                        withdrawn=[FLOOD_SOURCE])
    result, _ = answer(provider, PIN_2)
    assert result.answer == "General background."
    shown = next(m for m in provider.requests[1]["messages"] if m.get("tool_call_id") == "s")
    assert json.loads(shown["content"])["reason"] == "withheld" and FLOOD not in sent_text(provider.requests[1])


class Unnamed(Corpus):
    async def resolve(self, references=(), record_ids=()):
        self.calls.append(("resolve", tuple(references)))
        return ToolResult(NO_MATCH, matches=(Match(1, "title", "none"),), coverage=Coverage(0, 1, False))


def test_a_paper_name_that_matched_nothing_does_not_end_the_run():
    provider = screened(tools(call("r", "resolve_papers", references=["Tide and Seek"])),
                        reply("No paper by that name is among the records you can see."))
    result, _ = answer(provider, PIN_2, Unnamed(), "Find the Tide and Seek paper.")
    assert result.answer == "No paper by that name is among the records you can see."


class Chat(Corpus):
    scope = 1


def test_a_research_7_paper_chat_names_its_paper_to_the_model():
    provider = screened(reply("General background."))
    answer(provider, PIN_7, Chat(), "How does this approach treat floods?")
    note = next(m["content"] for m in provider.requests[0]["messages"]
                if str(m.get("content", "")).startswith(PAPER_CHAT_PREFIX))
    assert json.loads(note[len(PAPER_CHAT_PREFIX):]) == {"paper": handle("R", 1), "title": "Flood forecasting"}


def test_earlier_pins_and_unscoped_chats_add_no_paper_note():
    for pin, corpus in ((PIN_6, Chat()), (PIN_7, Corpus())):
        provider = screened(reply("General background."))
        answer(provider, pin, corpus)
        assert PAPER_CHAT_PREFIX not in sent_text(provider.requests[0])


def test_a_paper_the_send_cannot_carry_is_not_named():
    provider = screened(reply("General background."), withdrawn=[FLOOD_SOURCE])
    result, _ = answer(provider, PIN_7, Chat())
    assert PAPER_CHAT_PREFIX not in sent_text(provider.requests[0]) and result.answer == "General background."


class Searchable(Corpus):
    async def hybrid_search(self, query, limit=10, filters=None):
        return await self.search(query, limit)


BAD = f"It predicted 912 floods [{handle('P', 1)}]."
GOOD = f"It predicted 87 floods [{handle('P', 1)}]."


def test_research_7_repairs_a_draft_twice_and_journals_only_rule_codes():
    provider = screened(tools(call("s", "search", query="flood")), reply(BAD), reply(BAD), reply(GOOD))
    result, corpus = answer(provider, PIN_7, Searchable())
    assert result.answer == "It predicted 87 floods [1]."
    assert [m["phase"] for m in models(corpus)] == ["gather", "gather", "repair", "repair"]
    checks = [data for name, data in corpus.events if name == "check"]
    assert checks == [{"stage": "draft", "codes": ["unsupported_number"]},
                      {"stage": "repair_1", "codes": ["unsupported_number"]}]


def test_research_6_still_repairs_once_then_keeps_supported_sentences():
    provider = screened(tools(call("s", "search", query="flood")),
                        reply(f"{GOOD} Some 40 more papers agree."), reply(f"{GOOD} Some 40 more papers agree."))
    result, corpus = answer(provider, PIN_6, Searchable())
    assert result.answer == f"It predicted 87 floods [1].\n\n{LIMITATION}"
    assert [m["phase"] for m in models(corpus)] == ["gather", "gather", "repair"]
