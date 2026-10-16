"""IR-598: per-arm, per-family scoring, equal conditions, preference, judge, cost. Pure."""

import pytest

from apps.ai.evaluation.conversation_scoring import (
    TARGET_LABEL,
    ScoringError,
    calibrate_judge,
    check_conditions,
    cost_latency,
    preference,
    score_reviews,
    wilson,
)

from .test_conversations import conv, make_set


def review(cid, arm="current", **extra):
    base = {"conversation": cid, "arm": arm, "reviewer": "Ana", "rubric_version": 1,
            "task_completion": "yes", "pair_usefulness": "useful",
            "claims": [{"supported": True, "citation_correct": True, "page_correct": True}],
            "unnecessary_clarification": False, "presentation_leak": False,
            "access_breach": False, "no_answer": False}
    base.update(extra)
    return base


def data(n=4):
    return make_set([conv(f"c{i}", "A01") for i in range(n)]
                    + [conv("u", "A02", supported_unambiguous=False)])


def test_wilson_matches_known_values():
    low, high = wilson(9, 10)
    assert low == pytest.approx(0.5958, abs=1e-3)
    assert high == pytest.approx(0.9821, abs=1e-3)
    assert wilson(0, 0) == (None, None)


def test_metrics_have_own_denominators_and_partial_is_not_complete():
    reviews = [review("c0"), review("c1", task_completion="partial"),
               review("c2", task_completion="no", pair_usefulness="na"),
               review("u", task_completion="no")]
    out = score_reviews(data(), reviews, arm="current", min_examples=2)
    fam = out["families"]["A01"]
    assert (fam["task_completion"]["numerator"], fam["task_completion"]["denominator"]) == (1, 3)
    assert fam["partial"]["numerator"] == 1
    assert fam["pair_usefulness"]["denominator"] == 2
    assert out["families"]["A02"]["task_completion"]["denominator"] == 0
    assert out["families"]["A02"]["status"] == "INCONCLUSIVE"
    assert "blended" not in out and "overall_score" not in out


def test_claim_citation_page_support_and_small_n_is_inconclusive():
    reviews = [review("c0", claims=[
        {"supported": True, "citation_correct": True, "page_correct": None},
        {"supported": False, "citation_correct": True, "page_correct": False}])]
    out = score_reviews(data(), reviews, arm="current", min_examples=5)
    fam = out["families"]["A01"]
    assert fam["claim_support"]["numerator"] == 1
    assert fam["claim_support"]["denominator"] == 2
    assert fam["citation_support"]["numerator"] == 2
    assert fam["page_support"]["denominator"] == 1
    assert fam["status"] == "INCONCLUSIVE"


def test_targets_are_labelled_and_straddling_is_inconclusive():
    reviews = [review(f"c{i}") for i in range(4)]
    out = score_reviews(data(), reviews, arm="current", min_examples=2)
    target = out["targets"]["task_completion"]
    assert target["label"] == TARGET_LABEL
    assert TARGET_LABEL == "proposed owner-review target — not an approved release gate"
    assert target["status"] == "inconclusive"
    many = make_set([conv(f"k{i}", "A01") for i in range(200)])
    out = score_reviews(many, [review(f"k{i}") for i in range(200)], arm="current")
    assert out["targets"]["task_completion"]["status"] == "met"
    bad = [review(f"k{i}", task_completion="no") for i in range(200)]
    assert score_reviews(many, bad, arm="current")["targets"]["task_completion"]["status"] == "not_met"


def test_any_access_breach_blocks_enablement_and_zero_is_hedged():
    out = score_reviews(data(), [review("c0", access_breach=True), review("c1")], arm="current")
    assert out["enablement_blocked"] is True
    assert out["access_breaches"]["conversations"] == ["c0"]
    clean = score_reviews(data(), [review("c0")], arm="current")
    assert clean["enablement_blocked"] is False
    assert "does not prove absence" in clean["access_breaches"]["note"]
    assert clean["access_breaches"]["suite_size"] == 1


def test_anonymous_reviews_and_unknown_conversations_are_refused():
    with pytest.raises(ScoringError, match="reviewer"):
        score_reviews(data(), [review("c0", reviewer="")], arm="current")
    with pytest.raises(ScoringError, match="rubric_version"):
        score_reviews(data(), [review("c0", rubric_version=None)], arm="current")
    with pytest.raises(ScoringError, match="not in the set"):
        score_reviews(data(), [review("nope")], arm="current")


