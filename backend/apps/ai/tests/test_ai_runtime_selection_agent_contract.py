"""What the model is sent when a reader asks about a selected passage (IR-581).

The recording provider throughout; no vendor is called. The worker hands the
executor a selection only after rechecking it (`test_ai_runtime_selection_db.py`);
here the executor's half, under research-12: the passage is named once, just
before the question, quoted as paper text, and a withdrawn one is named as
withdrawn, its text never sent. No earlier pin is ever sent either.
"""

import dataclasses
import json
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.agent import checkpoint  # noqa: E402
from ai.agent.executor import AgentExecutor  # noqa: E402
from ai.agent.prompts import (  # noqa: E402
    DELIMITED_INSTRUCTIONS, PROMPTS, SELECTION_INSTRUCTIONS, SELECTION_PREFIX, SELECTION_PROMPT_VERSION,
    SELECTION_TOOL_VERSION, SELECTION_WITHDRAWN, quoted,
)
from ai.runs.anchor import OTHER_VERSION, SAME_VERSION, Assessed, Selection  # noqa: E402
from .test_ai_runtime_agent_loop_contract import FLOOD, PROFILES, context, handle, reply, run  # noqa: E402
from .test_ai_runtime_followups_contract import RESERVES, screened  # noqa: E402
from .test_ai_runtime_ir1196_contract import PIN_11  # noqa: E402
from .test_ai_runtime_ir995_contract import Chat  # noqa: E402

PIN_12 = dataclasses.replace(PIN_11, prompt_version="agent-research-12", tool_version="research-12")
QUESTION = "What does this passage mean?"
CHOSEN = Assessed(Selection(record_id=1, revision=str(uuid.uuid4()), page=4, quote=FLOOD),
                  found_on_page=True, version=SAME_VERSION)


def ask(pin, **kw):
    provider = screened(reply("General background."))
    agent = AgentExecutor(provider, pin, RESERVES, profiles=PROFILES)
    run(agent.answer(QUESTION, Chat(), context(**kw)))
    return [m.get("content") for m in provider.requests[0]["messages"]]


def test_research_12_is_research_11_plus_one_rule_about_selections():
    assert (SELECTION_PROMPT_VERSION, SELECTION_TOOL_VERSION) == ("agent-research-12", "research-12")
    assert PROMPTS[("agent-research-12", "research-12")] is SELECTION_INSTRUCTIONS
    assert PROMPTS[("agent-research-11", "research-11")] is DELIMITED_INSTRUCTIONS
    added = "A message starting [IRIS selection] is a passage the reader selected in a paper"
    assert SELECTION_INSTRUCTIONS.count(added) == 1
    # research-13 is built on research-12 and keeps the rule (IR-1278).
    assert {pin for pin, text in PROMPTS.items() if added in text} == {
        ("agent-research-12", "research-12"), ("agent-research-13", "research-13"),
        ("agent-research-14", "research-13")}
    rule = SELECTION_INSTRUCTIONS[SELECTION_INSTRUCTIONS.index("Selections."):
                                  SELECTION_INSTRUCTIONS.index("Searching. search")]
    assert SELECTION_INSTRUCTIONS.replace(rule, "", 1) == DELIMITED_INSTRUCTIONS


def test_a_verified_selection_is_named_just_before_the_question():
    sent = ask(PIN_12, selection=CHOSEN)
    assert sent[0] == SELECTION_INSTRUCTIONS
    assert sent[-1] == QUESTION
    assert sent[-2].startswith(SELECTION_PREFIX)
    body = json.loads(sent[-2][len(SELECTION_PREFIX):])
    # Paper text, quoted as research-11 began to (IR-1196); the Paper Chat note already names the title.
    assert body == {"paper": handle("R", 1), "page": 4, "quote": quoted(FLOOD), "found_on_page": True,
                    "version": "same"}
    assert sum(FLOOD in str(c) for c in sent) == 1


def test_an_unmatched_selection_from_another_version_is_still_sent_with_what_was_found():
    # Never refused: the model is told, and looks for the passage itself (IR-581).
    elsewhere = Assessed(CHOSEN.selection, found_on_page=False, version=OTHER_VERSION)
    sent = ask(PIN_12, selection=elsewhere)
    body = json.loads(sent[-2][len(SELECTION_PREFIX):])
    assert (body["found_on_page"], body["version"], body["quote"]) == (False, "different", quoted(FLOOD))
    assert "look on nearby pages" in sent[0]


def test_a_selection_from_another_paper_names_that_paper():
    other = Assessed(Selection(record_id=2, revision=None, page=2, quote="Tilapia ponds"),
                     found_on_page=True, version="unknown")
    sent = ask(PIN_12, selection=other)
    body = json.loads(sent[-2][len(SELECTION_PREFIX):])
    assert body["paper"] == handle("R", 2)
    assert body["title"] == quoted("Pond sampling")


def test_a_withdrawn_selection_is_said_to_be_gone_and_its_text_is_not_sent():
    sent = ask(PIN_12, selection_withdrawn=True)
    assert sent[-2:] == [SELECTION_WITHDRAWN, QUESTION]
    assert not any(FLOOD in str(c) for c in sent)


def test_a_question_without_a_selection_sends_no_selection_note():
    sent = ask(PIN_12)
    assert not any(str(c).startswith("[IRIS selection]") for c in sent)


def test_an_earlier_pin_is_never_sent_a_selection():
    for kw in ({"selection": CHOSEN}, {"selection_withdrawn": True}):
        sent = ask(PIN_11, **kw)
        assert sent[0] == DELIMITED_INSTRUCTIONS
        assert not any(str(c).startswith("[IRIS selection]") for c in sent)
        assert not any(FLOOD in str(c) for c in sent)


def test_a_step_taken_with_a_selection_is_not_resumed_without_it():
    plain = checkpoint.task_key(QUESTION, (), {})
    assert checkpoint.task_key(QUESTION, (), {}, selection=None) == plain
    unmatched = Assessed(CHOSEN.selection, False, SAME_VERSION)
    keys = {plain, checkpoint.task_key(QUESTION, (), {}, selection=CHOSEN.to_json()),
            checkpoint.task_key(QUESTION, (), {}, selection=unmatched.to_json()),
            checkpoint.task_key(QUESTION, (), {}, selection={"withdrawn": True})}
    assert len(keys) == 4
