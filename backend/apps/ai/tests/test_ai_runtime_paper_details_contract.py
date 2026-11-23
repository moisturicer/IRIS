"""A paper's recorded details reach the model under research-13 (IR-1278, ADR-049).

The executor's half: only the research-13 pin offers `paper_details`; what the
submitter recorded is sent typed, its free text quoted as paper text; and the
years a details call returned may be stated without a passage handle. The
row policy's half is `test_ai_runtime_paper_details_db.py`.
"""

import dataclasses
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.agent.executor import AgentExecutor  # noqa: E402
from ai.agent.prompts import (  # noqa: E402
    DETAILS_INSTRUCTIONS, DETAILS_PROMPT_VERSION, DETAILS_TOOL_VERSION, PROMPTS, SELECTION_INSTRUCTIONS, quoted,
)
from ai.infrastructure.recording_adapter import RecordingAgentProvider  # noqa: E402
from ai.research.tools import OK, PARTIAL, Coverage, PaperDetails, ToolResult  # noqa: E402
from .test_ai_runtime_agent_loop_contract import (  # noqa: E402
    MILLION, PIN, PROFILES, Corpus, call, context, handle, reply, run, tools,
)
from .test_ai_runtime_context_contract import RESERVES  # noqa: E402

PIN_12 = dataclasses.replace(PIN, prompt_version="agent-research-12", tool_version="research-12")
PIN_13 = dataclasses.replace(PIN, prompt_version="agent-research-13", tool_version="research-13")

FLOOD_DETAILS = PaperDetails(
    handle=handle("R", 1), record_id=1, title="Flood forecasting",
    authors=("Ana Cruz", "Ben Reyes"), adviser="Carla Santos",
    year_completed=2023, year_accomplished=2022, publication_year=2024,
    record_type="Thesis / Research", classification="Hydrology", psced="Engineering",
    keywords=("floods", "neural networks"),
    abstract="A neural network trained on 12 rain gauges predicted 87 floods.",
    origin="institutional", is_ip=False, ip_type=None, for_commercialization=True,
    community_extension=False, requires_ethics_review=False, requested_offices=("KTTO",),
)
UNKNOWN = handle("R", 99)


def provider(*responses):
    return RecordingAgentProvider(responses=list(responses), capabilities=("continuation",),
                                  capacities={"scripted-model": MILLION})


class Detailed(Corpus):
    async def details(self, handles):
        self.calls.append(("details", list(handles)))
        found = tuple(d for d in (FLOOD_DETAILS,) if d.handle in handles)
        return ToolResult(OK if len(found) == len(handles) else PARTIAL, details=found,
                          coverage=Coverage(len(found), len(handles)))


def offered(request):
    return {t["function"]["name"] for t in request["tools"]}


def sent(request, call_id):
    return json.loads(next(m for m in request["messages"] if m.get("tool_call_id") == call_id)["content"])


def test_research_13_is_research_12_plus_one_paragraph_on_paper_details():
    assert (DETAILS_PROMPT_VERSION, DETAILS_TOOL_VERSION) == ("agent-research-13", "research-13")
    assert PROMPTS[("agent-research-13", "research-13")] is DETAILS_INSTRUCTIONS
    assert DETAILS_INSTRUCTIONS.startswith(SELECTION_INSTRUCTIONS.split("To answer from a whole paper")[0])
    assert "paper_details" in DETAILS_INSTRUCTIONS
    # No earlier pin is told about a tool it is never offered.
    assert not any("paper_details" in text for pin, text in PROMPTS.items()
                   if pin not in {("agent-research-13", "research-13"), ("agent-research-14", "research-13")})


def test_only_the_research_13_pin_offers_paper_details():
    newer = provider(reply("General background."))
    run(AgentExecutor(newer, PIN_13, RESERVES, profiles=PROFILES).answer("Hello", Detailed(), context()))
    assert "paper_details" in offered(newer.requests[0])
    older = provider(reply("General background."))
    run(AgentExecutor(older, PIN_12, RESERVES, profiles=PROFILES).answer("Hello", Detailed(), context()))
    assert "paper_details" not in offered(older.requests[0])


def test_every_recorded_field_reaches_the_model_with_its_free_text_quoted_and_unknown_handles_named():
    recording = provider(
        tools(call("d", "paper_details", papers=[handle("R", 1), UNKNOWN])),
        reply("«Flood forecasting» is by Ana Cruz and Ben Reyes."),
    )
    corpus = Detailed()
    run(AgentExecutor(recording, PIN_13, RESERVES, profiles=PROFILES).answer(
        "Who wrote Flood forecasting?", corpus, context()))
    assert ("details", [handle("R", 1), UNKNOWN]) in corpus.calls
    body = sent(recording.requests[1], "d")
    assert body["status"] == "partial" and body["not_found"] == [UNKNOWN]
    (paper,) = body["details"]
    # The submitter typed every string here, so each is quoted as paper text, never an instruction.
    assert paper == {
        "paper": handle("R", 1), "title": quoted("Flood forecasting"),
        "authors": [quoted("Ana Cruz"), quoted("Ben Reyes")], "adviser": quoted("Carla Santos"),
        "year_completed": 2023, "year_accomplished": 2022, "publication_year": 2024,
        "record_type": "Thesis / Research", "classification": "Hydrology", "psced": "Engineering",
        "keywords": [quoted("floods"), quoted("neural networks")],
        "abstract": quoted("A neural network trained on 12 rain gauges predicted 87 floods."),
        "origin": "institutional", "is_ip": False, "ip_type": None, "for_commercialization": True,
        "community_extension": False, "requires_ethics_review": False, "requested_offices": ["KTTO"],
    }
    assert body["recorded_by"] == "submitter"


def test_a_detail_the_call_returned_may_be_stated_without_a_passage_handle():
    answer = ("«Flood forecasting» was completed in 2023, accomplished in 2022 and published in 2024. "
              "It is a «Thesis / Research» paper in «Hydrology».")
    recording = provider(tools(call("d", "paper_details", papers=[handle("R", 1)])), reply(answer))
    result = run(AgentExecutor(recording, PIN_13, RESERVES, profiles=PROFILES).answer(
        "When was Flood forecasting published?", Detailed(), context()))
    # No repair was asked for: every year and catalogue name came from the details.
    assert len(recording.requests) == 2
    assert result.answer == answer


def test_a_year_the_details_did_not_return_is_still_checked():
    recording = provider(
        tools(call("d", "paper_details", papers=[handle("R", 1)])),
        reply("«Flood forecasting» was published in 2019."),
        reply("«Flood forecasting» was published in 2024."),
    )
    run(AgentExecutor(recording, PIN_13, RESERVES, profiles=PROFILES).answer(
        "When was Flood forecasting published?", Detailed(), context()))
    # The made-up year failed the number check, so the draft was sent back once.
    assert len(recording.requests) == 3


def test_a_figure_from_the_abstract_still_needs_a_cited_passage():
    recording = provider(
        tools(call("d", "paper_details", papers=[handle("R", 1)])),
        reply("«Flood forecasting» predicted 87 floods."),
        reply("«Flood forecasting» reports predicted floods."),
    )
    run(AgentExecutor(recording, PIN_13, RESERVES, profiles=PROFILES).answer(
        "How many floods did Flood forecasting predict?", Detailed(), context()))
    # The abstract is what the submitter typed, not a passage read: its numbers are cited from the paper.
    assert len(recording.requests) == 3
