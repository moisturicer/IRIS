"""IR-741: the release-readiness report and its manifest. Pure; synthetic fixtures only.

A passing fixture here proves the gate's logic, never that any runtime is ready: its runs
declare themselves ``real`` so the checks can be exercised, and nothing in this file is
measured evidence. The tests that matter most are the ones where evidence is missing,
breached, unknown or incomparable and the manifest must come out blocked.
"""

import copy
import json

import pytest

from apps.ai.evaluation.readiness import (POLICY_DECISIONS, ReadinessRefused, build_readiness,
                                          canonical_digest, assert_ready, collection_preflight,
                                          scenario_rows, validate_measurement, verify_manifest)
from apps.ai.evaluation.scenarios import browser_result

from apps.ai.evaluation.campaign_report import build_report

from .readiness_fixtures import (CASES, LOCK, PROFILE, REFS, SCENARIOS_PASSED, SET, WORKLOAD,
                                 CAPS, campaign, campaign_report, frozen, measurements, mkrun,
                                 reviews, verdict)
from .test_campaign_report import APPROVED

# --- slice 1: what the campaign report must carry for a baseline comparison -------------


def test_a_measured_arm_records_its_conditions_and_the_cases_each_family_ran():
    arm = campaign_report()["arms"]["runtime"]
    assert arm["conditions"] == {
        "corpus_snapshot_digest": "c0ffee", "models": ["m1"], "data_policy": "no-training",
        "limits": {"case_cost_usd": 1.0}, "rubric_version": 1, "cache_states": ["cold"],
        "set_digests": arm["conditions"]["set_digests"]}
    assert arm["conditions"]["set_digests"]["development"]
    assert arm["family_cases"]["A01"] == [f"A01-{i}" for i in range(10)]
    assert len(arm["family_cases"]["A02"]) == 10


def test_the_report_names_every_family_of_the_set():
    assert campaign_report()["set_families"] == ["A01", "A02"]


# --- slice 2: quality, breach, human review and the frozen baseline ----------------------


def pinned(report_, arm="controller"):
    return {"report": frozen(report_), "arm": arm, "expected_sha256": canonical_digest(report_)}


def readiness(report_=None, **kwargs):
    report_ = report_ if report_ is not None else campaign_report()
    kwargs.setdefault("baseline", pinned(report_))
    kwargs.setdefault("scenarios", SCENARIOS_PASSED)
    kwargs.setdefault("references", REFS)
    return build_readiness(report_, **kwargs)


def gate(manifest, name):
    return manifest["gates"][name]


def worse(arm="runtime", rep=0, cases=(), **fields):
    return {(arm, rep, cid): fields for cid in cases}


def test_every_repetition_and_family_is_scored_against_the_selected_objectives():
    q = gate(readiness(), "quality")
    assert q["status"] == "met" and q["reasons"] == []
    assert q["targets"] == {"task_completion": 0.9, "claim_support": 0.95,
                            "citation_support": 0.95, "page_support": 0.95}
    assert [r["run_id"] for r in q["repetitions"]] == ["runtime-0", "runtime-1", "runtime-2"]
    first = q["repetitions"][0]["families"]["A01"]
    assert (first["task_completion"]["numerator"], first["task_completion"]["denominator"]) == (10, 10)
    assert first["task_completion"]["wilson_low"] < 1.0   # the interval is published
    assert q["families"]["A01"] == {"status": "met", "distinct_cases": 10, "repetitions": 3,
                                    "reasons": []}


def test_a_family_below_the_objective_fails_even_when_the_average_clears_it():
    # Rep 1: 8/10 completions in A01, 10/10 in A02 -> overall 18/20 = 0.90, which meets 0.90.
    revs = reviews(worse(rep=1, cases=("A01-0", "A01-1"), task_completion="no"))
    m = readiness(campaign_report(revs=revs))
    q = gate(m, "quality")
    assert q["repetitions"][1]["overall"]["task_completion"]["numerator"] == 18
    assert q["status"] == "not_met"
    assert any("runtime-1" in r and "A01" in r and "task_completion" in r for r in q["reasons"])
    assert m["status"] == "blocked"


def test_claim_citation_and_page_support_use_the_higher_objective():
    bad = {"claims": [{"record_id": 1, "supported": True, "citation_correct": False,
                       "page_correct": True}]}
    revs = reviews(worse(rep=0, cases=("A02-0",), **bad))
    q = gate(readiness(campaign_report(revs=revs)), "quality")
    assert q["status"] == "not_met"
    assert any("A02" in r and "citation_support" in r and "0.95" in r for r in q["reasons"])
    assert not any("claim_support" in r for r in q["reasons"])


def test_fewer_than_three_repetitions_is_inconclusive_not_a_pass():
    m = readiness(campaign_report(runs=campaign(n=2), counted=False))
    q = gate(m, "quality")
    assert q["status"] == "inconclusive"
    assert any("2 repetitions" in r and "3" in r for r in q["reasons"])
    assert m["status"] == "blocked"


def test_a_family_with_fewer_than_ten_distinct_cases_is_insufficient():
    short = [c for c in CASES if c != "A02-9"]
    skip = {(arm, i, "A02-9") for arm in ("controller", "runtime") for i in range(3)}
    m = readiness(campaign_report(runs=campaign(cases=short), revs=reviews(skip=skip)))
    q = gate(m, "quality")
    assert q["status"] == "inconclusive"
    assert q["families"]["A02"]["status"] == "inconclusive"
    assert q["families"]["A02"]["distinct_cases"] == 9
    assert any("A02" in r and "9 distinct cases" in r and "10" in r for r in q["reasons"])
    assert q["families"]["A01"]["status"] == "met"


def test_a_family_of_the_set_that_was_not_run_is_named_not_averaged_away():
    only_a01 = [c for c in CASES if c.startswith("A01")]
    skip = {(arm, i, c) for arm in ("controller", "runtime") for i in range(3)
            for c in CASES if c.startswith("A02")}
    m = readiness(campaign_report(runs=campaign(cases=only_a01), revs=reviews(skip=skip)))
    q = gate(m, "quality")
    assert q["status"] == "inconclusive"
    assert q["missing_families"] == ["A02"]
    assert any("A02" in r and "not run" in r for r in q["reasons"])


def test_the_disabled_public_research_family_is_listed_as_excluded_not_silently_dropped():
    q = gate(readiness(), "quality")
    assert q["excluded_families"] == {"A15": "public research stays disabled pending its own "
                                             "approval (ADR-042)"}


def test_fake_providers_are_a_contract_check_never_measured_quality():
    m = readiness(campaign_report(runs=campaign(providers="fake"), counted=False))
    q = gate(m, "quality")
    assert q["status"] == "contract_only"
    assert any("fake" in r for r in q["reasons"])
    assert m["status"] == "blocked"


