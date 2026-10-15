"""IR-594: the validated answer at the chat boundary, fakes only.

A06, A07, A09, A10 and invalid citations, asserted on the final public
payload and the stored Turn.
"""
import json

import pytest

from apps.ai.composition import use_composition_root
from apps.ai.models import ResearchRun, Turn
from apps.ai.providers.fakes import ScriptedLLM, ScriptedToolCallingLLM

from .test_controller_http import asked_flood, budget, call, compose, controller_root, flood_scene  # noqa: F401

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

INTERNAL = ("search_research", "aggregate_records", "bindings", "unsupported_number",
            "repaired", "tool_call", "planner")


class Replies(ScriptedLLM):
    def __init__(self, *replies):
        super().__init__()
        self.replies = list(replies)

    def generate(self, system, user):
        self.calls.append((system, user))
        return self.replies.pop(0)


def searched(monkeypatch, embedder, writer, *extra):
    planner = ScriptedToolCallingLLM([
        call("search_research", {"query": "flood prediction", "target": "passages"}, "c1"),
        *extra, compose(basis="evidence"),
    ])
    return controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)


@pytest.mark.parametrize("endpoint", ["ai-ask", "ai-ask-stream"])
def test_an_unsupported_number_is_repaired_once_and_no_internal_wording_is_published(
    endpoint, flood_scene, monkeypatch, embedder,
):
    """A10: the repaired answer is what the reader and the Turn receive."""
    writer = Replies("Flood Prediction reports 97% accuracy [1].",
                     'Flood Prediction forecasts river levels [1].\n```bindings\n'
                     '{"summary": "Only one paper addresses forecasting here."}\n```')
    root = searched(monkeypatch, embedder, writer)
    with use_composition_root(root):
        body = asked_flood(flood_scene["client"], flood_scene["conversation"], endpoint)

    assert body["answer"] == "Flood Prediction forecasts river levels [1]."
    assert [c["record_id"] for c in body["citations"]] == [flood_scene["flood"].pk]
    published = json.dumps(body)
    assert "97%" not in published
    assert not any(word in published for word in INTERNAL)
    assert len(writer.calls) == 2
    assert Turn.objects.get(conversation=flood_scene["conversation"]).answer == body["answer"]
    run = ResearchRun.objects.get(conversation=flood_scene["conversation"])
    assert run.validation_codes == ["repaired"]


def test_an_invented_citation_that_survives_repair_is_removed_with_a_plain_note(
    flood_scene, monkeypatch, embedder,
):
    bad = "Flood Prediction forecasts river levels [1]. A second study agrees [4]."
    writer = Replies(bad, bad)
    root = searched(monkeypatch, embedder, writer)
    with use_composition_root(root):
        body = asked_flood(flood_scene["client"], flood_scene["conversation"])

    assert body["answer"].startswith("Flood Prediction forecasts river levels [1].")
    assert "[4]" not in body["answer"] and "second study" not in body["answer"]
    assert "left out" in body["answer"]


def test_a_wrong_count_is_corrected_against_the_computed_fact(flood_scene, monkeypatch, embedder):
    """A06: the metadata count is code-owned; the prose must state it."""
    planner = ScriptedToolCallingLLM([
        call("aggregate_records", {"operation": "count"}, "c1"), compose(basis="evidence"),
    ])
    writer = Replies("There are 5 papers visible to you.",
                     'There are 2 papers visible to you.\n```bindings\n'
                     '{"facts": [{"value": 2, "fact": "total"}]}\n```')
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    with use_composition_root(root):
        body = asked_flood(flood_scene["client"], flood_scene["conversation"])

    assert body["answer"] == "There are 2 papers visible to you."
    assert "unsupported_count" not in json.dumps(body)


def test_a_two_paper_comparison_table_is_delivered_whole(flood_scene, monkeypatch, embedder):
    """A07: a two-paper table passes when every figure is its own paper's."""
    from .corpus import FLOOD_TEXT, POND_TEXT

    table = ("| Paper | Focus |\n|---|---|\n| Flood Prediction | river levels [1] |\n"
             "| Tilapia ponds | brackish water [2] |\n\n"
             "The two address different problems, so their results are not directly comparable [1] [2].")
    planner = ScriptedToolCallingLLM([
        call("search_research", {"query": "flood prediction", "target": "passages"}, "c1"),
        call("search_research", {"query": "tilapia ponds", "target": "passages"}, "c2"),
        compose(basis="evidence"),
    ])
    writer = Replies(table)
    root = controller_root(monkeypatch, embedder=embedder, planner=planner, writer=writer)
    with use_composition_root(root):
        body = asked_flood(flood_scene["client"], flood_scene["conversation"])

    assert FLOOD_TEXT and POND_TEXT
    assert body["answer"] == table and len(writer.calls) == 1
    assert "two or more papers" in writer.calls[0][0]


def test_a_model_outage_returns_sources_and_no_findings(flood_scene, monkeypatch, embedder):
    """A09: unavailable is explicit; the passages found stay readable."""
    from apps.ai.providers.openai_compatible import LLMUnavailable

    class Down(ScriptedLLM):
        def generate(self, system, user):
            raise LLMUnavailable("answer down")

    root = searched(monkeypatch, embedder, Down())
    with use_composition_root(root):
        body = asked_flood(flood_scene["client"], flood_scene["conversation"])

    assert body["mode"] != "generated"
    assert body["citations"] == [] and body["sources"]
    assert "unavailable" in json.dumps(body).lower()
