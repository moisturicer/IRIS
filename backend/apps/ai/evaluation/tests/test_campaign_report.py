"""IR-609: campaign preflight, smoke, spend and report. Pure; hand-worked numbers."""

import copy

import pytest

from apps.ai.evaluation.campaign_report import (
    CampaignRefused,
    approvals_status,
    build_report,
    preflight,
    render_markdown,
    require_paid_held_out,
    smoke_summary,
    spend,
)
from apps.ai.evaluation.conversations import lock_record, split_digests

from .test_conversations import conv, make_set

#: Two families of four supported development cases, plus one held-out case.
SET = make_set([conv(f"a{i}", "A01") for i in range(4)]
               + [conv(f"b{i}", "A02") for i in range(4)]
               + [conv("h0", "A01", split="held_out", topic="other", papers=("Q",))])
SET["label_status"] = "human_reviewed"
SET["corpus"] = {"snapshot_id": "proxy-40", "paper_set_sha256": "c0ffee"}
LOCK = {**lock_record(SET), "locked_at": "2026-10-01T00:00:00+00:00"}
ENGINES = {"controller": "controller-v1", "current": "lanes-v1", "fixed_synthesis": "lanes-v1"}
COMMITS = {"controller": "abc", "current": "def", "fixed_synthesis": "fed"}


def attempt(op, cost, reported=True, model="m1"):
    return {"operation": op, "model": model, "usage_reported": reported, "cost_usd": cost,
            "state": "settled", "price_basis": "admission"}


def turn(outcome="answered", attempts=(), usage=None):
    attempts = list(attempts)
    if usage is None:
        usage = "reported" if attempts and all(a["usage_reported"] for a in attempts) else "missing"
    return {"number": 1, "question": "q", "outcome": outcome, "physical_attempts": attempts,
            "usage_status": usage, "latency_ms": 10, "diagnostics": {"stage": "answered"}}


def row(cid, family, *, conversation_id, cache="cold", latency=100, turns=None,
        status="complete"):
    return {"id": cid, "family": family, "split": "development", "cache": cache,
            "conversation_id": conversation_id, "status": status, "latency_ms": latency,
            "turns": turns or [turn(attempts=[attempt("llm", 0.01)])]}


def run(arm="controller", run_id="r1", rows=None, providers="real", **manifest):
    rows = rows if rows is not None else [
        row(c["id"], c["family"], conversation_id=f"{run_id}/{c['id']}")
        for c in SET["conversations"] if c["split"] == "development"]
    base = {"run_id": run_id, "timestamp_utc": "2026-10-02T00:00:00+00:00",
            "git_commit": COMMITS[arm], "engine_version": ENGINES[arm],
            "protocol_version": "public-1", "cache_state": "cold",
            "corpus_snapshot_digest": "c0ffee", "model_ids": {"answer": "m1"},
            "data_policy": "no-training", "limits": {"case_cost_usd": 1.0},
            "set_digests": split_digests(SET), "rubric_version": 1,
            "pricing_per_million_tokens_usd": {"m1": {"input": 1.0, "output": 2.0}}}
    base.update(manifest)
    return {"schema_version": 1, "run_id": run_id, "arm": arm, "providers": providers,
            "manifest": base, "conversations": rows}


def reps(arm, n=3, prefix=None, **manifest):
    return [run(arm, run_id=f"{prefix or arm}-{i}", **manifest) for i in range(n)]


def refused(*args, **kwargs):
    with pytest.raises(CampaignRefused) as caught:
        preflight(*args, **kwargs)
    return str(caught.value)


# --- preflight -------------------------------------------------------------


def test_a_matched_three_repetition_campaign_passes_counted_preflight():
    campaign = {"controller": reps("controller"), "current": reps("current")}
    assert preflight(SET, LOCK, campaign, mode="architecture", counted=True) == []


def test_draft_labels_and_missing_lock_are_refused_for_a_counted_run():
    draft = {**SET, "label_status": "draft_unreviewed"}
    campaign = {"controller": reps("controller")}
    assert "draft" in refused(draft, LOCK, campaign, mode="architecture", counted=True)
    assert "lock" in refused(SET, None, campaign, mode="architecture", counted=True)
    reasons = preflight(draft, LOCK, campaign, mode="architecture", counted=False)
    assert any("draft" in r for r in reasons)