def test_a_lowered_family_minimum_cannot_pass():
    m = readiness(campaign_report(min_examples=4, counted=False))
    q = gate(m, "quality")
    assert q["status"] == "inconclusive"
    assert any("family minimum 4" in r for r in q["reasons"])


def test_an_access_breach_blocks_readiness_whatever_the_quality():
    revs = reviews({("runtime", 2, "A02-3"): {"access_breach": True}})
    m = readiness(campaign_report(revs=revs))
    assert gate(m, "quality")["status"] == "met"
    safety = gate(m, "safety")
    assert safety["status"] == "breached"
    assert safety["breaches"] == [{"run_id": "runtime-2", "conversation": "A02-3"}]
    assert m["status"] == "blocked"
    assert any("access breach" in b and "A02-3" in b for b in m["blocking"])


def test_unreviewed_and_single_reviewed_cases_are_explicit_human_review_gaps():
    revs = reviews(skip={("runtime", 0, "A01-0")}, single={("runtime", 1, "A02-2")})
    m = readiness(campaign_report(revs=revs, counted=False))
    review = gate(m, "human_review")
    assert review["status"] == "not_met"
    gaps = " ".join(m["human_review_gaps"])
    assert "A01" in gaps and "unreviewed" in gaps and "A01-0" in gaps
    assert "runtime-1/A02-2" in gaps and "one review" in gaps


def test_a_clean_counted_report_leaves_no_review_gap_but_still_needs_the_release_decision():
    m = readiness()
    assert gate(m, "human_review")["status"] == "met"
    assert m["human_review_gaps"] == ["release_owner_decision: no named person has recorded "
                                      "the release decision; this manifest decides nothing"]


# --- the frozen baseline ---------------------------------------------------------------


def test_equal_matched_aggregates_are_not_a_regression():
    b = gate(readiness(), "baseline")
    assert b["status"] == "met"
    assert b["metrics"]["task_completion"]["candidate"]["denominator"] == 60
    assert b["metrics"]["task_completion"]["regressed"] is False
    assert b["baseline_sha256"]


def test_a_matched_aggregate_regression_blocks_even_when_every_objective_is_met():
    revs = reviews(worse(rep=0, cases=("A01-0",), task_completion="partial"))
    m = readiness(campaign_report(revs=revs))
    assert gate(m, "quality")["status"] == "met"          # 9/10 still meets 0.90
    b = gate(m, "baseline")
    assert b["status"] == "not_met"
    assert b["metrics"]["task_completion"]["regressed"] is True
    assert any("task_completion" in r and "59/60" in r and "60/60" in r for r in b["reasons"])
    assert m["status"] == "blocked"


def test_a_baseline_taken_under_other_conditions_is_incomparable_not_compared():
    other = campaign_report(runs=campaign(controller={"model_ids": {"answer": "m2"}},
                                          runtime={"model_ids": {"answer": "m2"}}))
    m = readiness(baseline=pinned(other))
    b = gate(m, "baseline")
    assert b["status"] == "incomparable"
    assert any("model_ids" in r for r in b["reasons"])
    assert b.get("metrics") is None
    assert m["status"] == "blocked"


def test_a_baseline_that_is_not_the_frozen_one_is_incomparable():
    report_ = campaign_report()
    wrong = {**pinned(report_), "expected_sha256": "0" * 64}
    b = gate(readiness(report_, baseline=wrong), "baseline")
    assert b["status"] == "incomparable" and "digest" in " ".join(b["reasons"])


def test_a_baseline_that_is_not_pinned_missing_or_unmeasured_is_not_measured():
    report_ = campaign_report()
    unpinned = {"report": frozen(report_), "arm": "controller"}
    assert gate(readiness(report_, baseline=unpinned), "baseline")["status"] == "not_measured"
    missing = readiness(report_, baseline=None)
    assert gate(missing, "baseline")["status"] == "not_measured"
    unmeasured = {**pinned(report_), "arm": "fixed_synthesis"}
    b = gate(readiness(report_, baseline=unmeasured), "baseline")
    assert b["status"] == "not_measured" and "fixed_synthesis" in " ".join(b["reasons"])
    assert missing["status"] == "blocked"


# --- slice 3: recorded access, PostgreSQL/worker and browser evidence; references ---------


def without(scenarios, *names):
    return {k: v for k, v in scenarios.items() if k not in names}


def test_all_three_scenario_gates_are_met_by_recorded_passing_evidence():
    m = readiness()
    for name in ("access_disclosure", "postgres_workers", "browser_accessibility"):
        assert gate(m, name)["status"] == "met", name


def test_an_omitted_worker_result_is_not_measured_and_blocks():
    m = readiness(scenarios=without(SCENARIOS_PASSED, "durability"))
    g = gate(m, "postgres_workers")
    assert g["status"] == "not_measured"
    assert m["status"] == "blocked"
    assert any(b.startswith("postgres_workers [not_measured]") for b in m["blocking"])
    assert gate(m, "browser_accessibility")["status"] == "met"


def test_an_omitted_browser_result_is_not_measured_and_blocks():
    m = readiness(scenarios=without(SCENARIOS_PASSED, "browser"))
    assert gate(m, "browser_accessibility")["status"] == "not_measured"
    assert m["status"] == "blocked"


def test_no_scenario_evidence_at_all_blocks_all_three_gates():
    m = readiness(scenarios=None)
    assert {gate(m, n)["status"] for n in (
        "access_disclosure", "postgres_workers", "browser_accessibility")} == {"not_measured"}


def test_a_failed_scenario_is_not_met_with_its_counts():
    failed = {**SCENARIOS_PASSED, "durability": {**SCENARIOS_PASSED["durability"],
                                                 "passed": False, "failed": 2}}
    g = gate(readiness(scenarios=failed), "postgres_workers")
    assert g["status"] == "not_met"
    assert any("2 failed" in r for r in g["reasons"])


def test_a_contract_suite_cannot_stand_in_for_real_postgres_and_independent_workers():
    contract = {**SCENARIOS_PASSED, "durability": {
        **SCENARIOS_PASSED["durability"], "kind": "deterministic_provider_contract"}}
    g = gate(readiness(scenarios=contract), "postgres_workers")
    assert g["status"] == "contract_only"


def test_a_passing_suite_that_ran_no_tests_or_skipped_some_is_not_measured():
    empty = {**SCENARIOS_PASSED, "durability": {**SCENARIOS_PASSED["durability"], "tests": 0}}
    assert gate(readiness(scenarios=empty), "postgres_workers")["status"] == "not_measured"
    skipped = {**SCENARIOS_PASSED, "access_and_recovery": {
        **SCENARIOS_PASSED["access_and_recovery"], "skipped": 3}}
    assert gate(readiness(scenarios=skipped), "access_disclosure")["status"] == "not_measured"


