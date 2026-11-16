"""research-10: a follow-up sees each earlier Turn's number and what it cited (IR-1168).

The recording provider throughout; no vendor is called. Loading the citations
from PostgreSQL is `test_ai_runtime_turn_sources_db.py`'s.
"""

import dataclasses
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.agent.compaction import Compaction  # noqa: E402
from ai.agent.executor import AgentExecutor, _Run  # noqa: E402
from ai.agent.prompts import (  # noqa: E402
    CITED_INSTRUCTIONS, CITED_NOTE, CITED_PROMPT_VERSION, CITED_TOOL_VERSION, COHERENT_INSTRUCTIONS, EARLIER_TURN,
    PROMPTS,
)
from ai.research.tools import RecoveredTurn  # noqa: E402
from ai.runs.executor import PriorTurn  # noqa: E402
from .test_ai_runtime_agent_loop_contract import (  # noqa: E402
    FLOOD, PROFILES, RESERVES, Corpus, call, context, handle, models, reply, run, tools,
)
from .test_ai_runtime_compaction_contract import WINDOW, Handoffs, windowed  # noqa: E402
from .test_ai_runtime_followups_contract import screened  # noqa: E402
from .test_ai_runtime_ir1166_contract import PIN_9  # noqa: E402
from .test_ai_runtime_ir995_contract import Searchable  # noqa: E402

PIN_10 = dataclasses.replace(PIN_9, prompt_version="agent-research-10", tool_version="research-10")
QUESTION = "What about the second one?"
FIRST = PriorTurn("Which papers study water?", "Two papers [1] [2].", "answer", 1,
                  cited=((1, 4), (2, 2), (1, 6)))
SECOND = PriorTurn("Hello", "Hello; ask about the papers.", "answer", 2)
#: The note under Turn 1's answer while both papers are readable.
LISTED = (f"\n\nPapers this answer cited: «Flood forecasting» (paper {handle('R', 1)}), pages 4, 6; "
          f"«Pond sampling» (paper {handle('R', 2)}), page 2.")


def follow_up(provider, pin=PIN_10, prior=(FIRST, SECOND), corpus=None, **kw):
    corpus = corpus or Corpus()
    agent = AgentExecutor(provider, pin, RESERVES, profiles=PROFILES, **kw.pop("agent", {}))
    return run(agent.answer(QUESTION, corpus, context(prior=prior, **kw))), corpus


def messages(provider, n=0):
    return provider.requests[n]["messages"]


def contents(provider, n=0):
    return [m.get("content") for m in messages(provider, n)]


def test_research_10_is_a_new_pin_and_research_9_keeps_its_text():
    assert (CITED_PROMPT_VERSION, CITED_TOOL_VERSION) == ("agent-research-10", "research-10")
    assert PROMPTS[("agent-research-10", "research-10")] is CITED_INSTRUCTIONS
    assert PROMPTS[("agent-research-9", "research-9")] is COHERENT_INSTRUCTIONS
    added = "reread that Turn with recover_turn by its number, or read a cited page again with read_page"
    assert CITED_INSTRUCTIONS.count(added) == 1 and added not in COHERENT_INSTRUCTIONS
    assert CITED_INSTRUCTIONS.count("[IRIS earlier Turn 2]") == 1
    # research-10's bytes: these texts are part of every follow-up it sends.
    assert (EARLIER_TURN, CITED_NOTE) == ("[IRIS earlier Turn {n}] ", "\n\nPapers this answer cited: ")


def test_a_follow_up_is_sent_each_earlier_turn_with_its_number_and_cited_papers():
    provider = screened(reply("General background."))
    follow_up(provider)
    sent = contents(provider)
    assert sent[0] == CITED_INSTRUCTIONS
    assert sent[1:] == [
        "[IRIS earlier Turn 1] Which papers study water?", "Two papers." + LISTED,
        "[IRIS earlier Turn 2] Hello", "Hello; ask about the papers.",
        QUESTION,
    ]


def test_the_agent_recovers_an_earlier_turn_by_the_number_it_was_shown():
    corpus = Corpus()
    corpus.turns[1] = (RecoveredTurn(1, FIRST.question, f"Two papers [{handle('P', 1)}].", "answer"),
                       [corpus.papers[1][2]])
    provider = screened(tools(call("r", "recover_turn", turn=1)),
                        reply(f"The first predicted 87 floods [{handle('P', 1)}]."))
    result, corpus = follow_up(provider, corpus=corpus)
    assert "[IRIS earlier Turn 1]" in contents(provider)[1]
    assert ("recover_turn", 1) in corpus.calls
    recovered = json.loads(next(m["content"] for m in messages(provider, 1) if m.get("tool_call_id") == "r"))
    assert [p["text"] for p in recovered["passages"]] == [FLOOD]
    assert result.answer == "The first predicted 87 floods [1]."


