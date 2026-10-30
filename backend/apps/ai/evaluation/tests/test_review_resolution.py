"""IR-607: two independent reviews, an adjudicated verdict, and human-only verdicts. Pure."""

import pytest

from apps.ai.evaluation.conversation_scoring import ScoringError, score_reviews

from .test_conversation_scoring import data, review


def test_two_agreeing_independent_reviews_count_once_and_both_stay_on_record():
    out = score_reviews(data(), [review("c0"), review("c0", reviewer="Bo")], arm="current")
    assert out["overall"]["reviewed"] == 1
    assert out["overall"]["task_completion"]["denominator"] == 1
    audit = out["review_audit"]["c0"]
    assert audit["resolution"] == "agreed" and audit["reviewers"] == ["Ana", "Bo"]
    assert len(audit["records"]) == 2


def test_a_disagreement_needs_an_adjudicated_verdict_that_keeps_both_reviews():
    first = review("c0", task_completion="yes")
    second = review("c0", reviewer="Bo", task_completion="partial")
    with pytest.raises(ScoringError, match="adjudicat"):
        score_reviews(data(), [first, second], arm="current")
    verdict = review("c0", reviewer="Cy", role="adjudication", task_completion="partial")
    out = score_reviews(data(), [first, second, verdict], arm="current")
    assert out["overall"]["task_completion"]["numerator"] == 0
    assert out["overall"]["partial"]["numerator"] == 1
    audit = out["review_audit"]["c0"]
    assert audit["resolution"] == "adjudicated" and audit["adjudicated_by"] == "Cy"
    assert [r["task_completion"] for r in audit["records"]] == ["yes", "partial", "partial"]


def test_one_person_cannot_be_both_independent_reviewers():
    with pytest.raises(ScoringError, match="independent"):
        score_reviews(data(), [review("c0"), review("c0")], arm="current")


def test_an_adjudication_needs_two_independent_reviews():
    with pytest.raises(ScoringError, match="two independent"):
        score_reviews(data(), [review("c0"), review("c0", reviewer="Cy", role="adjudication")],
                      arm="current")


def test_an_adjudication_is_finished_and_by_a_third_person():
    pair = [review("c0"), review("c0", reviewer="Bo", task_completion="no")]
    pending = {"conversation": "c0", "arm": "current", "reviewer": "Cy", "rubric_version": 1,
               "role": "adjudication", "status": "not_reviewed"}
    with pytest.raises(ScoringError, match="not finished"):
        score_reviews(data(), [*pair, pending], arm="current")
    with pytest.raises(ScoringError, match="adjudicator"):
        score_reviews(data(), [*pair, review("c0", reviewer="Bo", role="adjudication")],
                      arm="current")


def test_a_claim_without_explicit_support_judgments_is_refused():
    for claim in ({"citation_correct": True, "page_correct": True},
                  {"supported": True, "page_correct": None},
                  {"supported": True, "citation_correct": True, "page_correct": "maybe"}):
        with pytest.raises(ScoringError, match="claim"):
            score_reviews(data(), [review("c0", claims=[claim])], arm="current")


def test_a_model_judge_or_automated_trace_cannot_supply_a_verdict():
    for kind in ("model_judge", "automated_trace"):
        with pytest.raises(ScoringError, match="human"):
            score_reviews(data(), [review("c0", reviewer_kind=kind)], arm="current")
    with pytest.raises(ScoringError, match="human"):
        score_reviews(data(), [review("c0"), review("c0", reviewer="judge", role="adjudication",
                                                    reviewer_kind="model_judge")],
                      arm="current")


def test_not_reviewed_is_explicit_and_leaves_every_denominator():
    pending = {"conversation": "c1", "arm": "current", "reviewer": "Ana",
               "rubric_version": 1, "status": "not_reviewed"}
    out = score_reviews(data(), [review("c0"), pending], arm="current")
    assert out["overall"]["reviewed"] == 1
    assert out["overall"]["task_completion"]["denominator"] == 1
    assert out["not_reviewed"] == ["c1"]


def test_a_reviewed_record_states_clarification_and_access_safety_explicitly():
    for field in ("access_breach", "unnecessary_clarification"):
        bare = review("c0")
        del bare[field]
        with pytest.raises(ScoringError, match=field):
            score_reviews(data(), [bare], arm="current")