def test_browser_evidence_needs_the_accessibility_checks_measured_and_passed():
    checks = dict(SCENARIOS_PASSED["browser"]["checks"])
    checks["keyboard"] = {"status": "not_measured", "passed": False}
    partial = {**SCENARIOS_PASSED, "browser": {**SCENARIOS_PASSED["browser"], "checks": checks,
                                               "status": "not_measured", "passed": False}}
    g = gate(readiness(scenarios=partial), "browser_accessibility")
    assert g["status"] == "not_measured" and any("keyboard" in r for r in g["reasons"])
    checks["keyboard"] = {"status": "measured", "passed": False}
    failed = {**SCENARIOS_PASSED, "browser": {**SCENARIOS_PASSED["browser"], "checks": checks,
                                              "status": "measured", "passed": False}}
    g = gate(readiness(scenarios=failed), "browser_accessibility")
    assert g["status"] == "not_met" and any("keyboard" in r for r in g["reasons"])


def test_browser_evidence_from_another_commit_is_incomparable():
    stale = {**SCENARIOS_PASSED, "browser": {**SCENARIOS_PASSED["browser"],
                                             "git_commit": "old1"}}
    g = gate(readiness(scenarios=stale), "browser_accessibility")
    assert g["status"] == "incomparable" and "old1" in " ".join(g["reasons"])


# --- evidence references ---------------------------------------------------------------


def test_every_gate_names_the_evidence_it_rests_on():
    m = readiness()
    assert gate(m, "quality")["evidence"] == [{"name": "report", **REFS["report"]}]
    assert gate(m, "baseline")["evidence"] == [{"name": "baseline", **REFS["baseline"]}]
    assert gate(m, "postgres_workers")["evidence"] == [{"name": "scenarios",
                                                         **REFS["scenarios"]}]


def test_a_gate_with_no_recorded_reference_cannot_be_met():
    m = readiness(references={k: v for k, v in REFS.items() if k != "scenarios"})
    for name in ("access_disclosure", "postgres_workers", "browser_accessibility"):
        g = gate(m, name)
        assert g["status"] == "not_measured"
        assert any("no evidence reference" in r and "scenarios" in r for r in g["reasons"])
    assert gate(m, "quality")["status"] == "met"
    assert m["status"] == "blocked"


# --- capability and model results stay separate -----------------------------------------


def labelled(prefix_to_extra):
    """Runtime runs under several labels; reviews tie each repetition to its run."""
    runs = {label: [mkrun("runtime", f"{label}-{i}", **extra) for i in range(3)]
            for label, extra in prefix_to_extra.items()}
    revs = [verdict(label, cid, f"{label}-{i}", who)
            for label in runs for i in range(3) for cid in CASES for who in ("Ana", "Ben")]
    return runs, revs


def alternate(mode, spec):
    runs, revs = labelled(spec)
    return build_report(SET, LOCK, runs, revs, mode=mode, approvals=APPROVED,
                        scenarios=SCENARIOS_PASSED, min_examples=10)


CAPABILITY_SPEC = {"small": {"limits": {"case_cost_usd": 1.0}},
                   "large": {"limits": {"case_cost_usd": 5.0}}}
MODEL_SPEC = {"m1": {}, "m2": {"model_ids": {"answer": "m2"}}}


def test_capability_and_model_results_are_reported_apart_and_never_gate():
    plain = readiness()
    m = readiness(capability=alternate("capability", CAPABILITY_SPEC),
                  model=alternate("model", MODEL_SPEC))
    assert m["gates"] == plain["gates"] and m["status"] == plain["status"]
    cap = m["separate_results"]["capability"]
    assert cap["credited_to_architecture"] is False and cap["gates_affected"] is False
    assert cap["labels"]["large"]["allowance"] == {"case_cost_usd": 5.0}
    assert cap["labels"]["small"]["allowance"] == {"case_cost_usd": 1.0}
    assert cap["labels"]["large"]["aggregate"]["task_completion"]["denominator"] == 60
    assert "never credited" in cap["note"]
    model = m["separate_results"]["model"]
    assert model["labels"]["m2"]["conditions"]["models"] == ["m2"]
    assert model["credited_to_architecture"] is False


def test_a_report_of_the_wrong_mode_is_refused_as_a_separate_result():
    with pytest.raises(ReadinessRefused, match="capability"):
        readiness(capability=campaign_report())
    with pytest.raises(ReadinessRefused, match="model"):
        readiness(model=alternate("capability", CAPABILITY_SPEC))


def test_a_model_comparison_cannot_be_the_gating_report():
    report_ = alternate("model", MODEL_SPEC)
    m = build_readiness(report_, candidate="m1", baseline=None, scenarios=SCENARIOS_PASSED,
                        references=REFS)
    assert gate(m, "comparison")["status"] == "incomparable"
    assert m["status"] == "blocked"


# --- slice 4: the declared workload, the authorized profile, performance and cost --------


def full(report_=None, **kwargs):
    """Every input a ready fixture needs. Logic only: nothing here is measured evidence."""
    kwargs.setdefault("workload", WORKLOAD)
    kwargs.setdefault("profile", PROFILE)
    kwargs.setdefault("measurements", measurements())
    kwargs.setdefault("approvals", APPROVED)
    return readiness(report_, **kwargs)


def test_a_complete_synthetic_fixture_is_the_only_way_to_evidence_met_and_authorizes_nothing():
    m = full()
    assert m["status"] == "evidence_met" and m["blocking"] == []
    assert {g["status"] for g in m["gates"].values()} == {"met"}
    assert any("authorizes no release" in n for n in m["notes"])
    assert m["human_review_gaps"] == ["release_owner_decision: no named person has recorded "
                                      "the release decision; this manifest decides nothing"]


def test_queue_inclusive_p95_tool_model_time_and_resources_are_reported_per_class():
    perf = gate(full(), "workload")
    ordinary = perf["classes"]["ordinary"]
    assert perf["status"] == "met"
    assert ordinary["total_p95_ms"] == 1370           # the slowest are failures: still counted
    assert ordinary["failures"] == 3 and ordinary["n"] == 40
    assert ordinary["queue_p95_ms"] == 137 and ordinary["cap_p95_ms"] == 2000
    assert ordinary["tool_p95_ms"] == 87 and ordinary["model_p95_ms"] == 637
    assert perf["classes"]["deep"]["total_p95_ms"] == 29000
    assert perf["classes"]["ingestion"]["n"] == 5
    assert perf["resources"] == {"peak_memory_mb": 900, "peak_connections": 40, "lock_waits": 3,
                                 "max_lock_wait_ms": 120}