def test_a_stale_lock_or_stale_run_digest_is_refused_even_uncounted():
    edited = copy.deepcopy(SET)
    edited["conversations"][0]["topic"] = "changed after locking"
    campaign = {"controller": reps("controller")}
    assert "development" in refused(edited, LOCK, campaign, mode="architecture", counted=False)
    stale = {"controller": reps("controller", set_digests={"development": "old",
                                                            "held_out": "old"})}
    assert "set_digests" in refused(SET, LOCK, stale, mode="architecture", counted=False)


def test_an_incomplete_manifest_is_refused():
    runs = reps("controller")
    del runs[1]["manifest"]["git_commit"]
    assert "git_commit" in refused(SET, LOCK, {"controller": runs}, mode="architecture",
                                   counted=False)


def test_duplicate_conversation_ids_are_refused_across_runs_and_within_one():
    runs = reps("controller")
    runs[2]["conversations"][0]["conversation_id"] = runs[0]["conversations"][3]["conversation_id"]
    assert "Conversation" in refused(SET, LOCK, {"controller": runs}, mode="architecture",
                                     counted=False)
    twice = reps("controller")
    twice[0]["conversations"].append(copy.deepcopy(twice[0]["conversations"][0]))
    twice[0]["conversations"][-1]["conversation_id"] = "fresh"
    assert "a0" in refused(SET, LOCK, {"controller": twice}, mode="architecture", counted=False)
    same_run = reps("controller")
    same_run[1]["run_id"] = same_run[1]["manifest"]["run_id"] = "controller-0"
    assert "run_id" in refused(SET, LOCK, {"controller": same_run}, mode="architecture",
                               counted=False)


@pytest.mark.parametrize("key, value", [
    ("corpus_snapshot_digest", "other"), ("model_ids", {"answer": "m2"}),
    ("data_policy", "retains"), ("limits", {"case_cost_usd": 5.0})])
def test_arms_with_unequal_conditions_are_refused(key, value):
    campaign = {"controller": reps("controller"), "current": reps("current", **{key: value})}
    assert key in refused(SET, LOCK, campaign, mode="architecture", counted=False)


def test_an_arm_must_run_its_own_pinned_engine_through_the_public_protocol():
    wrong_engine = {"controller": reps("controller", engine_version="lanes-v1")}
    assert "engine" in refused(SET, LOCK, wrong_engine, mode="architecture", counted=False)
    switch = {"controller": reps("controller", protocol_version="legacy")}
    assert "public-1" in refused(SET, LOCK, switch, mode="architecture", counted=False)
    same_code = {"current": reps("current", implementation_ref="release/x"),
                 "fixed_synthesis": reps("fixed_synthesis", git_commit="def",
                                         implementation_ref="release/x")}
    assert "distinct" in refused(SET, LOCK, same_code, mode="architecture", counted=False)


def test_fewer_than_three_repetitions_or_fake_providers_are_not_counted():
    short = {"controller": reps("controller", n=2)}
    assert "repetitions" in refused(SET, LOCK, short, mode="architecture", counted=True)
    fake = {"controller": [run("controller", run_id=f"f{i}", providers="fake") for i in range(3)]}
    reasons = preflight(SET, LOCK, fake, mode="architecture", counted=False)
    assert any("fake" in r for r in reasons)


def test_model_mode_lets_models_differ_but_nothing_else():
    campaign = {"m1": reps("controller"), "m2": reps("controller", prefix="m2", model_ids={"answer": "m2"})}
    assert preflight(SET, LOCK, campaign, mode="model", counted=True) == []
    mixed = {"m1": reps("controller"), "m2": reps("current")}
    assert "architecture" in refused(SET, LOCK, mixed, mode="model", counted=False)


# --- approvals -------------------------------------------------------------

APPROVED = {key: {"reference": f"REF-{key}", "approved_by": "Owner Name", "date": "2026-10-20"}
            for key in ("funding", "provider_data_policy", "dataset_transmission")}


