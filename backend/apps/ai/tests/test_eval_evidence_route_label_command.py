"""`eval_evidence --model-decision --decision-mode route-label` (IR-481).

Offline: the root holds a plain `ScriptedLLM`, so no vendor is called and no
tool is offered. The curated-instrument properties still hold: no
`Conversation`, `Turn` or shadow row, and the provenance records the prompt
hash, the mode and the generation parameters.
"""

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.evidence.route_label import ROUTE_LABEL_MAX_TOKENS, route_label_digest
from apps.ai.models import Conversation, Turn
from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.tests.test_eval_evidence_model_command import direct, grounded, write_set

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


class ByWord(ScriptedLLM):
    def generate(self, system, user):
        self.calls.append((system, user))
        return '{"route":"search"}' if "paper" in user else '{"route":"answer"}'


@pytest.fixture
def questions(tmp_path):
    return write_set(
        tmp_path,
        grounded("q1", "what did the paper find?"),
        direct("q2", "what is a median?"),
    )


def run(questions, *extra, llm=None):
    with use_composition_root(CompositionRoot(llm=llm or ByWord())):
        call_command(
            "eval_evidence", "--questions", questions, "--model-decision",
            "--decision-mode", "route-label", *extra,
        )


@override_settings(AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",))
def test_the_label_route_is_reported_and_the_provenance_is_recorded(
    questions, tmp_path, capsys
):
    out = tmp_path / "runs"
    llm = ByWord()
    run(questions, "--out", str(out), llm=llm)

    (written,) = out.glob("*-evidence-*.json")
    data = json.loads(written.read_text(encoding="utf-8"))
    prov = data["provenance"]
    assert data["model"]["questions"] == 2 and data["model"]["fallbacks"] == 0
    assert data["model"]["model_alone"]["correct"] == 2
    assert prov["decision_mode"] == "route-label"
    assert prov["prompt_digest"] == route_label_digest(ROUTE_LABEL_MAX_TOKENS)
    assert prov["generation"]["max_tokens"] == ROUTE_LABEL_MAX_TOKENS
    assert prov["workers"] == 1
    assert len(llm.calls) == 2
    assert "Model decision" in capsys.readouterr().out


@override_settings(AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",))
def test_a_malformed_label_is_a_counted_fallback(questions, tmp_path):
    out = tmp_path / "runs"
    run(questions, "--out", str(out), llm=ScriptedLLM(reply="search"))

    (written,) = out.glob("*-evidence-*.json")
    model = json.loads(written.read_text(encoding="utf-8"))["model"]
    assert model["fallbacks"] == 2
    assert model["reasons"]["invalid_json"] == 2


@override_settings(AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",))
def test_it_creates_no_conversation_and_no_turn(questions):
    run(questions, "--no-write")
    assert (Conversation.objects.count(), Turn.objects.count()) == (0, 0)


@override_settings(AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",))
def test_the_mode_needs_model_decision(questions):
    with pytest.raises(CommandError, match="needs --model-decision"):
        call_command(
            "eval_evidence", "--questions", questions,
            "--decision-mode", "route-label", "--no-write",
        )
