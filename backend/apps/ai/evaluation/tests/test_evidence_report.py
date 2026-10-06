"""The curated instrument: per-rule over-fires, misses, coverage (IR-464).

ADR-035 §10. Pure: no database, no model, no vendor.
"""

import pytest

from apps.ai.evaluation.evidence import (
    LANE_COMBINED,
    LANE_RAW,
    LANE_RESOLVED,
    annotated,
    judge,
    run_curated,
)
from apps.ai.evaluation.labels import parse_question_set
from apps.ai.evidence.detector import EvidenceDetector
from apps.ai.evidence.rules import (
    AGGREGATE_SHAPE,
    DOCUMENT_REFERENCE,
    SCOPE_RECORD,
    SOURCING_DEMAND,
    build_rule_set,
)

QUOTE = "the document stopped moving and nobody noticed that it had"


@pytest.fixture
def detector():
    return EvidenceDetector(build_rule_set(institution_terms=("CIT-U",)))


def question(qid, text, evidence, outcome="answer", **extra):
    body = {
        "id": qid,
        "question": text,
        "evidence_required": evidence,
        "expected_outcome": outcome,
        **extra,
    }
    body.setdefault(
        "expected",
        [] if evidence == "none" else [{"record": "A", "quote": QUOTE}],
    )
    return body


def question_set(*questions, name="t"):
    return parse_question_set({"name": name, "questions": list(questions)})


# -- what gets judged ------------------------------------------------------


def test_only_annotated_questions_are_judged(detector):
    given = question_set(
        question("q1", "what did the paper find?", "corpus", kind="mechanism"),
        {"id": "q2", "question": "unlabelled", "expected": [
            {"record": "A", "quote": QUOTE}
        ]},
    )
    assert [q.id for q in annotated(given)] == ["q1"]

    report = run_curated(detector, given)
    assert report.coverage == {
        "questions_in_set": 2,
        "annotated": 1,
        "annotated_fraction": 0.5,
        "with_resolved_question": 0,
        "unannotated": 1,
    }


def test_a_question_set_with_no_annotation_produces_no_judgement(detector):
    given = question_set(
        {"id": "q1", "question": "x", "expected": [{"record": "A", "quote": QUOTE}]}
    )
    assert run_curated(detector, given).judgements == ()


# -- over-fires and misses, per rule and per lane --------------------------


def test_an_over_fire_is_attributed_to_the_rule_that_caused_it(detector):
    report = run_curated(
        detector,
        question_set(
            question("over", "which papers are the most cited?", "none", "clarify"),
        ),
    )
    raw = report.lane(LANE_RAW)
    assert raw.over_fires == ("over",)
    assert raw.misses == ()
    by_code = {tally.code: tally for tally in raw.rules}
    assert by_code[AGGREGATE_SHAPE].over_fires == ("over",)
    assert by_code[DOCUMENT_REFERENCE].over_fires == ("over",)
    assert by_code[SOURCING_DEMAND].over_fires == ()


def test_a_miss_is_only_a_detector_miss_on_the_combined_lane(detector):
    """A rule being silent on a question it does not describe is the rule
    working; only the OR of all of them can miss."""
    report = run_curated(
        detector,
        question_set(question("miss", "what exactly did they say?", "corpus")),
    )
    combined = report.lane(LANE_COMBINED)
    assert combined.misses == ("miss",)
    by_code = {tally.code: tally for tally in combined.rules}
    assert by_code[SCOPE_RECORD].silent_on_required == ("miss",)
    assert by_code[AGGREGATE_SHAPE].silent_on_required == ("miss",)


def test_the_resolved_lane_covers_only_questions_carrying_one(detector):
    report = run_curated(
        detector,
        question_set(
            question(
                "q1",
                "what exactly did they say about that?",
                "corpus",
                resolved_question="what did the authors say about Pareto fronts?",
            ),
            question("q2", "what did the paper find?", "corpus"),
        ),
    )
    assert report.lane(LANE_RAW).judged == ("q1", "q2")
    assert report.lane(LANE_RESOLVED).judged == ("q1",)
    assert report.coverage["with_resolved_question"] == 1


