"""A vague question may be searched without penalty (IR-467).

An `ambiguous` question is too vague to answer, so the right reply is a
clarifying question and a retrieval beforehand is not an error. Answering
directly stays correct, and every other kind is scored exactly as before.
"""

import json

import pytest
from django.test import override_settings

from apps.ai.evaluation import load_question_set
from apps.ai.evaluation.evidence import SEARCH_TOLERATED_KINDS, run_curated
from apps.ai.evidence import active_rule_set
from apps.ai.evidence.detector import EvidenceDetector
from apps.ai.evidence.model_decision import ModelEvidenceDecision
from apps.ai.providers.fakes import ScriptedToolCallingLLM


def _q(qid, text, kind):
    return {
        "id": qid,
        "kind": kind,
        "question": text,
        "evidence_required": "none",
        "expected_outcome": "clarify" if kind == "ambiguous" else "answer",
        "expected": [],
    }


@pytest.fixture
def run(tmp_path):
    path = tmp_path / "q.json"
    path.write_text(
        json.dumps(
            {
                "name": "t",
                "tier": "proxy",
                "questions": [
                    _q("vague", "which paper is better?", "ambiguous"),
                    _q("plain", "which paper is better?", "general-knowledge"),
                ],
            }
        ),
        encoding="utf-8",
    )

    def go(script):
        with override_settings(AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",)):
            return run_curated(
                EvidenceDetector(active_rule_set()),
                load_question_set(str(path)),
                decider=ModelEvidenceDecision(ScriptedToolCallingLLM(script)),
            )

    return go


def test_only_ambiguous_is_tolerated():
    assert SEARCH_TOLERATED_KINDS == ("ambiguous",)


def test_the_detector_requiring_evidence_on_a_vague_question_is_not_an_over_fire(run):
    report = run(lambda request: ScriptedToolCallingLLM.calling())
    raw = report.lane("raw")

    assert "vague" not in raw.over_fires
    assert "plain" in raw.over_fires
    assert all("vague" not in rule.over_fires for rule in raw.rules)


def test_the_model_searching_on_a_vague_question_is_correct_and_elsewhere_it_is_not(run):
    model = run(lambda request: ScriptedToolCallingLLM.calling()).model

    assert model.alone["over_searches"] == ["plain"]
    assert model.union["over_searches"] == ["plain"]
    assert model.decided["correct"] == 1


def test_answering_a_vague_question_directly_is_still_correct(run):
    report = run(lambda request: ScriptedToolCallingLLM.answering("hypothetical"))

    assert report.model.alone["missed_searches"] == []
    assert report.judgements[0].correct("raw") is not False


def test_the_scoring_rule_is_written_into_the_results_file(run):
    data = run(lambda request: ScriptedToolCallingLLM.calling()).as_dict()

    assert data["scoring"] == {"search_tolerated_kinds": ["ambiguous"]}
    assert data["questions"][0]["search_tolerated"] is True
    assert data["questions"][1]["search_tolerated"] is False
