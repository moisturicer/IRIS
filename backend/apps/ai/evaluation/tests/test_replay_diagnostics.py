"""IR-607: private diagnostics tell a lost hand-off from an empty search or an outage."""

import json

import pytest

from apps.ai.composition import use_composition_root
from apps.ai.controller.budget import FAKE_TEST_PROFILE
from apps.ai.evaluation.replay import ResearchDiagnostics, collect_case
from apps.ai.providers.fakes import ScriptedLLM, ScriptedToolCallingLLM
from apps.ai.research.tests.conftest import fresh_vector_indexes
from apps.ai.tests.corpus import FLOOD_TEXT, make_record, make_user
from apps.ai.tests.test_controller_http import call, compose, controller_root
from apps.records.models import Record

from .test_replay import Reader

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

CASE = {"id": "dev-diag", "family": "A09", "split": "development",
        "turns": [{"user": "Any papers about floods?"}]}


@pytest.fixture
def empty(settings):
    for name, value in FAKE_TEST_PROFILE.items():
        setattr(settings, name, value)
    settings.AI_DURABLE_ASK = False
    fresh_vector_indexes()


@pytest.fixture
def scene(empty, embedder, space):
    make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)


def replay(monkeypatch, embedder, client_for, email, planner, *, diagnostics=True):
    root = controller_root(monkeypatch, embedder=embedder, planner=planner,
                           writer=ScriptedLLM(reply="Should not be reached [1]."))
    with use_composition_root(root):
        return collect_case(Reader(client_for(make_user(email))), CASE,
                            diagnostics=ResearchDiagnostics() if diagnostics else None)


def test_candidates_found_then_no_results_is_a_handoff_failure(
    scene, monkeypatch, embedder, client_for,
):
    # IR-703: a found paper's abstract is now a source, so only a paper with
    # nothing citable leaves the handoff empty; so is its best passage.
    from apps.ai.research.tools import search
    monkeypatch.setattr(search, "BEST_PASSAGES", 0)
    Record.objects.filter(title="Flood Prediction").update(abstract="")
    planner = ScriptedToolCallingLLM([
        call("search_research", {"query": "flood", "target": "papers"}, "c1"),
        compose(basis="evidence"),
    ])
    turn = replay(monkeypatch, embedder, client_for, "diag-handoff@cit.edu", planner)["turns"][0]
    assert turn["diagnostics"]["stage"] == "candidates_then_no_results"
    assert turn["diagnostics"]["candidate_steps"] >= 1


def test_no_candidate_is_not_a_handoff_failure(empty, monkeypatch, embedder, client_for):
    planner = ScriptedToolCallingLLM([
        call("search_research", {"query": "flood", "target": "papers"}, "c1"),
        compose(basis="evidence"),
    ])
    turn = replay(monkeypatch, embedder, client_for, "diag-empty@cit.edu", planner)["turns"][0]
    assert turn["diagnostics"]["stage"] == "no_candidates"
    assert turn["diagnostics"]["candidate_steps"] == 0


def test_provider_failure_is_its_own_stage(scene, monkeypatch, embedder, client_for):

    class Down(ScriptedToolCallingLLM):
        def converse_with_tools(self, *args, **kwargs):
            from apps.ai.providers.openai_compatible import LLMUnavailable
            raise LLMUnavailable("down")

    turn = replay(monkeypatch, embedder, client_for, "diag-down@cit.edu", Down([]))["turns"][0]
    assert turn["diagnostics"]["stage"] == "provider_failure"


def test_diagnostics_do_not_change_the_reader_response(
    scene, monkeypatch, embedder, client_for,
):
    def planner():
        return ScriptedToolCallingLLM([
            call("search_research", {"query": "flood", "target": "papers"}, "c1"),
            compose(basis="evidence"),
        ])

    traced = replay(monkeypatch, embedder, client_for, "diag-a@cit.edu", planner())
    plain = replay(monkeypatch, embedder, client_for, "diag-b@cit.edu", planner(),
                   diagnostics=False)
    def reader_view(result):
        return {k: v for k, v in result["turns"][0]["public_answer"].items()
                if k != "conversation_id"}

    assert reader_view(traced) == reader_view(plain)
    assert plain["turns"][0]["diagnostics"] == {"stage": "not_traced"}
    public = json.dumps(traced["turns"][0]["public_answer"])
    assert "candidates_then_no_results" not in public and "search_research" not in public