def test_approvals_need_a_reference_and_a_named_approver_each():
    status = approvals_status({**APPROVED, "dataset_transmission": {"reference": "X"}})
    assert status["complete"] is False
    assert status["unrecorded"] == ["dataset_transmission"]
    assert status["funding"] == {"recorded": True, "reference": "REF-funding",
                                 "approved_by": "Owner Name", "date": "2026-10-20"}
    assert approvals_status(None)["unrecorded"] == ["funding", "provider_data_policy",
                                                 "dataset_transmission"]


def test_a_paid_held_out_campaign_is_refused_until_every_approval_is_recorded():
    with pytest.raises(CampaignRefused, match="funding"):
        require_paid_held_out({k: v for k, v in APPROVED.items() if k != "funding"})
    require_paid_held_out(APPROVED)


# --- spend -----------------------------------------------------------------


def spend_run():
    cold = [
        row("a0", "A01", conversation_id=1, latency=100, turns=[turn(attempts=[
            attempt("llm", 0.02), attempt("llm", 0.01, model="m2"), attempt("embed", 0.001)])]),
        row("a1", "A01", conversation_id=2, latency=300, turns=[turn(attempts=[
            attempt("llm", 0.03), attempt("rerank", 0.002)])]),
    ]
    warm = [
        row("b0", "A02", conversation_id=3, cache="warm", latency=50, turns=[
            turn(attempts=[attempt("llm", 0.05, reported=False)])]),
        row("b1", "A02", conversation_id=4, cache="warm", latency=None, turns=[turn()]),
    ]
    return run("controller", rows=cold + warm)


def test_spend_keeps_cold_and_warm_apart_and_counts_every_operation():
    out = spend([spend_run()], successes={("r1", "a0"), ("r1", "a1")})
    cold = out["cold"]
    assert cold["conversations"] == 2
    assert (cold["p50_ms"], cold["p95_ms"]) == (100, 300)
    assert cold["operations"]["llm"] == {"attempts": 3, "reported_usd": pytest.approx(0.06),
                                         "unreported_reserved_usd": 0}
    assert cold["operations"]["embed"]["attempts"] == 1
    assert cold["operations"]["rerank"]["reported_usd"] == pytest.approx(0.002)
    assert "decision" not in cold["operations"]
    assert cold["models"] == ["m1", "m2"]
    assert cold["reported_usd"] == pytest.approx(0.063)
    assert cold["cost_status"] == "complete"
    assert cold["cost_per_successful_task"] == pytest.approx(0.0315)


def test_missing_usage_is_reported_never_imputed_as_zero():
    warm = spend([spend_run()], successes={("r1", "b0")})["warm"]
    assert warm["reported_usd"] == 0
    assert warm["unreported_reserved_usd"] == pytest.approx(0.05)
    assert warm["turns_missing_usage"] == 2
    assert warm["cost_status"] == "incomplete"
    assert warm["cost_per_successful_task"] is None
    assert "missing usage" in warm["note"]
    assert warm["no_latency_recorded"] == 1


def test_spend_records_the_vendor_price_basis():
    out = spend([spend_run()])
    assert out["price_basis"]["per_million_tokens_usd"] == [
        {"m1": {"input": 1.0, "output": 2.0}}]
    assert out["price_basis"]["consistent"] is True
    assert out["price_basis"]["attempt_basis"] == ["admission"]


# --- smoke -----------------------------------------------------------------


def smoke_run(providers="real"):
    return run("controller", providers=providers, rows=[
        row("a0", "A01", conversation_id=1, turns=[turn(attempts=[
            attempt("llm", 0.02), attempt("llm", 0.01, model="m2"), attempt("embed", 0.001)])]),
        row("a1", "A01", conversation_id=2, status="incomplete", turns=[
            turn(attempts=[attempt("llm", 0.03)]),
            turn("timeout", attempts=[attempt("llm", 0.04, reported=False)])]),
    ])


def test_smoke_measures_failures_and_spend_against_the_proposed_caps():
    out = smoke_summary(smoke_run(), case_cost_usd=0.05, campaign_cost_usd=1.0,
                        planned_cases=20)
    assert out["conversations"] == 2 and out["complete"] == 1
    assert out["outcomes"] == {"answered": 2, "timeout": 1}
    assert out["max_conversation_cost_usd"] == pytest.approx(0.07)
    assert out["operations_in_cap"] == ["embed", "llm"]
    assert out["case_cap_covers_observed"] is False
    assert out["projected_campaign_cost_usd"] == pytest.approx(1.4)
    assert out["campaign_cap_covers_projection"] is False
    assert out["ready"] is False