def test_total_cost_per_successful_task_includes_the_failed_requests():
    cost = gate(full(), "cost")
    assert cost["status"] == "met"
    assert cost["total_usd"] == pytest.approx(0.90)
    assert cost["successes"] == 47 and cost["failures"] == 3
    assert cost["cost_per_successful_task"] == pytest.approx(0.90 / 47)
    assert cost["cap_per_successful_task_usd"] == 0.02
    assert cost["ingestion_usd"] == pytest.approx(0.01)


def test_latency_memory_connections_and_lock_pressure_over_the_profile_are_not_met():
    slow = measurements(samples=[dict(s, total_ms=s["total_ms"] * 3) for s in
                                 measurements()["samples"]])
    g = gate(full(measurements=slow), "workload")
    assert g["status"] == "not_met"
    assert any("ordinary" in r and "p95" in r for r in g["reasons"])
    heavy = measurements(resources={"peak_memory_mb": 2048, "peak_connections": 90,
                                    "lock_waits": 40, "max_lock_wait_ms": 900})
    g = gate(full(measurements=heavy), "workload")
    assert g["status"] == "not_met"
    text = " ".join(g["reasons"])
    assert "memory" in text and "connections" in text and "lock" in text


def test_no_measurement_is_not_measured_for_performance_and_cost():
    m = full(measurements=None)
    assert gate(m, "workload")["status"] == "not_measured"
    assert gate(m, "cost")["status"] == "not_measured"
    assert m["status"] == "blocked"


def test_fake_provider_or_in_process_measurements_are_a_contract_check_not_capacity():
    fake = full(measurements=measurements(providers="fake"))
    assert gate(fake, "workload")["status"] == "contract_only"
    assert gate(fake, "cost")["status"] == "contract_only"
    in_process = full(measurements=measurements(environment={"database": "sqlite",
                                                              "workers": "in_process"}))
    assert gate(in_process, "workload")["status"] == "contract_only"
    assert fake["status"] == "blocked" and in_process["status"] == "blocked"


def test_a_measurement_of_another_workload_or_made_before_it_was_declared_is_refused():
    other = full(measurements=measurements(workload_sha256="f" * 64))
    assert gate(other, "workload")["status"] == "incomparable"
    early = full(measurements=measurements(started_at="2026-10-19T00:00:00+00:00"))
    g = gate(early, "workload")
    assert g["status"] == "not_met" and any("before" in r and "declared" in r for r in g["reasons"])


def test_latency_that_is_not_queue_inclusive_is_not_measured():
    bare = [{k: v for k, v in s.items() if k != "queue_ms"} for s in measurements()["samples"]]
    g = gate(full(measurements=measurements(samples=bare)), "workload")
    assert g["status"] == "not_measured"
    assert any("queue" in r for r in g["reasons"])


def test_fewer_samples_than_the_declared_mix_is_inconclusive():
    few = [s for s in measurements()["samples"] if not (s["class"] == "deep" and s["queue_ms"] > 103)]
    g = gate(full(measurements=measurements(samples=few)), "workload")
    assert g["status"] == "inconclusive"
    assert any("deep" in r and "4" in r and "10" in r for r in g["reasons"])


def test_unknown_usage_is_counted_at_its_reservation_and_blocks_the_cost_gate():
    unknown = measurements()
    unknown["samples"][5] = dict(unknown["samples"][5], usage_reported=False, cost_usd=0.5)
    g = gate(full(measurements=unknown), "cost")
    assert g["status"] == "not_met"                    # the conservative figure breaks the cap
    assert g["unknown_usage_samples"] == 1
    assert g["total_usd"] == pytest.approx(0.90 - 0.01 + 0.5)
    assert any("usage" in r and "unknown" in r for r in g["reasons"])
    small = measurements()
    small["samples"][5] = dict(small["samples"][5], usage_reported=False, cost_usd=0.01)
    g = gate(full(measurements=small), "cost")
    assert g["status"] == "inconclusive"               # under the cap, but usage is incomplete
    assert g["unknown_usage_samples"] == 1


def test_usage_with_no_figure_at_all_cannot_be_bounded():
    blank = measurements()
    blank["samples"][5] = dict(blank["samples"][5], usage_reported=False, cost_usd=None)
    g = gate(full(measurements=blank), "cost")
    assert g["status"] == "not_measured" and g["unbounded_samples"] == 1
    assert g["cost_per_successful_task"] is None


def test_campaign_spend_with_missing_usage_keeps_the_cost_gate_open():
    from .test_campaign_report import attempt

    runs = campaign(runtime={"attempts": [attempt("llm", 0.01, reported=False)]})
    g = gate(full(campaign_report(runs=runs)), "cost")
    assert g["status"] == "inconclusive"
    assert g["campaign"]["cold"]["cost_status"] == "incomplete"
    assert g["campaign"]["cold"]["conservative_usd"] == pytest.approx(0.6)
    assert any("campaign" in r and "missing usage" in r for r in g["reasons"])


# --- the live-collection preflight -------------------------------------------------------


def test_a_complete_declaration_profile_and_approvals_allow_live_collection():
    out = collection_preflight(WORKLOAD, PROFILE, APPROVED)
    assert out["allowed"] is True and out["unrecorded"] == []
    assert full()["live_collection"] == {"allowed": True, "unrecorded": []}


def test_a_missing_operational_cap_blocks_live_collection_and_is_named():
    caps = {k: v for k, v in CAPS.items() if k != "max_cost_usd"}
    out = collection_preflight(WORKLOAD, {**PROFILE, "caps": caps}, APPROVED)
    assert out["allowed"] is False
    assert out["unrecorded"] == ["profile.caps.max_cost_usd"]
    zero = collection_preflight(WORKLOAD, {**PROFILE, "caps": {**CAPS, "deadline_seconds": 0}},
                                APPROVED)
    assert "profile.caps.deadline_seconds" in zero["unrecorded"]


def test_missing_paid_provider_or_data_approvals_block_live_collection():
    out = collection_preflight(WORKLOAD, PROFILE, {k: v for k, v in APPROVED.items()
                                                    if k != "dataset_transmission"})
    assert out["allowed"] is False
    assert out["unrecorded"] == ["approvals.dataset_transmission"]
    assert "approvals.funding" in collection_preflight(WORKLOAD, PROFILE, None)["unrecorded"]