def test_a_paper_the_reader_can_no_longer_read_is_not_listed():
    gone = PriorTurn("Which papers study water?", "Two papers.", "answer", 1, cited=((1, 4), (9, 3)))
    only_gone = PriorTurn("And the other?", "That one.", "answer", 2, cited=((9, 3),))
    provider = screened(reply("General background."))
    _, corpus = follow_up(provider, prior=(gone, only_gone))
    sent = contents(provider)
    assert sent[2] == f"Two papers.{CITED_NOTE}«Flood forecasting» (paper {handle('R', 1)}), page 4."
    # A Turn whose every cited paper is unreadable is shown without a list.
    assert sent[4] == "That one."
    assert ("recall", (1, 9)) in corpus.calls
    assert not any(str(c).startswith("[IRIS conversation state]") for c in sent)


def test_a_turn_with_no_citations_is_shown_without_a_list():
    provider = screened(reply("General background."))
    follow_up(provider, prior=(SECOND,))
    assert contents(provider)[1:3] == ["[IRIS earlier Turn 2] Hello", "Hello; ask about the papers."]


def test_a_cited_paper_lends_the_turn_its_source():
    result, _ = follow_up(screened(reply("General background.")), prior=(FIRST,))
    flood, pond = Corpus().papers[1][1], Corpus().papers[2][1]
    assert result.sources >= {flood, pond}


def test_research_9_receives_earlier_turns_exactly_as_before():
    plain = (dataclasses.replace(FIRST, cited=()), SECOND)
    with_cited, without = screened(reply("General background.")), screened(reply("General background."))
    _, corpus = follow_up(with_cited, pin=PIN_9)
    follow_up(without, pin=PIN_9, prior=plain)
    assert messages(with_cited) == messages(without)
    assert contents(with_cited)[1:3] == ["Which papers study water?", "Two papers."]
    # Nothing is read for citations an older pin does not show.
    assert not any(c[0] == "recall" for c in corpus.calls)


def wide(*responses):
    # A larger fixture window, for research-10's tools and text.
    provider = windowed(*responses)
    provider.capacities = {"scripted-model": dataclasses.replace(WINDOW, context_tokens=32_000)}
    return provider


def occupancy(listed: bool) -> int:
    agent = AgentExecutor(wide(), PIN_10, RESERVES, profiles=PROFILES)
    turn = _Run(agent, QUESTION, Corpus(), context(prior=(FIRST, SECOND)))
    run(turn.investigation.recall({}, also=[1, 2]))
    return agent.occupancy(turn.request([*turn._earlier(listed=listed), *turn._closing({}, None)]))


def test_a_history_that_would_overflow_drops_the_citation_lists_before_any_turn():
    without, with_lists = occupancy(False), occupancy(True)
    assert without < with_lists
    # Compacting would drop Turns; the lists alone push the history to the threshold.
    rule = Compaction(threshold_tokens=without + 1, summary_tokens=400, keep_exchanges=1, max_attempts=2)
    provider = wide(reply("General background."))
    _, corpus = follow_up(provider, agent={"compaction": rule}, commit_handoff=Handoffs())
    assert [m["phase"] for m in models(corpus)] == ["gather"]
    assert contents(provider)[1:5] == [
        "[IRIS earlier Turn 1] Which papers study water?", "Two papers.",
        "[IRIS earlier Turn 2] Hello", "Hello; ask about the papers.",
    ]


def test_with_room_the_same_rule_keeps_the_lists():
    rule = Compaction(threshold_tokens=occupancy(True) + 1, summary_tokens=400, keep_exchanges=1, max_attempts=2)
    provider = wide(reply("General background."))
    _, corpus = follow_up(provider, agent={"compaction": rule}, commit_handoff=Handoffs())
    assert [m["phase"] for m in models(corpus)] == ["gather"]
    assert contents(provider)[2] == "Two papers." + LISTED


#: Turn 1 citing many pages, so its list outweighs one search result.
MANY = dataclasses.replace(FIRST, cited=tuple((1, page) for page in range(1, 201)))


def used(corpus):
    return [data["used_tokens"] for name, data in corpus.events if name == "context"]


def searched(prior, **kw):
    provider = wide(tools(call("s", "search", query="flood")), reply("General background."))
    return (provider, *follow_up(provider, prior=prior, corpus=Searchable(), **kw))


def test_lists_also_go_before_a_turn_once_research_grows_the_history():
    _, _, corpus = searched((MANY, SECOND))
    opened, grown = used(corpus)
    _, _, plain = searched((dataclasses.replace(MANY, cited=()), SECOND))
    lists = opened - used(plain)[0]
    assert grown - lists < opened + 1 <= grown
    rule = Compaction(threshold_tokens=opened + 1, summary_tokens=400, keep_exchanges=1, max_attempts=2)
    provider, _, corpus = searched((MANY, SECOND), agent={"compaction": rule}, commit_handoff=Handoffs())
    # No Turn was compacted: dropping the lists was enough.
    assert [m["phase"] for m in models(corpus)] == ["gather", "gather"]
    assert CITED_NOTE in contents(provider, 0)[2] and CITED_NOTE not in contents(provider, 1)[2]
    assert contents(provider, 1)[1:5] == [
        "[IRIS earlier Turn 1] Which papers study water?", "Two papers.",
        "[IRIS earlier Turn 2] Hello", "Hello; ask about the papers.",
    ]