def test_other_arms_reviews_are_not_mixed_in():
    reviews = [review("c0", arm="current"), review("c0", arm="controller", task_completion="no")]
    out = score_reviews(data(), reviews, arm="current")
    assert out["families"]["A01"]["task_completion"]["numerator"] == 1


def test_preference_counts_excludes_ties_and_refuses_unblinded():
    recs = [{"conversation": f"c{i}", "reviewer": "Ana", "preferred": "candidate",
             "blinded": True} for i in range(8)]
    recs += [{"conversation": "t", "reviewer": "Ana", "preferred": "tie", "blinded": True},
             {"conversation": "l", "reviewer": "Ana", "preferred": "baseline", "blinded": True}]
    out = preference(recs)
    assert (out["wins"], out["losses"], out["ties"], out["denominator"]) == (8, 1, 1, 10)
    assert out["p_value"] == pytest.approx(2 * (1 + 9) / 512)
    recs[0]["blinded"] = False
    with pytest.raises(ScoringError, match="unblinded"):
        preference(recs)


def test_judge_calibration_kappa_and_institutional_claim():
    pairs = [("y", "y"), ("y", "y"), ("n", "n"), ("y", "n")]
    items = [{"item": str(i), "judge": j, "human": h, "human_reviewer": "Ana"}
             for i, (j, h) in enumerate(pairs)]
    out = calibrate_judge(items)
    assert out["n"] == 4 and out["agreement"] == 0.75
    assert out["kappa"] == pytest.approx(0.5)
    assert out["confusion"]["y"]["n"] == 1
    assert out["institutional_claim_allowed"] is False
    two = [dict(i, human_reviewer="Bo") if k % 2 else i for k, i in enumerate(items)]
    assert calibrate_judge(two)["institutional_claim_allowed"] is False
    assert calibrate_judge(two, adjudication={"by": "Cy"})["institutional_claim_allowed"] is True
    with pytest.raises(ScoringError, match="human reviewer"):
        calibrate_judge([{"item": "1", "judge": "y", "human": "y"}])


def run(arm, **overrides):
    manifest = {"corpus_snapshot_digest": "d", "model_ids": {"answer": "m"},
                "data_policy": "p", "limits": {"tool_calls": 6}, "rubric_version": 1, "campaign_approval_id": "APP-1",
                "set_digests": {"development": "a", "held_out": "b"}}
    manifest.update(overrides.pop("manifest", {}))
    base = {"arm": arm, "manifest": manifest, "providers": "real", "capacity_fit": True,
            "conversations": []}
    base.update(overrides)
    return base


def test_equal_conditions_enforced_for_architecture_and_model_mode():
    other = {"model_ids": {"answer": "x"}}
    runs = {"current": run("current"), "controller": run("controller", manifest=other)}
    with pytest.raises(ScoringError, match="model_ids"):
        check_conditions(runs, mode="architecture")
    same_arm = {"a": run("current"), "b": run("current", manifest=other)}
    check_conditions(same_arm, mode="model")
    with pytest.raises(ScoringError, match="same architecture"):
        check_conditions(runs, mode="model")
    matching = {"current": run("current"), "controller": run("controller")}
    check_conditions(matching, mode="architecture")


def test_cost_latency_cold_and_warm_separately_and_capacity_labels():
    rows = [{"id": str(i), "latency_ms": float(i + 1), "cost": 0.5, "success": i < 3,
             "cache": "cold"} for i in range(4)]
    rows.append({"id": "w", "latency_ms": 1.0, "cost": 1.0, "success": False,
                 "cache": "warm"})
    out = cost_latency(run("current", conversations=rows))
    cold, warm = out["cold"], out["warm"]
    assert cold["n"] == 4 and cold["p50"] == 2.0 and cold["p95"] == 4.0
    assert cold["cost_per_successful_task"] == pytest.approx(2.0 / 3)
    assert warm["cost_per_successful_task"] is None and "no successful" in warm["note"]
    assert out["capacity"] == "unverified"
    unfit = cost_latency(run("current", capacity_fit=False, conversations=rows))
    assert unfit["capacity"] == "unverified"
    fake = cost_latency(run("current", providers="fake", conversations=rows))
    assert fake["capacity"] == "unverified" and "contract check" in fake["evidence"]