def test_an_unauthorized_profile_or_incomplete_declaration_blocks_live_collection():
    unsigned = {k: v for k, v in PROFILE.items() if k != "authorized_by"}
    assert "profile.authorized_by" in collection_preflight(WORKLOAD, unsigned, APPROVED)["unrecorded"]
    thin = {k: v for k, v in WORKLOAD.items() if k not in ("declared_at", "mix")}
    missing = collection_preflight(thin, PROFILE, APPROVED)["unrecorded"]
    assert "workload.declared_at" in missing and "workload.mix" in missing
    assert collection_preflight(None, None, APPROVED)["allowed"] is False
    no_deep = {**WORKLOAD, "mix": {"ordinary": 40, "ingestion": 5}}
    assert "workload.mix.deep" in collection_preflight(no_deep, PROFILE, APPROVED)["unrecorded"]
    for dropped in ("latency", "cost", "resources"):
        bare = {k: v for k, v in PROFILE.items() if k != dropped}
        assert any(m.startswith(f"profile.{dropped}") for m in
                   collection_preflight(WORKLOAD, bare, APPROVED)["unrecorded"])


def test_without_authorization_the_manifest_says_so_and_is_blocked():
    m = full(profile=None, approvals=None)
    assert gate(m, "authorization")["status"] == "not_measured"
    assert m["live_collection"]["allowed"] is False
    assert m["status"] == "blocked"


# --- the independent demonstration -------------------------------------------------------


def test_a_missing_worker_and_browser_result_a_breach_and_unknown_usage_yield_blocked_readiness():
    revs = reviews({("runtime", 1, "A01-4"): {"access_breach": True}})
    unknown = measurements()
    unknown["samples"][3] = dict(unknown["samples"][3], usage_reported=False, cost_usd=0.01)
    m = full(campaign_report(revs=revs), measurements=unknown,
             scenarios=without(SCENARIOS_PASSED, "durability", "browser"))
    assert m["status"] == "blocked"
    # The campaign report's own verdict blocks too (it read the breach): the comparison gate
    # no longer ignores enablement_blocked.
    assert {name: g["status"] for name, g in m["gates"].items() if g["status"] != "met"} == {
        "comparison": "not_met", "safety": "breached", "postgres_workers": "not_measured",
        "browser_accessibility": "not_measured", "cost": "inconclusive"}
    assert gate(m, "quality")["status"] == "met"          # the average is fine; it does not matter
    assert len(m["blocking"]) >= 4


# --- slice 5: the versioned manifest cutover preflight reads -------------------------------


def sealed(manifest):
    """Recompute the self-digest the way a forger who edits the file would have to."""
    body = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    return {**body, "manifest_sha256": canonical_digest(body)}


def test_the_manifest_is_versioned_self_digested_and_byte_for_byte_reproducible():
    a, b = full(), full()
    assert a["schema_version"] == "release-readiness-1" and a["issue"] == "IR-741"
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["manifest_sha256"] == sealed(a)["manifest_sha256"]
    assert verify_manifest(a) == []
    assert verify_manifest(readiness()) == []              # a blocked manifest is also sound


def read_full(**over):
    """``read`` for assert_ready over the in-memory files ``full()`` was built from."""
    report_ = campaign_report()
    files = {"report": report_, "baseline": frozen(report_), "scenarios": SCENARIOS_PASSED,
             "workload": WORKLOAD, "profile": PROFILE, "measurements": measurements(),
             "approvals": APPROVED, **over}
    by_path = {REFS[k]["path"]: (REFS[k]["sha256"], v) for k, v in files.items()}

    def read(path):
        if path not in by_path:
            raise OSError(f"no such file {path}")
        return by_path[path]
    return read


def test_a_ready_manifest_passes_the_cutover_check_and_a_blocked_one_is_refused_with_why():
    assert_ready(full(), expect_commit="rt1", read=read_full())
    blocked = readiness()
    with pytest.raises(ReadinessRefused) as caught:
        assert_ready(blocked, expect_commit="rt1", read=read_full())
    assert "blocked" in str(caught.value) and "workload" in str(caught.value)


def test_a_manifest_edited_to_say_ready_is_caught_even_when_resealed():
    forged = {**readiness(), "status": "evidence_met", "blocking": []}
    assert any("digest" in p for p in verify_manifest(forged))
    resealed = sealed(forged)
    problems = verify_manifest(resealed)
    assert any("evidence_met" in p and "not met" in p for p in problems)
    with pytest.raises(ReadinessRefused):
        assert_ready(resealed, expect_commit="rt1", read=read_full())


def test_a_manifest_for_another_commit_or_schema_or_with_a_gate_removed_is_refused():
    ready = full()
    with pytest.raises(ReadinessRefused, match="commit"):
        assert_ready(ready, expect_commit="other", read=read_full())
    assert any("schema" in p for p in verify_manifest(sealed({**ready, "schema_version": "x"})))
    gates = {k: v for k, v in ready["gates"].items() if k != "safety"}
    assert any("safety" in p for p in verify_manifest(sealed({**ready, "gates": gates})))


def test_a_met_gate_without_an_evidence_reference_is_a_problem():
    ready = full()
    gates = copy.deepcopy(ready["gates"])
    gates["quality"]["evidence"] = []
    problems = verify_manifest(sealed({**ready, "gates": gates}))
    assert any("quality" in p and "reference" in p for p in problems)


# --- review hardening: ways a gate must not be met -------------------------------------------


def test_a_report_that_lists_no_set_families_cannot_gate_quality():
    old = campaign_report()
    del old["set_families"]
    g = gate(readiness(old), "quality")
    assert g["status"] == "not_measured" and any("set_families" in r for r in g["reasons"])


def test_a_repetition_that_reviewed_fewer_than_ten_cases_of_a_family_is_inconclusive():
    skip = {("runtime", 1, f"A01-{i}") for i in range(4)}
    g = gate(readiness(campaign_report(revs=reviews(skip=skip), counted=False)), "quality")
    assert g["status"] != "met"
    assert any("runtime-1" in r and "A01" in r and "reviewed cases" in r for r in g["reasons"])


def test_a_baseline_with_unrecorded_conditions_or_fake_providers_is_not_a_baseline():
    fake = campaign_report(runs=campaign(providers="fake"), counted=False)
    assert gate(readiness(baseline=pinned(fake)), "baseline")["status"] != "met"
    hollow = campaign_report()
    hollow["arms"]["controller"]["conditions"]["corpus_snapshot_digest"] = None
    g = gate(readiness(baseline=pinned(hollow)), "baseline")
    assert g["status"] == "incomparable" and any("corpus_snapshot_digest" in r
                                                  for r in g["reasons"])