def test_the_combined_lane_is_the_or_of_the_two(detector):
    report = run_curated(
        detector,
        question_set(
            question(
                "q1",
                "what exactly did they say about that?",
                "corpus",
                resolved_question="what did the authors say about Pareto fronts?",
            ),
        ),
    )
    assert report.lane(LANE_RAW).misses == ("q1",)
    assert report.lane(LANE_RESOLVED).misses == ()
    assert report.lane(LANE_COMBINED).misses == ()
    assert report.lane(LANE_COMBINED).accuracy == 1.0


def test_an_undetermined_verdict_is_reported_as_such(detector):
    report = run_curated(
        detector, question_set(question("q1", "   ?   ", "none", "clarify"))
    )
    combined = report.lane(LANE_COMBINED)
    # "?" normalizes away entirely, so the question is unreadable and the
    # detector fails safe to a requirement -- counted as an over-fire, and
    # named so the reason is not mistaken for a rule firing.
    assert combined.undetermined == ("q1",)
    assert combined.over_fires == ("q1",)
    assert combined.rules[0].fired == ()


# -- categories and the institutional column -------------------------------


def test_a_category_with_too_few_examples_is_inconclusive(detector):
    report = run_curated(
        detector,
        question_set(
            question("q1", "what did the paper find?", "corpus", kind="mechanism"),
            question("q2", "what is a median?", "none", "answer", kind="general"),
        ),
        min_examples=2,
    )
    categories = {c.kind: c for c in report.categories}
    assert categories["mechanism"].inconclusive is True
    assert categories["general"].inconclusive is True
    assert report.inconclusive_categories == ("general", "mechanism")


def test_a_category_at_the_threshold_is_not_inconclusive(detector):
    report = run_curated(
        detector,
        question_set(
            *[
                question(f"q{i}", "what did the paper find?", "corpus", kind="m")
                for i in range(3)
            ]
        ),
        min_examples=3,
    )
    assert report.inconclusive_categories == ()
    assert report.categories[0].accuracy == 1.0


def test_institutional_questions_are_reported_separately(detector):
    report = run_curated(
        detector,
        question_set(
            question(
                "inst",
                "what exactly did they say?",
                "corpus",
                institutional=True,
            ),
            question("other", "what did the paper find?", "corpus"),
        ),
    )
    assert report.institutional == {"judged": 1, "incorrect": ["inst"]}


# -- the scope rule --------------------------------------------------------


def test_a_record_scoped_question_always_carries_scope_record(detector):
    given = question_set(question("q1", "what is the colour of the sky?", "none"))
    judgement = judge(detector, annotated(given)[0], record_scoped=True)
    assert judgement.combined.evidence_required
    assert SCOPE_RECORD in judgement.combined.codes


# -- what the report keeps apart -------------------------------------------


def test_model_decisions_are_a_separate_section_and_are_empty(detector):
    """ADR-035 §10: the curated set supplies accuracy, the shadow pilot
    supplies operational figures, and this command calls no model at all."""
    report = run_curated(
        detector, question_set(question("q1", "what did the paper find?", "corpus"))
    )
    data = report.as_dict()
    assert data["model"] is None
    assert set(data["detector"]) == {"lanes", "categories", "institutional"}
    assert data["instrument"] == "curated"


def test_the_report_records_the_rule_set_digest_it_was_produced_under(detector):
    report = run_curated(
        detector, question_set(question("q1", "what did the paper find?", "corpus"))
    )
    assert report.rule_set_digest == detector.rule_set.digest
    assert report.as_dict()["rule_set"]["definition"]["rules"]


def test_the_report_renders_without_a_resolved_question(detector):
    report = run_curated(
        detector, question_set(question("q1", "what did the paper find?", "corpus"))
    )
    rendered = report.render()
    assert "resolved lane: no question carries one." in rendered
    assert "Model decisions: none" in rendered
