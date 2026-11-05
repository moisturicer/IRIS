"""IR-740: the runtime arm in IR-605's campaign preflight, spend and report. Pure.

Old controller and lanes artifacts keep their readers and denominators; the
tests in test_campaign_report.py still pin that. These add what the runtime
needs: its own identity, effective-condition preflight and separate reports
for a larger allowance and for models.
"""

import copy

import pytest

from apps.ai.evaluation.campaign_report import (CampaignRefused, build_report, preflight,
                                                render_markdown, spend)
from apps.ai.evaluation.engines import runtime_identity

from .test_campaign_report import LOCK, SET, attempt, row, run, turn

RUNTIME = {"engine_version": "ai-runtime-1", "protocol_version": "runs-reader-1",
           "identity": runtime_identity(), "git_commit": "rt1"}


def rt_runs(n=3, prefix="runtime", **manifest):
    out = []
    for i in range(n):
        r = run("controller", run_id=f"{prefix}-{i}", **{**RUNTIME, **manifest})
        r["arm"] = "runtime"
        out.append(r)
    return out


def refused(campaign, mode="architecture", counted=False):
    with pytest.raises(CampaignRefused) as caught:
        preflight(SET, LOCK, campaign, mode=mode, counted=counted)
    return str(caught.value)


def controller_and_runtime(**runtime_manifest):
    from .test_campaign_report import reps

    return {"controller": reps("controller"), "runtime": rt_runs(**runtime_manifest)}


def test_a_matched_controller_and_runtime_campaign_passes_preflight_without_relabelling():
    campaign = controller_and_runtime()
    assert preflight(SET, LOCK, campaign, mode="architecture", counted=True) == []


def test_the_runtime_arm_cannot_borrow_the_controller_engine_or_protocol():
    assert "engine" in refused({"runtime": rt_runs(engine_version="controller-v1")})
    assert "runs-reader-1" in refused({"runtime": rt_runs(protocol_version="public-1")})
    assert "identity" in refused({"runtime": rt_runs(identity={"engine": "controller-v1"})})
    assert "public-1" in refused({"controller": [
        run("controller", run_id=f"c{i}", protocol_version="runs-reader-1") for i in range(3)]})


def test_the_unequal_budget_comparison_is_refused_and_named():
    campaign = controller_and_runtime(limits={"case_cost_usd": 5.0})
    assert "limits" in refused(campaign)


@pytest.mark.parametrize("key, value, named", [
    ("model_ids", {"agent": "other-model"}, "model_ids"),
    ("cache_state", "warm", "cache_state"),
    ("data_policy", "retains", "data_policy"),
    ("corpus_snapshot_digest", "other", "corpus_snapshot_digest")])
def test_unequal_effective_conditions_are_refused(key, value, named):
    assert named in refused(controller_and_runtime(**{key: value}))


def test_effective_models_not_configured_names_decide_comparability():
    # Configured alike, but the runtime's attempts were served by a fallback model.
    served = [{"operation": "llm", "model": "fallback"}]
    assert "model_ids" in refused(controller_and_runtime(physical_attempts=served))
    # Configured differently, served by the same model once case is folded.
    alike = controller_and_runtime(model_ids={"agent": "M1"})
    assert preflight(SET, LOCK, alike, mode="architecture", counted=False) == []


def test_a_larger_allowance_is_a_capability_report_never_an_architecture_comparison():
    base, bigger = rt_runs(prefix="base"), rt_runs(prefix="big", limits={"case_cost_usd": 5.0})
    campaign = {"base": base, "larger": bigger}
    assert refused(campaign, mode="architecture")  # arm labels, not allowances, name the arms
    assert preflight(SET, LOCK, campaign, mode="capability", counted=False) == []
    assert "architecture comparison" in refused({"a": rt_runs(prefix="a"), "b": rt_runs(prefix="b")},
                                                mode="capability")
    assert "model_ids" in refused({"base": base, "larger": rt_runs(
        prefix="x", limits={"case_cost_usd": 5.0}, model_ids={"agent": "m2"})}, mode="capability")


