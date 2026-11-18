"""What the model is sent when a reader asks about a selected passage (IR-581).

The recording provider throughout; no vendor is called. The worker hands the
executor a selection only after rechecking it (`test_ai_runtime_selection_db.py`);
here the executor's half: the passage is named once, just before the
question, quoted as paper text under research-11, and a withdrawn one is
named as withdrawn, its text never sent.
"""

import json
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.agent import checkpoint  # noqa: E402
from ai.agent.executor import AgentExecutor  # noqa: E402
from ai.agent.prompts import SELECTION_PREFIX, SELECTION_WITHDRAWN, quoted  # noqa: E402
from ai.runs.anchor import Selection  # noqa: E402
from .test_ai_runtime_agent_loop_contract import FLOOD, PROFILES, context, handle, reply, run  # noqa: E402
from .test_ai_runtime_followups_contract import RESERVES, screened  # noqa: E402
from .test_ai_runtime_ir1196_contract import PIN_11  # noqa: E402
from .test_ai_runtime_ir995_contract import PIN_7, Chat  # noqa: E402

QUESTION = "What does this passage mean?"
CHOSEN = Selection(record_id=1, revision=str(uuid.uuid4()), page=4, quote=FLOOD)


def ask(pin, **kw):
    provider = screened(reply("General background."))
    agent = AgentExecutor(provider, pin, RESERVES, profiles=PROFILES)
    run(agent.answer(QUESTION, Chat(), context(**kw)))
    return [m.get("content") for m in provider.requests[0]["messages"]]


def test_a_verified_selection_is_named_just_before_the_question():
    sent = ask(PIN_7, selection=CHOSEN)
    assert sent[-1] == QUESTION
    assert sent[-2].startswith(SELECTION_PREFIX)
    assert json.loads(sent[-2][len(SELECTION_PREFIX):]) == {"paper": handle("R", 1), "page": 4, "quote": FLOOD}
    assert sum(FLOOD in str(c) for c in sent) == 1


def test_under_research_11_the_quote_is_marked_as_paper_text():
    sent = ask(PIN_11, selection=CHOSEN)
    body = json.loads(sent[-2][len(SELECTION_PREFIX):])
    assert body["quote"] == quoted(FLOOD)


def test_a_withdrawn_selection_is_said_to_be_gone_and_its_text_is_not_sent():
    sent = ask(PIN_7, selection_withdrawn=True)
    assert sent[-2:] == [SELECTION_WITHDRAWN, QUESTION]
    assert not any(FLOOD in str(c) for c in sent)


def test_a_question_without_a_selection_sends_no_selection_note():
    sent = ask(PIN_7)
    assert not any(str(c).startswith("[IRIS selection]") for c in sent)


def test_a_step_taken_with_a_selection_is_not_resumed_without_it():
    plain = checkpoint.task_key(QUESTION, (), {})
    assert checkpoint.task_key(QUESTION, (), {}, selection=None) == plain
    keys = {plain, checkpoint.task_key(QUESTION, (), {}, selection=CHOSEN.to_json()),
            checkpoint.task_key(QUESTION, (), {}, selection={"withdrawn": True})}
    assert len(keys) == 3
