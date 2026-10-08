"""The threshold curve of a probability-returning decision (IR-482).

Missed searches over the evidence-required questions and over-searches over the
rest, at every threshold, by category -- and **no operating point chosen**.
A fallback is a search at every threshold, so it can only ever be an
over-search.
"""

import pytest

from apps.ai.evaluation.evidence import THRESHOLDS, run_curated
from apps.ai.evaluation.labels import parse_question_set
from apps.ai.evidence.detector import EvidenceDetector
from apps.ai.evidence.jev_noul import JevNoulDecision
from apps.ai.evidence.rules import build_rule_set
from apps.ai.providers.decisions import DecisionUnavailable, ScriptedDecisionModel
from apps.ai.providers.errors import ErrorKind

pytestmark = pytest.mark.django_required

QUOTE = "the document stopped moving and nobody noticed that it had"


def q(qid, text, evidence, kind=None):
    return {
        "id": qid,
        "question": text,
        "evidence_required": evidence,
        "expected_outcome": "answer",
        "expected": [] if evidence == "none" else [{"record": "A", "quote": QUOTE}],
        **({"kind": kind} if kind else {}),
    }


@pytest.fixture
def detector():
    return EvidenceDetector(build_rule_set(institution_terms=("CIT-U",)))


def report(detector, steps, *items):
    qs = parse_question_set({"name": "t", "questions": list(items)})
    decider = JevNoulDecision(ScriptedDecisionModel(*steps))
    return run_curated(detector, qs, decider=decider)


@pytest.fixture
def curve_report(detector):
    #            p     needs corpus?
    # a  0.95  corpus    -> found at every threshold up to 0.95
    # b  0.40  corpus    -> missed from 0.45 up
    # c  0.10  corpus    -> missed from 0.15 up
    # d  0.60  none      -> an over-search up to 0.60
    # e  0.02  none      -> never an over-search
    # f  fallback none   -> an over-search at every threshold
    return report(
        detector,
        [0.95, 0.40, 0.10, 0.60, 0.02, DecisionUnavailable("429", kind=ErrorKind.RATE_LIMIT)],
        q("a", "what did they find?", "corpus", kind="factual"),
        q("b", "what else did they find?", "corpus", kind="factual"),
        q("c", "how many samples?", "corpus", kind="numeric"),
        q("d", "what is a mean?", "none", kind="general"),
        q("e", "what is a median?", "none", kind="general"),
        q("f", "what is a mode?", "none", kind="general"),
    )


def row(model, threshold):
    (match,) = [r for r in model.curve if r["threshold"] == pytest.approx(threshold)]
    return match


class TheCurveTests:
    def test_the_thresholds_are_a_fixed_grid_of_nineteen(self):
        assert THRESHOLDS[0] == pytest.approx(0.05)
        assert THRESHOLDS[-1] == pytest.approx(0.95)
        assert len(THRESHOLDS) == 19

    def test_missed_searches_rise_with_the_threshold(self, curve_report):
        model = curve_report.model

        assert row(model, 0.10)["missed_searches"] == []
        assert row(model, 0.15)["missed_searches"] == ["c"]
        assert row(model, 0.40)["missed_searches"] == ["c"]
        assert row(model, 0.45)["missed_searches"] == ["b", "c"]
        assert row(model, 0.50)["missed_searches"] == ["b", "c"]
        assert row(model, 0.95)["missed_searches"] == ["b", "c"]

    def test_a_probability_equal_to_the_threshold_is_a_search(self, curve_report):
        assert "a" not in row(curve_report.model, 0.95)["missed_searches"]

    def test_over_searches_fall_with_the_threshold(self, curve_report):
        model = curve_report.model

        assert row(model, 0.05)["over_searches"] == ["d", "f"]
        assert row(model, 0.60)["over_searches"] == ["d", "f"]
        assert row(model, 0.65)["over_searches"] == ["f"]

    def test_a_fallback_is_a_search_at_every_threshold_so_never_a_miss(self, curve_report):
        for r in curve_report.model.curve:
            assert "f" in r["over_searches"]
            assert "f" not in r["missed_searches"]

    def test_counts_are_by_category(self, curve_report):
        r = row(curve_report.model, 0.50)

        assert r["missed_by_kind"] == {"factual": 1, "numeric": 1}
        assert r["over_by_kind"] == {"general": 2}

    def test_the_union_curve_uses_the_detector_as_a_floor(self, detector):
        # "CIT-U" is an institution term: the detector fires although p is low.
        model = report(
            detector,
            [0.01],
            q("a", "what is CIT-U research output?", "corpus"),
        ).model

        assert row(model, 0.50)["missed_searches"] == ["a"]
        assert row(model, 0.50)["union_missed_searches"] == []

    def test_no_operating_point_is_chosen_anywhere(self, curve_report):
        data = curve_report.model.as_dict()

        assert data["operating_point"] is None
        assert data["reference_threshold"] == 0.5
        assert "no operating point chosen" in curve_report.render()

    def test_the_totals_the_curve_is_measured_over_are_reported(self, curve_report):
        data = curve_report.model.as_dict()["threshold_curve"]

        assert data["evidence_required"] == 3
        assert data["no_evidence_needed"] == 3

    def test_every_decision_carries_its_probability_in_the_run_file(self, curve_report):
        rows = curve_report.model.as_dict()["per_question"]
        assert [r["probability"] for r in rows] == [0.95, 0.4, 0.1, 0.6, 0.02, None]

    def test_a_mode_without_probabilities_has_no_curve(self, detector):
        from apps.ai.evidence.model_decision import ModelEvidenceDecision
        from apps.ai.providers.fakes import ScriptedToolCallingLLM

        qs = parse_question_set({"name": "t", "questions": [q("a", "what did they find?", "corpus")]})
        decider = ModelEvidenceDecision(
            ScriptedToolCallingLLM(lambda request: ScriptedToolCallingLLM.calling())
        )
        data = run_curated(detector, qs, decider=decider).model.as_dict()

        assert "threshold_curve" not in data