def reviews_for(campaign):
    out = []
    for label, runs in campaign.items():
        for r in runs:
            for c in SET["conversations"]:
                if c["split"] == "development":
                    out.append({"conversation": c["id"], "arm": label, "run_id": r["run_id"],
                                "reviewer": "Rev One", "reviewer_kind": "human",
                                "role": "independent", "rubric_version": 1, "status": "reviewed",
                                "task_completion": "yes", "pair_usefulness": "useful",
                                "claims": [], "evidence_record_ids": [],
                                "presentation_leak": False, "no_answer": False,
                                "unnecessary_clarification": False, "access_breach": False})
    return out


def test_the_capability_report_names_each_allowance_and_credits_nothing_to_the_architecture():
    campaign = {"base": rt_runs(prefix="base"),
                "larger": rt_runs(prefix="big", limits={"case_cost_usd": 5.0})}
    out = build_report(SET, LOCK, campaign, reviews_for(campaign), mode="capability",
                       approvals=None, scenarios=None)
    assert out["mode"] == "capability"
    assert "allowance" in out["comparison"] and "never credited" in out["comparison"]
    assert out["arms"]["base"]["allowance"] == {"case_cost_usd": 1.0}
    assert out["arms"]["larger"]["allowance"] == {"case_cost_usd": 5.0}
    assert out["arms"]["larger"]["identity"] == runtime_identity()
    assert "ai-runtime-1" in render_markdown(out)


def test_an_architecture_report_lists_the_runtime_arm_as_measured_with_its_own_engine():
    from .test_campaign_report import reps

    campaign = {"controller": reps("controller"), "runtime": rt_runs()}
    out = build_report(SET, LOCK, campaign, reviews_for(campaign), mode="architecture",
                       approvals=None, scenarios=None)
    assert out["arms"]["runtime"]["status"] == "measured"
    assert out["arms"]["runtime"]["engine_version"] == "ai-runtime-1"
    assert out["arms"]["controller"]["engine_version"] == "controller-v1"
    assert out["counted"] is False


def test_spend_retains_purposes_outcomes_reserved_and_missing_usage_by_cache_state():
    def physical(purpose, cost, reported=True, reserved=0.04, state="settled"):
        return {**attempt("llm", cost, reported=reported), "purpose": purpose, "state": state,
                "reserved_cost_usd": reserved}

    cold = row("a0", "A01", conversation_id=1, turns=[
        turn(attempts=[physical("agent", 0.02), physical("repair", 0.01)]),
        turn("cap_stop", attempts=[], usage="missing")])
    failed = row("a1", "A01", conversation_id=2, status="incomplete", turns=[
        turn("timeout", attempts=[physical("agent", 0.04, reported=False, state="abandoned")])])
    cancelled = row("b0", "A02", conversation_id=3, cache="warm", status="incomplete", turns=[
        turn("cancellation", attempts=[physical("agent", 0.03, reported=False)])])
    out = spend([run("controller", rows=[cold, failed, cancelled])])
    assert out["cold"]["purposes"] == {
        "agent": {"attempts": 2, "reported_usd": pytest.approx(0.02),
                  "unreported_reserved_usd": pytest.approx(0.04)},
        "repair": {"attempts": 1, "reported_usd": pytest.approx(0.01),
                   "unreported_reserved_usd": 0}}
    assert out["cold"]["outcomes"] == {"answered": 1, "cap_stop": 1, "timeout": 1}
    assert out["cold"]["attempt_states"] == {"settled": 2, "abandoned": 1}
    assert out["cold"]["reserved_usd"] == pytest.approx(0.12)
    assert out["cold"]["turns_missing_usage"] == 2
    assert out["warm"]["outcomes"] == {"cancellation": 1}
    assert out["warm"]["purposes"]["agent"]["unreported_reserved_usd"] == pytest.approx(0.03)
    assert copy.deepcopy(out)["cold"]["cost_status"] == "incomplete"