def test_a_browser_check_with_no_evidence_reference_or_an_unknown_candidate_is_not_measured():
    bare = copy.deepcopy(SCENARIOS_PASSED)
    del bare["browser"]["checks"]["mobile"]["evidence_ref"]
    g = gate(readiness(scenarios=bare), "browser_accessibility")
    assert g["status"] == "not_measured" and any("mobile" in r for r in g["reasons"])
    report_ = campaign_report()
    report_["arms"]["runtime"]["git_commit"] = None
    g = gate(readiness(report_), "browser_accessibility")
    assert g["status"] == "not_measured" and any("commit is unknown" in r for r in g["reasons"])


def test_a_naive_timestamp_is_a_clean_block_not_a_crash():
    g = gate(full(measurements=measurements(started_at="2026-10-21T00:00:00")), "workload")
    assert g["status"] == "not_measured" and any("timezone" in r for r in g["reasons"])


def test_a_measurement_run_below_the_declared_concurrency_is_incomparable():
    g = gate(full(measurements=measurements(concurrency=1)), "workload")
    assert g["status"] == "incomparable" and any("concurrency" in r for r in g["reasons"])
    absent = measurements()
    del absent["concurrency"]
    assert gate(full(measurements=absent), "workload")["status"] == "not_measured"


def test_a_class_where_every_sample_failed_is_not_met_whatever_its_latency():
    m = measurements()
    for s in m["samples"]:
        if s["class"] == "ordinary":
            s["outcome"] = "failed"
    g = gate(full(measurements=m), "workload")
    assert g["status"] == "not_met" and any("every ordinary sample failed" in r
                                            for r in g["reasons"])


def test_cost_is_judged_only_from_a_measurement_of_the_declared_workload():
    g = gate(full(measurements=measurements(workload_sha256="0" * 64)), "cost")
    assert g["status"] == "incomparable"
    in_process = measurements(environment={"database": "sqlite", "workers": "threads"})
    assert gate(full(measurements=in_process), "cost")["status"] == "contract_only"


def test_a_negative_cost_cannot_lower_the_total_it_is_unbounded():
    m = measurements()
    m["samples"][0]["cost_usd"] = -5.0
    g = gate(full(measurements=m), "cost")
    assert g["status"] == "not_measured"
    assert any("cost_usd must be a non-negative number" in r for r in g["reasons"])


def test_verify_reads_a_file_as_write_run_wrote_it_and_survives_malformed_manifests():
    m = full()
    stamped = {**m, "commit": "abc123"}
    assert verify_manifest(stamped) == []
    assert verify_manifest([]) == ["the manifest is not a JSON object"]
    assert any("no gates object" in p for p in verify_manifest({**m, "gates": []}))
    bad = {**m, "gates": {**m["gates"], "quality": "met"}}
    assert any("gate quality is not an object" in p for p in verify_manifest(bad))


def test_the_manifest_records_every_input_it_was_given():
    m = readiness()
    assert m["inputs"] == {k: v for k, v in sorted(REFS.items())}


# --- IR-608 provenance: a commit is recorded by the producer or it is unverified ---------------


def _with(name, **change):
    rows = copy.deepcopy(SCENARIOS_PASSED)
    rows[name].update(change)
    return rows


@pytest.mark.parametrize("name,gate_name", [("access_and_recovery", "access_disclosure"),
                                            ("durability", "postgres_workers")])
def test_a_suite_row_with_no_commit_is_unverified_and_blocks(name, gate_name):
    rows = copy.deepcopy(SCENARIOS_PASSED)
    del rows[name]["git_commit"]
    g = gate(readiness(scenarios=rows), gate_name)
    assert g["status"] == "not_measured" and g["provenance"] == "unverified"
    assert any("never inferred" in r for r in g["reasons"])


@pytest.mark.parametrize("recorded", ["unknown", "", None])
def test_an_unknown_commit_is_not_provenance(recorded):
    g = gate(readiness(scenarios=_with("durability", git_commit=recorded)), "postgres_workers")
    assert g["status"] == "not_measured" and g["provenance"] == "unverified"


def test_a_suite_run_at_another_commit_or_a_dirty_tree_is_incomparable():
    for commit in ("old1", "rt1-dirty"):
        g = gate(readiness(scenarios=_with("access_and_recovery", git_commit=commit)),
                 "access_disclosure")
        assert g["status"] == "incomparable" and g["provenance"] == "mismatch"
        assert commit in " ".join(g["reasons"])


def test_a_suite_at_the_candidates_commit_is_verified():
    g = gate(readiness(), "postgres_workers")
    assert g["status"] == "met" and g["provenance"] == "verified" and g["git_commit"] == "rt1"


def test_the_run_level_commit_of_an_eval_scenarios_file_reaches_its_rows_marked_as_such():
    bare = {k: {x: y for x, y in v.items() if x != "git_commit"}
            for k, v in SCENARIOS_PASSED.items() if k != "browser"}
    run = {"schema_version": 1, "issue": "IR-608", "git_commit": "rt1", "providers": "fake",
           "scenarios": {**bare, "browser": SCENARIOS_PASSED["browser"]}}
    rows = scenario_rows(run)
    assert rows["durability"]["git_commit"] == "rt1"
    assert rows["durability"]["git_commit_source"] == "run_file"
    assert rows["browser"]["git_commit"] == "rt1" and "git_commit_source" not in rows["browser"]
    g = gate(readiness(scenarios=rows), "postgres_workers")
    assert g["status"] == "met" and g["git_commit_source"] == "run_file"


def test_nothing_is_filled_in_when_the_run_records_no_commit():
    bare = {k: v for k, v in SCENARIOS_PASSED["durability"].items() if k != "git_commit"}
    run = {"scenarios": {"durability": bare}}
    assert "git_commit" not in scenario_rows(run)["durability"]
    unknown = {**run, "git_commit": "unknown"}
    assert "git_commit" not in scenario_rows(unknown)["durability"]
    own = {"git_commit": "rt1", "scenarios": {"durability": {"git_commit": "mine"}}}
    assert scenario_rows(own)["durability"]["git_commit"] == "mine"
    assert scenario_rows(None) == {} and scenario_rows([]) == {}


def test_a_row_the_real_browser_producer_writes_clears_the_browser_gate():
    """The IR-608 producer keeps no private reference, only that one was recorded."""
    evidence = {"operator": "Operator One", "timestamp_utc": "2026-11-01T00:00:00+00:00",
                "git_commit": "rt1", "browser": "Chrome 130", "viewport": "390x844",
                "conversation_id": "c1",
                "checks": {n: {"status": "measured", "passed": True, "evidence_ref": f"p/{n}"}
                           for n in SCENARIOS_PASSED["browser"]["checks"]}}
    row = browser_result(evidence)
    assert "p/live" not in json.dumps(row)
    g = gate(readiness(scenarios={**SCENARIOS_PASSED, "browser": row}), "browser_accessibility")
    assert g["status"] == "met" and g["provenance"] == "verified"