def test_smoke_is_not_ready_while_usage_is_missing_or_providers_are_fake():
    roomy = smoke_summary(smoke_run(), case_cost_usd=0.1, campaign_cost_usd=2.0,
                          planned_cases=20)
    assert roomy["case_cap_covers_observed"] and roomy["campaign_cap_covers_projection"]
    assert any("missing usage" in r for r in roomy["not_ready_reasons"])
    fake = smoke_summary(smoke_run("fake"), case_cost_usd=0.1, campaign_cost_usd=2.0,
                         planned_cases=20)
    assert any("fake" in r for r in fake["not_ready_reasons"])


def test_smoke_runs_development_cases_only():
    held = smoke_run()
    held["conversations"][0]["split"] = "held_out"
    with pytest.raises(CampaignRefused, match="development"):
        smoke_summary(held, case_cost_usd=1, campaign_cost_usd=1, planned_cases=1)


# --- report ----------------------------------------------------------------

DEV = [c["id"] for c in SET["conversations"] if c["split"] == "development"]
PASSED = {name: {"status": "measured", "passed": True}
          for name in ("access_and_recovery", "durability", "browser")}


def verdict(cid, run_id, **extra):
    base = {"conversation": cid, "arm": "controller", "run_id": run_id, "reviewer": "Ana",
            "reviewer_kind": "human", "rubric_version": 1, "status": "reviewed",
            "task_completion": "yes", "pair_usefulness": "useful",
            "claims": [{"record_id": 1, "supported": True, "citation_correct": True,
                        "page_correct": True}],
            "unnecessary_clarification": False, "presentation_leak": False,
            "access_breach": False, "no_answer": False}
    base.update(extra)
    return base


def campaign_reviews(overrides=None, skip=()):
    """Rep 0: b0 fails. Rep 1: all complete. Rep 2: a0 partial."""
    changes = {("controller-0", "b0"): {"task_completion": "no"},
               ("controller-2", "a0"): {"task_completion": "partial"}}
    changes.update(overrides or {})
    return [verdict(cid, f"controller-{i}", **changes.get((f"controller-{i}", cid), {}))
            for i in range(3) for cid in DEV if (f"controller-{i}", cid) not in skip]


def report(reviews=None, **kwargs):
    kwargs.setdefault("scenarios", PASSED)
    kwargs.setdefault("min_examples", 4)
    return build_report(SET, LOCK, {"controller": reps("controller")},
                        campaign_reviews() if reviews is None else reviews,
                        mode="architecture", approvals=APPROVED, **kwargs)


def test_each_repetition_is_scored_with_its_own_denominators_and_the_range_is_shown():
    arm = report()["arms"]["controller"]
    per_rep = [r["scores"]["overall"]["task_completion"] for r in arm["repetitions"]]
    assert [(f["numerator"], f["denominator"]) for f in per_rep] == [(7, 8), (8, 8), (7, 8)]
    completion = arm["summary"]["task_completion"]
    assert (completion["min"], completion["max"]) == (0.875, 1.0)
    assert arm["summary"]["claim_support"]["min"] == 1.0
    a02 = arm["families"]["A02"]
    assert [r["task_completion"]["numerator"] for r in a02["per_repetition"]] == [3, 4, 4]
    assert a02["status"] == "reported"


def test_small_families_are_inconclusive_at_the_scorers_default_minimum():
    out = report(min_examples=10)
    assert out["min_examples"] == 10
    assert {f["status"] for f in out["arms"]["controller"]["families"].values()} == {
        "INCONCLUSIVE"}


def test_a_counted_report_refuses_a_lowered_family_minimum():
    with pytest.raises(CampaignRefused, match="minimum"):
        report(counted=True, min_examples=4)


