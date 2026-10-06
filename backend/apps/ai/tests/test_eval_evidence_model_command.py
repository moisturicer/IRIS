"""`eval_evidence --model-decision` reports the model's route beside the
detector's (IR-465, ADR-035 §10).

Offline: the root holds a `ScriptedToolCallingLLM`, so no vendor is called. The
properties that keep this the curated instrument rather than IR-466's shadow
pilot still hold with a model in the loop -- no `Conversation`, no `Turn`, no
shadow row -- and a hypothetical direct answer reaches neither the results file
nor the console.
"""

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.models import Conversation, Turn
from apps.ai.providers.fakes import ScriptedLLM, ScriptedToolCallingLLM

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

QUOTE = "the document stopped moving and nobody noticed that it had"
HYPOTHETICAL = "HYPOTHETICAL-ANSWER a median is the middle value"


def write_set(tmp_path, *questions):
    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps({"name": "curated-model", "tier": "proxy", "questions": list(questions)}),
        encoding="utf-8",
    )
    return str(path)


def grounded(qid, text):
    return {
        "id": qid,
        "question": text,
        "evidence_required": "corpus",
        "expected_outcome": "answer",
        "expected": [{"record": "A", "quote": QUOTE}],
    }


def direct(qid, text):
    return {
        "id": qid,
        "question": text,
        "evidence_required": "none",
        "expected_outcome": "answer",
        "expected": [],
    }


def route_by_word(request):
    if "paper" in request.user:
        return ScriptedToolCallingLLM.calling(arguments='{"query":"leaked"}')
    return ScriptedToolCallingLLM.answering(HYPOTHETICAL)


@pytest.fixture
def questions(tmp_path):
    return write_set(
        tmp_path,
        grounded("q1", "what did the paper find?"),
        direct("q2", "what is a median?"),
    )


@override_settings(AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",))
def test_the_model_route_is_reported_beside_the_detector(questions, capsys, tmp_path):
    fake = ScriptedToolCallingLLM(route_by_word)
    out = tmp_path / "runs"

    with use_composition_root(CompositionRoot(llm=fake)):
        call_command(
            "eval_evidence", "--questions", questions, "--model-decision", "--out", str(out)
        )

    console = capsys.readouterr().out
    assert "Detector - over-fires and misses per lane" in console
    assert "Model decision" in console
    assert "agreement" in console

    (written,) = out.glob("*-evidence-*.json")
    data = json.loads(written.read_text(encoding="utf-8"))
    assert data["model"]["questions"] == 2
    assert data["model"]["agreement_with_detector"]["agreement"] == 1.0
    assert data["provenance"]["model_decision"] is True
    assert data["provenance"]["model"] == "answer task"
    assert len(fake.tool_requests) == 2


@override_settings(AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",))
def test_it_still_creates_no_conversation_and_no_turn(questions):
    before = (Conversation.objects.count(), Turn.objects.count())

    with use_composition_root(CompositionRoot(llm=ScriptedToolCallingLLM(route_by_word))):
        call_command("eval_evidence", "--questions", questions, "--model-decision", "--no-write")

    assert (Conversation.objects.count(), Turn.objects.count()) == before == (0, 0)


@override_settings(AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",))
def test_no_hypothetical_answer_reaches_the_console_or_the_results_file(
    questions, capsys, tmp_path
):
    out = tmp_path / "runs"
    with use_composition_root(CompositionRoot(llm=ScriptedToolCallingLLM(route_by_word))):
        call_command(
            "eval_evidence", "--questions", questions, "--model-decision", "--out", str(out)
        )

    (written,) = out.glob("*-evidence-*.json")
    assert "HYPOTHETICAL" not in written.read_text(encoding="utf-8")
    console = capsys.readouterr().out
    assert "HYPOTHETICAL" not in console
    assert "none retained" in console
    assert "leaked" not in console


@override_settings(AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",))
def test_a_provider_that_cannot_carry_a_decision_is_refused(questions):
    with use_composition_root(CompositionRoot(llm=ScriptedLLM())):
        with pytest.raises(CommandError, match="cannot carry a tool-calling decision"):
            call_command(
                "eval_evidence", "--questions", questions, "--model-decision", "--no-write"
            )


@override_settings(AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",))
def test_no_configured_model_is_refused_rather_than_scored_as_all_fallbacks(
    questions, monkeypatch
):
    monkeypatch.setattr(CompositionRoot, "generation_configured", lambda self: False)

    with pytest.raises(CommandError, match="none is configured"):
        call_command(
            "eval_evidence", "--questions", questions, "--model-decision", "--no-write"
        )


@override_settings(AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",))
def test_without_the_flag_no_root_is_built(questions, monkeypatch):
    import apps.ai.composition as composition

    def explode(*args, **kwargs):
        raise AssertionError("a run without --model-decision built a composition root")

    monkeypatch.setattr(composition, "composition_root", explode)
    call_command("eval_evidence", "--questions", questions, "--no-write")