# --- success counts and the policy limitation ---------------------------------------------------


def test_the_workload_reports_successes_failures_and_observed_rates_per_class():
    g = gate(full(), "workload")
    assert g["classes"]["ordinary"]["successes"] == 37
    assert g["classes"]["ordinary"]["failures"] == 3
    assert g["classes"]["ordinary"]["observed_success_rate"] == pytest.approx(0.925)
    assert g["classes"]["deep"]["observed_success_rate"] == 1.0
    assert g["classes"]["ingestion"]["successes"] == 5
    assert g["classes"]["ordinary"]["min_success_rate"] == 0.9
    assert "min_success_rate" in g["success_rate_policy"]


def test_a_success_rate_below_the_authorized_minimum_is_not_met():
    # Decided 2026-11-07: a low but not total failure rate now blocks (it used to pass).
    m = measurements()
    for s in m["samples"]:
        if s["class"] == "ordinary" and s["total_ms"] < 1300:
            s["outcome"] = "failed"
    g = gate(full(measurements=m), "workload")
    assert g["classes"]["ordinary"]["observed_success_rate"] < 0.25
    assert g["status"] == "not_met"
    assert any("ordinary success rate" in r and "below the authorized 0.9" in r
               for r in g["reasons"])
    # At exactly the minimum it passes: 36/40 = 0.9.
    edge = measurements()
    edge["samples"][36] = dict(edge["samples"][36], outcome="failed")
    assert gate(full(measurements=edge), "workload")["status"] == "met"


@pytest.mark.parametrize("value", [None, 0, -0.5, 1.5, float("inf"), "0.9", True])
def test_the_minimum_success_rate_must_be_authorized_as_a_rate(value):
    profile = copy.deepcopy(PROFILE)
    profile["success"] = {} if value is None else {"min_success_rate": value}
    assert "profile.success.min_success_rate" in collection_preflight(
        WORKLOAD, profile, APPROVED)["unrecorded"]
    assert gate(full(profile=profile), "workload")["status"] == "not_measured"


def test_every_manifest_lists_the_policy_decisions_it_applies_and_who_made_them():
    ids = {d["id"] for d in full()["policy_decisions"]}
    assert ids == {"objectives_on_point_estimate", "minimum_success_rate", "commit_from_run_file"}
    assert all(d["status"] == "confirmed" and d["decided_by"] == "Jive Tyler Revalde"
               and d["decided_on"] == "2026-11-07" for d in POLICY_DECISIONS)
    q = gate(full(), "quality")["repetitions"][0]["overall"]["task_completion"]
    assert {"wilson_low", "wilson_high", "value", "target"} <= set(q)   # reported, not gated


# --- workload-measurement-1: the contract a producer writes to ----------------------------------


def test_the_fixture_measurement_satisfies_the_contract():
    assert validate_measurement(measurements()) == []


@pytest.mark.parametrize("field,value,fragment", [
    ("schema_version", "workload-measurement-2", "schema_version"),
    ("run_id", "", "run_id"), ("providers", "mock", "providers"),
    ("environment", {"database": "postgresql"}, "environment"),
    ("started_at", "2026-10-21T00:00:00", "timezone-aware"),
    ("concurrency", 0, "concurrency"), ("workload_sha256", "abc", "workload_sha256"),
    ("workload_sha256", "Z" * 64, "workload_sha256"),
    ("resources", {"peak_memory_mb": -1, "peak_connections": 1, "lock_waits": 0,
                   "max_lock_wait_ms": 0}, "peak_memory_mb"),
    ("resources", [], "resources must be an object"),
    ("samples", "none", "samples must be a list")])
def test_each_top_level_defect_is_named(field, value, fragment):
    problems = validate_measurement(measurements(**{field: value}))
    assert problems and any(fragment in p for p in problems)


def test_each_sample_defect_is_named():
    m = measurements()
    m["samples"][0].update(total_ms=10, queue_ms=500)
    m["samples"][1]["class"] = "bulk"
    m["samples"][2]["usage_reported"] = "yes"
    m["samples"][3]["cost_usd"] = -1
    m["samples"][4]["outcome"] = ""
    m["samples"][5] = "not an object"
    text = " ".join(validate_measurement(m))
    for fragment in ("total_ms must include queue_ms", "class must be one of",
                     "usage_reported must be true or false", "cost_usd must be",
                     "outcome must be", "samples[5] is not an object"):
        assert fragment in text


def test_a_task_sample_needs_queue_and_total_but_ingestion_and_optional_times_may_be_absent():
    m = measurements()
    del m["samples"][0]["queue_ms"]
    assert any("queue_ms" in p for p in validate_measurement(m))
    ok = measurements()
    ok["samples"][0]["tool_ms"] = None
    for s in ok["samples"]:
        if s["class"] == "ingestion":
            s.pop("queue_ms", None)
    assert validate_measurement(ok) == []
    assert validate_measurement([]) == ["the measurement is not a JSON object"]


def test_the_problem_list_is_bounded():
    m = measurements()
    for s in m["samples"]:
        s["class"] = "bulk"
    assert len(validate_measurement(m, limit=5)) <= 6


def test_a_malformed_measurement_blocks_both_gates_instead_of_crashing_them():
    junk = measurements(samples=[1, None, "x"])
    for name in ("workload", "cost"):
        g = gate(full(measurements=junk), name)
        assert g["status"] == "not_measured" and any("not a well-formed" in r
                                                     for r in g["reasons"])


def test_a_well_formed_file_is_still_not_evidence_when_it_declares_fake_providers():
    fake = measurements(providers="fake")
    assert validate_measurement(fake) == []
    assert gate(full(measurements=fake), "workload")["status"] == "contract_only"
    assert gate(full(measurements=fake), "cost")["status"] == "contract_only"


# --- second review: evidence that cleared a gate it must not --------------------------------


def _deep(value, *path):
    out = copy.deepcopy(value)
    node = out
    for key in path[:-1]:
        node = node[key]
    return out, node, path[-1]


def test_campaign_spend_with_no_cache_state_cannot_clear_the_cost_gate():
    report_ = campaign_report()
    spend = report_["arms"]["runtime"]["spend"]
    spend["unknown_cache"] = spend["cold"]["conversations"]
    spend["cold"] = {**spend["cold"], "conversations": 0}
    g = gate(full(report_), "cost")
    assert g["status"] != "met"
    assert any("no cold or warm cache" in r for r in g["reasons"])
    assert any("no cold or warm spend" in r for r in g["reasons"])


@pytest.mark.parametrize("field,value", [("corpus_snapshot_digest", "other"),
                                         ("model_ids", {"answer": "m2"}),
                                         ("data_policy", "training-allowed"),
                                         ("cache_state", "warm")])