def test_an_access_breach_blocks_whatever_the_average():
    out = report(campaign_reviews({("controller-2", "b1"): {"access_breach": True}}))
    assert out["arms"]["controller"]["summary"]["task_completion"]["max"] == 1.0
    assert out["arms"]["controller"]["access_breaches"] == [
        {"run_id": "controller-2", "conversation": "b1"}]
    assert out["enablement_blocked"] is True
    assert any("access breach" in b for b in out["blocking"])


def test_an_unreviewed_family_blocks_and_is_not_averaged_away():
    out = report(campaign_reviews(skip={("controller-1", "b2")}))
    assert out["arms"]["controller"]["families"]["A02"]["status"] == "unreviewed"
    assert out["arms"]["controller"]["families"]["A01"]["status"] == "reported"
    assert any("A02" in b and "unreviewed" in b for b in out["blocking"])


def test_a_clean_report_is_not_blocked_but_still_authorizes_nothing():
    out = report()
    assert out["enablement_blocked"] is False and out["blocking"] == []
    assert any("authorizes no spending" in n for n in out["notes"])
    assert "not CIT-U research" in out["corpus"]["claim"]


def test_unavailable_arms_and_scenarios_are_not_measured_never_passed():
    out = report(scenarios=None)
    assert out["arms"]["current"]["status"] == "not_measured"
    assert out["arms"]["fixed_synthesis"]["status"] == "not_measured"
    assert {u["name"] for u in out["unmeasured"]} >= {
        "arm:current", "arm:fixed_synthesis", "scenario:access_and_recovery",
        "scenario:durability", "scenario:browser"}
    assert any("scenario" in b for b in out["blocking"])


def test_examples_diagnostics_spend_and_exclusions_are_reported():
    out = report(excluded=[{"run_id": "old", "reason": "collected before the lock"}])
    arm = out["arms"]["controller"]
    failures = {(e["run_id"], e["conversation"]) for e in arm["examples"]["failures"]}
    assert ("controller-0", "b0") in failures and ("controller-2", "a0") in failures
    assert all(e["verdict"] == "yes" for e in arm["examples"]["successes"])
    assert arm["repetitions"][0]["diagnostics"]["stages"] == {"answered": 8}
    # 24 cold conversations, one $0.01 call each, 22 human-judged successes.
    assert arm["spend"]["cold"]["cost_per_successful_task"] == pytest.approx(0.24 / 22)
    assert out["excluded_runs"] == [{"run_id": "old", "reason": "collected before the lock"}]


def test_repeated_runs_need_reviews_tied_to_a_run():
    loose = [{k: v for k, v in r.items() if k != "run_id"} for r in campaign_reviews()]
    with pytest.raises(CampaignRefused, match="run_id"):
        report(loose)


def test_a_paid_held_out_campaign_without_approvals_is_refused():
    runs = reps("controller")
    for r in runs:
        r["conversations"].append(row("h0", "A01", conversation_id=f"{r['run_id']}/h0"))
        r["conversations"][-1]["split"] = "held_out"
    with pytest.raises(CampaignRefused, match="approvals"):
        build_report(SET, LOCK, {"controller": runs}, campaign_reviews(),
                     mode="architecture", approvals={}, scenarios=PASSED, min_examples=4)


def test_a_model_comparison_is_labelled_separately():
    campaign = {"m1": reps("controller"), "m2": reps("controller", prefix="m2",
                                                     model_ids={"answer": "m2"})}
    out = build_report(SET, LOCK, campaign, [], mode="model", approvals=APPROVED,
                       scenarios=PASSED, min_examples=4)
    assert out["comparison"].startswith("model")
    assert set(out["arms"]) == {"m1", "m2"}


def test_markdown_shows_denominators_blocking_and_unmeasured():
    text = render_markdown(report(campaign_reviews({("controller-2", "b1"): {
        "access_breach": True}}), scenarios=None))
    assert "7/8" in text
    assert "BLOCKED" in text
    assert "not_measured" in text and "fixed_synthesis" in text
    assert "not CIT-U research" in text


# --- review fixes ----------------------------------------------------------


def test_a_breached_answer_is_not_a_success_in_cost_per_task():
    out = report(campaign_reviews({("controller-0", "a0"): {"access_breach": True}}))
    # 24 conversations at $0.01; 22 yes verdicts, one of them breached.
    assert out["arms"]["controller"]["spend"]["cold"]["cost_per_successful_task"] == (
        pytest.approx(0.24 / 21))


