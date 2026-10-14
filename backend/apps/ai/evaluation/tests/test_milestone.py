"""IR-550: scoring the first fixed-workflow milestone against pinned labels.

Pure: no database and no vendor. Each measure has its own denominator and
its own ground truth, and nothing is folded into one score. The labels are
the fixed-workflow baseline fixture's; the observations are what a run's
`done` events carried, keyed by fixture record key.
"""

import copy
import json
from pathlib import Path

import pytest

from apps.ai.evaluation.milestone import (
    MilestoneSetError,
    Observation,
    held_out_digest,
    parse_milestone_set,
    score,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "fixed_workflow_baseline.json"
BASELINE = json.loads(FIXTURE.read_text())


def _set(**split):
    data = copy.deepcopy(BASELINE)
    if split:
        data["split"] = split
    return parse_milestone_set(data)


def _row(key, state, restricted=False):
    if restricted:
        return {"record_key": key, "state": "unassessed", "restricted": True}
    return {"record_key": key, "state": state}


#: What a correct workflow returns for S0 (README §2, the cases' `contract`).
TOPIC_ROWS = [
    _row("flood-gauges", "included"), _row("flood-hazard", "included"),
    _row("tilapia", "excluded"), _row("rainfall-note", "uncertain"),
    _row("flood-warning", "unassessed", restricted=True),
]


def _topic(case_id, rows=TOPIC_ROWS, **extra):
    included = sum(r["state"] == "included" for r in rows)
    judged = sum(r["state"] in ("included", "excluded", "uncertain") for r in rows)
    listing = {"completeness": "matches_found" if judged or not rows else "inconclusive",
               "candidates": rows,
               "coverage": {"selected": len(rows), "limit": 20}}
    if case_id == "b02":
        listing["topic_count"] = {"matches": included, "assessed": judged}
    return Observation(case_id=case_id, mode="generative", listing=listing, **extra)


def _count(n):
    return Observation(case_id="b01", mode="generative",
                       listing={"completeness": "exact_count", "count": {"total": n}})


def _correct():
    return [_count(5), _topic("b02"), _topic("b03")]


def test_only_the_first_milestone_families_are_scored_and_the_rest_are_named():
    report = score(_set(), _correct(), tier="synthetic")
    assert report["scope"]["scored_cases"] == ["b01", "b02", "b03"]
    assert set(report["scope"]["out_of_milestone"]) == {"b04", "b05", "b06", "b07"}


def test_a_metadata_count_is_checked_against_the_population_not_the_workflow():
    report = score(_set(), [_count(6), _topic("b02"), _topic("b03")], tier="synthetic")
    counts = report["metadata_counts"]
    assert counts["denominator"] == 1
    assert counts["exact"] == 0
    assert counts["wrong"] == [{"case": "b01", "expected": 5, "reported": 6}]


def test_a_contract_count_that_disagrees_with_its_population_is_refused():
    data = copy.deepcopy(BASELINE)
    data["cases"][0]["contract"]["count"] = 4
    with pytest.raises(MilestoneSetError, match="b01"):
        parse_milestone_set(data)


def test_a_case_with_no_observation_counts_as_missing_not_as_correct():
    report = score(_set(), [_topic("b02"), _topic("b03")], tier="synthetic")
    assert report["metadata_counts"]["denominator"] == 1
    assert report["metadata_counts"]["missing"] == ["b01"]
    assert report["metadata_counts"]["exact"] == 0


def test_screening_precision_and_recall_are_over_assessed_candidates_with_a_human_label():
    rows = [_row("flood-gauges", "included"), _row("flood-hazard", "excluded"),
            _row("tilapia", "included"), _row("rainfall-note", "included"),
            _row("flood-warning", "unassessed", restricted=True)]
    report = score(_set(), [_count(5), _topic("b02", rows), _topic("b03")], tier="synthetic")
    b02 = report["screening"]["by_case"]["b02"]
    # rainfall-note is labelled uncertain, so it sits outside both denominators.
    assert b02["precision"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert b02["recall"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert b02["outside_denominators"] == {"label_uncertain": 1, "unlabelled": 0, "screener_uncertain": 0,
                                           "not_assessed": 1}


def test_candidate_recall_uses_every_relevant_record_the_asker_can_see_as_its_denominator():
    rows = [_row("flood-gauges", "included"), _row("tilapia", "excluded")]
    report = score(_set(), [_count(5), _topic("b02", rows), _topic("b03")], tier="synthetic")
    recall = report["candidate_recall"]["by_case"]["b02"]
    # flood-gauges, flood-hazard and flood-warning are relevant and visible;
    # flood-draft is relevant but invisible to the asker, so it is not owed.
    assert recall["denominator"] == 3
    assert recall["numerator"] == 1
    assert recall["missed"] == ["flood-hazard", "flood-warning"]
    eligible = report["candidate_recall"]["ai_eligible_by_case"]["b02"]
    assert (eligible["numerator"], eligible["denominator"]) == (1, 2)


def test_a_listed_record_the_asker_cannot_see_is_a_visibility_breach():
    rows = TOPIC_ROWS + [_row("flood-draft", "included")]
    report = score(_set(), [_count(5), _topic("b02", rows), _topic("b03")], tier="synthetic")
    assert report["breaches"] == [{"case": "b02", "record_key": "flood-draft",
                                   "why": "not in the asker's metadata population"}]


def test_a_restricted_record_that_is_named_or_judged_is_a_breach():
    rows = TOPIC_ROWS[:4] + [_row("flood-warning", "excluded")]
    report = score(_set(), [_count(5), _topic("b02", rows), _topic("b03")], tier="synthetic")
    assert {"case": "b02", "record_key": "flood-warning",
            "why": "not AI-eligible but was judged"} in report["breaches"]


def test_coverage_reports_unassessed_and_inconclusive_with_their_denominators():
    rows = [_row(k, "unassessed") for k in ("flood-gauges", "flood-hazard", "tilapia",
                                             "rainfall-note")] + [TOPIC_ROWS[4]]
    report = score(_set(), [_count(5), _topic("b02", rows), _topic("b03")], tier="synthetic")
    coverage = report["coverage"]
    assert coverage["selected"] == 10
    assert coverage["unassessed"] == 6
    assert coverage["inconclusive_cases"] == ["b02"]


def test_a_reported_topic_count_must_equal_its_own_included_candidates():
    observation = _topic("b02")
    observation.listing["topic_count"]["matches"] = 3
    report = score(_set(), [_count(5), observation, _topic("b03")], tier="synthetic")
    assert report["topic_counts"]["inconsistent"] == [
        {"case": "b02", "reported": 3, "included_candidates": 2}]
    assert report["topic_counts"]["labelled_relevant_among_included"] == {"b02": 2}


def test_without_a_held_out_split_every_result_is_exploratory_and_inconclusive():
    report = score(_set(), _correct(), tier="synthetic")
    assert report["standing"]["evidence"] == "exploratory_inconclusive"
    assert "no held-out questions" in report["standing"]["why"]


def test_a_held_out_split_whose_lock_does_not_match_is_refused():
    with pytest.raises(MilestoneSetError, match="lock"):
        _set(development=["b01"], held_out=["b02", "b03"], lock="0" * 64)


def test_a_question_in_both_development_and_held_out_is_refused():
    data = copy.deepcopy(BASELINE)
    data["split"] = {"development": ["b01", "b02"], "held_out": ["b02"],
                     "lock": held_out_digest(data, ["b02"])}
    with pytest.raises(MilestoneSetError, match="b02"):
        parse_milestone_set(data)


def test_a_locked_held_out_split_on_public_data_is_still_not_cit_u_evidence():
    lock = held_out_digest(BASELINE, ["b02", "b03"])
    milestone = _set(development=["b01"], held_out=["b02", "b03"], lock=lock)
    report = score(milestone, _correct(), tier="proxy")
    assert report["standing"]["evidence"] == "exploratory_inconclusive"
    assert "not CIT-U" in report["standing"]["why"]
    assert report["split"]["held_out"] == ["b02", "b03"]
    assert report["split"]["lock_verified"] is True


def test_a_change_to_a_held_out_label_changes_the_lock():
    changed = copy.deepcopy(BASELINE)
    changed["relevance"]["flooding"]["labels"]["tilapia"] = "relevant"
    assert held_out_digest(BASELINE, ["b02"]) != held_out_digest(changed, ["b02"])


REVIEW = {"reviewer": "Jive Tyler Revalde", "rubric": "pilot-rubric-v1", "independent": False}


def test_answer_quality_is_not_reviewed_until_a_person_reviews_it():
    report = score(_set(), _correct(), tier="synthetic")
    answers = report["answer_quality"]
    assert answers["status"] == "not_reviewed"
    assert answers["reviewed_fraction"] == {"numerator": 0, "denominator": 3, "value": 0.0}


def test_one_reviewer_gives_an_exploratory_review_with_its_fraction_and_rubric():
    reviews = [{**REVIEW, "case": "b02", "answer_correct": True,
                "claims": {"supported": 2, "total": 2}, "citations": {"supported": 1, "total": 2}}]
    report = score(_set(), _correct(), tier="synthetic", reviews=reviews)
    answers = report["answer_quality"]
    assert answers["status"] == "exploratory_single_reviewer"
    assert answers["reviewed_fraction"] == {"numerator": 1, "denominator": 3, "value": 1 / 3}
    assert answers["rubrics"] == ["pilot-rubric-v1"]
    assert answers["answer_correct"] == {"numerator": 1, "denominator": 1, "value": 1.0}
    assert answers["claim_support"] == {"numerator": 2, "denominator": 2, "value": 1.0}
    assert answers["citation_support"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert report["standing"]["institutional_quality_claim"] is False


def test_disagreements_between_reviewers_are_disclosed():
    second = {"reviewer": "Second Reviewer", "rubric": "pilot-rubric-v1", "independent": True}
    reviews = [{**REVIEW, "case": "b02", "answer_correct": True},
               {**second, "case": "b02", "answer_correct": False}]
    report = score(_set(), _correct(), tier="synthetic", reviews=reviews)
    answers = report["answer_quality"]
    assert answers["status"] == "independently_reviewed"
    assert answers["disagreements"] == [{"case": "b02", "field": "answer_correct",
                                         "verdicts": {"Jive Tyler Revalde": True,
                                                      "Second Reviewer": False}}]


def test_judge_scores_stay_uninterpreted_without_human_labels_on_the_same_cases():
    judge = [{"case": "b02", "answer_correct": True}]
    report = score(_set(), _correct(), tier="synthetic", judge=judge)
    assert report["judge"]["interpretable"] is False
    assert report["judge"]["agreement"] is None


def test_judge_agreement_with_human_labels_is_reported_but_the_threshold_is_the_owners():
    reviews = [{**REVIEW, "case": "b02", "answer_correct": True},
               {**REVIEW, "case": "b03", "answer_correct": False}]
    judge = [{"case": "b02", "answer_correct": True}, {"case": "b03", "answer_correct": True}]
    report = score(_set(), _correct(), tier="synthetic", reviews=reviews, judge=judge)
    assert report["judge"]["agreement"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert report["judge"]["interpretable"] is False
    assert "threshold" in report["judge"]["why"]


def test_latency_and_usage_report_what_was_observed_and_what_was_not():
    observed = {"model_calls": 1, "prompt_tokens_estimated": 120, "cache_hits": 0,
                "cache_misses": 4, "stage_ms": {"total": 40}}
    rows = [_count(5), _topic("b02", latency_ms=900), _topic("b03")]
    rows[1].listing["observed"] = observed
    report = score(_set(), rows, tier="synthetic")
    assert report["latency_ms"]["n"] == 1
    assert report["latency_ms"]["missing"] == ["b01", "b03"]
    assert report["usage"]["model_calls"] == 1
    assert report["usage"]["unreported"] == ["b01", "b03"]


def test_the_report_names_the_security_and_lifecycle_scenarios_and_their_tests():
    report = score(_set(), _correct(), tier="synthetic")
    names = {row["scenario"] for row in report["scenarios"]}
    assert {"invisible records never appear", "AI-restricted records are never named or sent",
            "cancel and retry of an owned run", "a foreign run is refused"} <= names
    assert all(row["status"] == "asserted by tests, not observed in this run"
               for row in report["scenarios"])


def test_held_out_figures_are_reported_apart_from_development():
    lock = held_out_digest(BASELINE, ["b02"])
    milestone = _set(development=["b01", "b03"], held_out=["b02"], lock=lock)
    report = score(milestone, _correct(), tier="proxy")
    held_out = report["held_out"]
    assert list(held_out["screening"]["by_case"]) == ["b02"]
    assert held_out["metadata_counts"]["denominator"] == 0
    assert score(_set(), _correct(), tier="proxy")["held_out"] is None


def test_a_judge_is_validated_against_the_independent_reviewer_when_there_is_one():
    second = {"reviewer": "Second Reviewer", "rubric": "pilot-rubric-v1", "independent": True}
    reviews = [{**REVIEW, "case": "b02", "answer_correct": True},
               {**second, "case": "b02", "answer_correct": False}]
    judge = [{"case": "b02", "answer_correct": True}]
    report = score(_set(), _correct(), tier="synthetic", reviews=reviews, judge=judge)
    assert report["judge"]["against"] == "independent reviewer"
    assert report["judge"]["agreement"]["numerator"] == 0