def test_a_workload_declared_under_other_conditions_is_incomparable(field, value):
    other = {**WORKLOAD, field: value}
    m = full(workload=other, measurements=measurements(workload=other))
    for name in ("workload", "cost"):
        assert gate(m, name)["status"] == "incomparable"
        assert any("differ from the conditions" in r for r in gate(m, name)["reasons"])


@pytest.mark.parametrize("commit,status", [("zzz", "incomparable"), (None, "not_measured")])
def test_a_measurement_not_tied_to_the_candidates_commit_does_not_clear(commit, status):
    m = full(measurements=measurements(git_commit=commit))
    assert gate(m, "workload")["status"] == status and gate(m, "cost")["status"] == status


def test_infinite_caps_and_measurements_are_not_numbers():
    endless = copy.deepcopy(PROFILE)
    endless["latency"]["ordinary_p95_ms"] = float("inf")
    endless["caps"]["max_cost_usd"] = float("inf")
    missing = collection_preflight(WORKLOAD, endless, APPROVED)["unrecorded"]
    assert "profile.latency.ordinary_p95_ms" in missing and "profile.caps.max_cost_usd" in missing
    slow = measurements()
    slow["samples"][0] = dict(slow["samples"][0], total_ms=float("inf"))
    assert any("total_ms" in d for d in validate_measurement(slow))
    assert gate(full(measurements=slow), "workload")["status"] == "not_measured"


def test_a_dirty_tree_never_verifies_even_against_the_same_dirty_candidate():
    report_ = campaign_report(runs=campaign(runtime={"git_commit": "rt1-dirty"}))
    rows = {k: {**v, "git_commit": "rt1-dirty"} for k, v in SCENARIOS_PASSED.items()}
    m = full(report_, scenarios=rows, baseline=pinned(report_),
             measurements=measurements(git_commit="rt1-dirty"))
    for name in ("access_disclosure", "postgres_workers", "browser_accessibility", "workload"):
        assert gate(m, name)["status"] == "not_measured", name
    with pytest.raises(ReadinessRefused, match="clean commit"):
        assert_ready(full(), expect_commit="rt1-dirty", read=read_full())


def test_assert_ready_rebuilds_the_manifest_so_a_resealed_edit_does_not_pass():
    ready = full()
    gates = copy.deepcopy(ready["gates"])
    gates["cost"]["cost_per_successful_task"] = 0.0001
    edited = sealed({**ready, "gates": gates})
    assert verify_manifest(edited) == []                      # consistent, so only a rebuild sees it
    with pytest.raises(ReadinessRefused, match="does not follow from its inputs"):
        assert_ready(edited, expect_commit="rt1", read=read_full())
    with pytest.raises(ReadinessRefused, match="inputs do not record"):
        assert_ready(sealed({**ready, "inputs": {}}), expect_commit="rt1", read=read_full())
    with pytest.raises(ReadinessRefused, match="changed since"):
        assert_ready(ready, expect_commit="rt1",
                     read=lambda p: ("0" * 64, read_full()(p)[1]))


def test_a_met_gate_citing_evidence_the_inputs_do_not_record_is_a_problem():
    ready = full()
    gates = copy.deepcopy(ready["gates"])
    gates["quality"]["evidence"] = [{"name": "report", "path": "made/up.json", "sha256": "f" * 64}]
    assert any("quality cites report" in p for p in verify_manifest(sealed({**ready,
                                                                             "gates": gates})))


def test_report_numbers_are_recomputed_from_their_counts():
    report_ = campaign_report()
    rep = report_["arms"]["runtime"]["repetitions"][0]
    rep["scores"]["overall"]["task_completion"]["value"] = float("nan")
    assert gate(full(report_), "quality")["status"] == "incomparable"

    report_ = campaign_report()
    fam = report_["arms"]["runtime"]["repetitions"][0]["scores"]["families"]["A01"]
    fam["task_completion"] = {**fam["task_completion"], "numerator": 0, "value": 1.0}
    g = gate(full(report_), "quality")
    assert g["status"] != "met" and any("is not 0/" in r for r in g["reasons"])


def test_repeated_cases_and_repetitions_count_once():
    report_ = campaign_report()
    report_["arms"]["runtime"]["family_cases"]["A01"] = ["A01-0"] * 10
    assert gate(full(report_), "quality")["families"]["A01"]["distinct_cases"] == 1

    report_ = campaign_report()
    reps = report_["arms"]["runtime"]["repetitions"]
    reps[1:] = [copy.deepcopy(reps[0]), copy.deepcopy(reps[0])]
    g = gate(full(report_), "quality")
    assert g["status"] != "met" and any("more than once" in r for r in g["reasons"])


def test_set_families_must_name_every_family_that_ran():
    report_ = campaign_report()
    report_["set_families"] = ["A15"]
    g = gate(full(report_), "quality")
    assert g["status"] != "met"
    assert any("not in the report's set_families" in r for r in g["reasons"])


def test_the_campaign_reports_own_block_and_excluded_runs_are_read():
    report_ = campaign_report()
    report_.update(enablement_blocked=True, blocking=["controller: something"])
    assert gate(full(report_), "comparison")["status"] == "not_met"
    report_ = campaign_report()
    report_["excluded_runs"] = [{"run_id": "runtime-9", "reason": "reused conversation"}]
    assert gate(full(report_), "comparison")["status"] == "inconclusive"


def test_a_candidate_cannot_be_its_own_baseline():
    report_ = campaign_report()
    g = gate(full(report_, baseline=pinned(report_, arm="runtime")), "baseline")
    assert g["status"] == "incomparable" and any("own baseline" in r for r in g["reasons"])
    assert g["pin_source"] == "operator_argument"


def test_required_measures_cannot_be_absent_or_junk():
    untimed = measurements()
    for s in untimed["samples"]:
        s.pop("tool_ms"), s.pop("model_ms")
    assert gate(full(measurements=untimed), "workload")["status"] == "not_measured"

    nobody = copy.deepcopy(SCENARIOS_PASSED)
    nobody["browser"]["operator"] = ""
    assert gate(full(scenarios=nobody), "browser_accessibility")["status"] == "not_measured"

    junk = copy.deepcopy(SCENARIOS_PASSED)
    junk["durability"]["tests"] = "many"
    assert gate(full(scenarios=junk), "postgres_workers")["status"] == "not_measured"

    broken = measurements()
    for s in broken["samples"]:
        if s["class"] == "ingestion":
            s.update(outcome="failed", cost_usd=None)
    m = full(measurements=broken)
    assert gate(m, "workload")["status"] == "not_met"
    assert gate(m, "cost")["status"] == "not_measured" and gate(m, "cost")["ingestion_usd"] is None