def test_an_attempt_without_a_cost_is_missing_usage_not_zero():
    r = run("controller", rows=[row("a0", "A01", conversation_id=1, turns=[
        turn(attempts=[{**attempt("llm", 0.01), "cost_usd": None}], usage="reported")])])
    cold = spend([r])["cold"]
    assert cold["attempts_missing_cost"] == 1
    assert cold["cost_status"] == "incomplete"


def test_different_price_bases_are_flagged_not_merged():
    a = run("controller", run_id="x")
    b = run("current", run_id="y", pricing_per_million_tokens_usd={"m1": {"input": 9.0}})
    basis = spend([a, b])["price_basis"]
    assert len(basis["per_million_tokens_usd"]) == 2
    assert basis["consistent"] is False


def test_examples_come_from_every_repetition():
    arm = report()["arms"]["controller"]
    assert {e["run_id"] for e in arm["examples"]["successes"]} == {
        "controller-0", "controller-1", "controller-2"}


def test_fixed_synthesis_needs_its_own_pinned_implementation_reference():
    campaign = {"current": reps("current"), "fixed_synthesis": reps("fixed_synthesis")}
    assert "implementation_ref" in refused(SET, LOCK, campaign, mode="architecture",
                                           counted=False)
    pinned = {"current": reps("current"),
              "fixed_synthesis": reps("fixed_synthesis", implementation_ref="release/fs-1")}
    assert preflight(SET, LOCK, pinned, mode="architecture", counted=False) == []


def test_a_model_comparison_needs_different_models():
    same = {"m1": reps("controller"), "m2": reps("controller", prefix="m2")}
    assert "model_ids" in refused(SET, LOCK, same, mode="model", counted=False)


def test_model_mode_reviews_must_name_their_run():
    campaign = {"m1": [run("controller", run_id="m1-0")],
                "m2": [run("controller", run_id="m2-0", model_ids={"answer": "m2"})]}
    loose = [{k: v for k, v in r.items() if k != "run_id"} for r in campaign_reviews()]
    with pytest.raises(CampaignRefused, match="run_id"):
        build_report(SET, LOCK, campaign, loose, mode="model", approvals=APPROVED,
                     scenarios=PASSED, min_examples=4)


def test_held_out_rows_need_a_frozen_lock_and_later_output():
    runs = reps("controller", providers="fake")
    for r in runs:
        r["conversations"].append(row("h0", "A01", conversation_id=f"{r['run_id']}/h0"))
        r["conversations"][-1]["split"] = "held_out"
    unfrozen = {k: v for k, v in LOCK.items() if k != "thresholds"}
    with pytest.raises(CampaignRefused, match="thresholds"):
        build_report(SET, unfrozen, {"controller": runs}, campaign_reviews(),
                     mode="architecture", approvals=APPROVED, scenarios=PASSED, min_examples=4)
    early = {**LOCK, "locked_at": "2026-10-03T00:00:00+00:00"}
    with pytest.raises(CampaignRefused, match="postdate"):
        build_report(SET, early, {"controller": runs}, campaign_reviews(),
                     mode="architecture", approvals=APPROVED, scenarios=PASSED, min_examples=4)


def test_runs_over_the_approved_case_cap_are_refused():
    approvals = {**APPROVED, "funding": {**APPROVED["funding"], "case_cost_usd": 0.5}}
    with pytest.raises(CampaignRefused, match="approved"):
        build_report(SET, LOCK, {"controller": reps("controller")}, campaign_reviews(),
                     mode="architecture", approvals=approvals, scenarios=PASSED,
                     min_examples=4)


def test_a_counted_report_needs_double_review_and_stated_reviewer_kind():
    single = report(min_examples=10)
    assert single["counted"] is False
    with pytest.raises(CampaignRefused, match="one review"):
        report(counted=True, min_examples=10)
    unstated = [{k: v for k, v in r.items() if k != "reviewer_kind"}
                for r in campaign_reviews()]
    with pytest.raises(CampaignRefused, match="reviewer_kind"):
        report(unstated, counted=True, min_examples=10)
