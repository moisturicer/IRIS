"""The chained-decision scorer (IR-486): every arm offline, with fakes."""

import json
from pathlib import Path

import pytest

from apps.ai.evaluation import chain as c
from apps.ai.evaluation.chain import (
    ARM_CHAIN,
    ARM_CONTROL,
    ARM_DETECTOR,
    ARM_JEV,
    ARM_JEV_FAILURE,
    ARM_LABEL,
    ARM_STRUCTURAL,
    ARM_TOOL,
    DIRECT,
    SEARCH,
    Bands,
    ChainError,
    DeciderRun,
    Facts,
)
from apps.ai.evidence.model_decision import (
    REASON_ANSWERED_DIRECTLY,
    REASON_MALFORMED_RESPONSE,
    REASON_RATE_LIMITED,
    REASON_SEARCH_REQUESTED,
    ROUTE_DIRECT,
    ROUTE_EVIDENCE,
    ModelDecision,
)

BANDS = Bands(search_cutoff=0.5, direct_cutoff=0.2)


def jev(p, cost=0.001, latency=900):
    needs = p >= 0.5
    return ModelDecision(
        route=ROUTE_EVIDENCE if needs else ROUTE_DIRECT,
        reason=REASON_SEARCH_REQUESTED if needs else REASON_ANSWERED_DIRECTLY,
        latency_ms=latency,
        probability=p,
        cost_usd=cost,
        model="jev",
    )


def jev_down(reason=REASON_RATE_LIMITED):
    return ModelDecision(route=ROUTE_EVIDENCE, reason=reason, latency_ms=50, model="jev")


def llm(search, latency=2500):
    return ModelDecision(
        route=ROUTE_EVIDENCE if search else ROUTE_DIRECT,
        reason=REASON_SEARCH_REQUESTED if search else REASON_ANSWERED_DIRECTLY,
        latency_ms=latency,
        model="label",
    )


def llm_down():
    return ModelDecision(
        route=ROUTE_EVIDENCE, reason="provider_failure", latency_ms=10, model="label"
    )


def facts(qid="q", *, needs=True, tolerated=False, detector=False, structural=False, kind="k"):
    return Facts(
        question_id=qid,
        kind=kind,
        expects_evidence=needs,
        search_tolerated=tolerated,
        detector_fires=detector,
        structural_fires=structural,
    )


# -- the policy: proposal 12 §5.1, row by row --------------------------------


@pytest.mark.parametrize(
    "case, f, first, second, expected_route, expected_reason",
    [
        ("structural", facts(structural=True), jev(0.01), llm(False), SEARCH, c.R_STRUCTURAL),
        ("detector", facts(detector=True), jev(0.01), llm(False), SEARCH, c.R_DETECTOR),
        ("jev high", facts(), jev(0.9), llm(False), SEARCH, c.R_JEV_SEARCH),
        ("jev uncertain", facts(), jev(0.3), llm(False), SEARCH, c.R_JEV_UNCERTAIN),
        ("jev low, llm search", facts(), jev(0.05), llm(True), SEARCH, c.R_LLM_SEARCH),
        ("jev low, llm answer", facts(needs=False), jev(0.05), llm(False), DIRECT, c.R_BOTH_PERMIT),
        ("jev low, llm down", facts(), jev(0.05), llm_down(), SEARCH, c.R_LLM_FAILED),
        ("jev down, llm search", facts(), jev_down(), llm(True), SEARCH, c.R_JEV_FAILED_LLM_SEARCH),
        ("jev down, llm answer", facts(needs=False), jev_down(), llm(False), DIRECT, c.R_LLM_ALONE_DIRECT),
        ("both down", facts(), jev_down(), llm_down(), SEARCH, c.R_JEV_FAILED_LLM_FAILED),
        ("jev malformed, llm answer", facts(needs=False), jev_down(REASON_MALFORMED_RESPONSE), llm(False), DIRECT, c.R_LLM_ALONE_DIRECT),
    ],
)
def test_the_decision_table(case, f, first, second, expected_route, expected_reason):
    outcome = c.chain(f, first, second, BANDS)
    assert (outcome.route, outcome.reason) == (expected_route, expected_reason), case


def test_a_model_never_turns_a_rule_search_into_a_direct_answer():
    for f in (facts(structural=True), facts(detector=True)):
        for first in (jev(0.0), jev_down(), None):
            for second in (llm(False), llm_down(), None):
                assert c.chain(f, first, second, BANDS).route == SEARCH
                assert c.chain(f, None, second, BANDS, force_first_failure=True).route == SEARCH


def test_a_rule_search_calls_no_model():
    outcome = c.chain(facts(detector=True), jev(0.0), llm(False), BANDS)
    assert (outcome.first_called, outcome.second_called, outcome.latency_ms) == (False, False, 0)


def test_a_high_jev_score_does_not_call_the_llm():
    outcome = c.chain(facts(), jev(0.9), llm(False), BANDS)
    assert outcome.first_called and not outcome.second_called


def test_only_a_jev_failure_sets_the_llm_alone_flag():
    assert c.chain(facts(needs=False), jev_down(), llm(False), BANDS).llm_alone
    assert not c.chain(facts(needs=False), jev(0.0), llm(False), BANDS).llm_alone


def test_forced_failure_ignores_a_healthy_jev():
    outcome = c.chain(facts(needs=False), jev(0.0), llm(False), BANDS, force_first_failure=True)
    assert (outcome.route, outcome.reason) == (DIRECT, c.R_LLM_ALONE_DIRECT)


def test_equal_cutoffs_leave_no_uncertain_band():
    single = Bands.single(0.3)
    assert c.chain(facts(), jev(0.29), llm(True), single).reason == c.R_LLM_SEARCH
    assert c.chain(facts(), jev(0.30), llm(True), single).reason == c.R_JEV_SEARCH


def test_bands_refuse_inverted_or_out_of_range_cutoffs():
    with pytest.raises(ChainError):
        Bands(search_cutoff=0.2, direct_cutoff=0.5)
    with pytest.raises(ChainError):
        Bands(search_cutoff=1.5, direct_cutoff=0.5)


def test_cost_and_latency_sum_the_calls_made():
    outcome = c.chain(facts(), jev(0.05, cost=0.002, latency=900), llm(True, latency=2500), BANDS)
    assert outcome.latency_ms == 3400
    assert outcome.cost_usd == pytest.approx(0.002)
    assert outcome.calls_without_cost == 1  # the LLM reported no cost


# -- the arms ---------------------------------------------------------------


def run(decider, decisions, source="r"):
    return DeciderRun(decider=decider, decisions=decisions, source=source)


QUESTIONS = [
    facts("need_lo", needs=True),  # Jev scores low: the dangerous one
    facts("need_hi", needs=True),
    facts("need_det", needs=True, detector=True),
    facts("not_lo", needs=False),
    facts("not_hi", needs=False),
    facts("amb", needs=False, tolerated=True, kind="ambiguous"),
]


def jev_run(scores, source="jev"):
    return run("jev", {f.question_id: jev(p) for f, p in zip(QUESTIONS, scores)}, source)


def label_run(searches, source="label"):
    return run("label", {f.question_id: llm(s) for f, s in zip(QUESTIONS, searches)}, source)


def tool_run(searches, source="tool"):
    return run("tool", {f.question_id: llm(s) for f, s in zip(QUESTIONS, searches)}, source)


@pytest.fixture
def runs():
    return {
        "jev": [jev_run([0.05, 0.9, 0.05, 0.05, 0.6, 0.3])],
        "label": [label_run([True, True, False, False, True, True])],
        "tool": [tool_run([False, True, False, False, True, False])],
    }


def result(arm, runs, bands=BANDS, qs=QUESTIONS):
    return c.evaluate_arm(arm, qs, runs, bands)


def test_structural_only_searches_nothing_on_curated_questions(runs):
    r = result(ARM_STRUCTURAL, runs).replicates[0]
    assert r.direct_answers == len(QUESTIONS)
    assert set(r.missed) == {"need_lo", "need_hi", "need_det"}


def test_detector_alone_misses_what_it_is_silent_on(runs):
    r = result(ARM_DETECTOR, runs).replicates[0]
    assert set(r.missed) == {"need_lo", "need_hi"}
    assert r.over_searches == ()


def test_label_arm_unions_the_detector_and_the_label(runs):
    r = result(ARM_LABEL, runs).replicates[0]
    assert r.missed == ()
    assert set(r.over_searches) == {"not_hi"}


def test_tool_arm_misses_what_the_tool_misses(runs):
    r = result(ARM_TOOL, runs).replicates[0]
    assert r.missed == ("need_lo",)


def test_jev_arm_is_jev_alone_and_uncertain_searches(runs):
    r = result(ARM_JEV, runs).replicates[0]
    assert r.missed == ("need_lo",)
    assert set(r.over_searches) == {"not_hi"}
    assert r.reasons[c.R_JEV_UNCERTAIN] == 1  # amb at 0.3


def test_the_chain_rescues_jev_misses_the_llm_catches(runs):
    arm = result(ARM_CHAIN, runs)
    r = arm.replicates[0]
    assert r.missed == ()  # the label searches need_lo
    rescue = arm.rescue["per_replicate"][0]
    assert rescue["jev_misses_before_confirmation"] == ["need_lo"]
    assert rescue["rescued_by_llm"] == ["need_lo"]
    assert rescue["missed_by_both"] == []


def test_missed_by_both_names_the_shared_blind_spot(runs):
    runs["label"] = [label_run([False, True, False, False, True, True])]
    arm = result(ARM_CHAIN, runs)
    assert arm.replicates[0].missed == ("need_lo",)
    assert arm.rescue["per_replicate"][0]["missed_by_both"] == ["need_lo"]


def test_jev_failure_arm_counts_llm_alone_direct_answers(runs):
    runs["label"] = [label_run([False, False, False, False, False, False])]
    arm = result(ARM_JEV_FAILURE, runs)
    r = arm.replicates[0]
    assert arm.arm.simulated_jev_failure
    # the detector still searches need_det; the LLM alone permits the rest
    assert set(r.llm_alone_direct) == {"need_lo", "need_hi", "not_lo", "not_hi", "amb"}
    assert set(r.llm_alone_needed_corpus) == {"need_lo", "need_hi"}
    assert r.reasons[c.R_LLM_ALONE_DIRECT] == 5


def test_control_arm_needs_no_jev_and_never_goes_direct_when_the_label_fails(runs):
    runs["label"] = [run("label", {f.question_id: llm_down() for f in QUESTIONS})]
    r = result(ARM_CONTROL, runs).replicates[0]
    assert r.direct_answers == 0
    assert r.reasons[c.R_FIRST_FAILED] == 5  # all but the detector's


def test_an_arm_without_its_decider_is_skipped_by_name():
    only_jev = {"jev": [jev_run([0.9] * 6)]}
    names = {a.name for a in c.available_arms(only_jev)}
    assert ARM_CHAIN.name not in names and ARM_JEV.name in names
    report = c.build_report(
        question_set={"name": "t"}, facts=QUESTIONS, runs=only_jev, bands=BANDS
    )
    assert ARM_CHAIN.name in report.as_dict()["skipped_arms"]


# -- scoring rules ----------------------------------------------------------


def test_ambiguous_searches_are_neither_a_miss_nor_an_over_search(runs):
    r = result(ARM_LABEL, runs).replicates[0]
    assert "amb" not in r.over_searches and "amb" not in r.missed
    assert r.ambiguous_searched == ("amb",) and r.ambiguous_judged == 1


def test_misses_are_split_into_stable_and_flaky_across_replicates():
    flip = lambda s: jev_run(s)
    runs = {
        "jev": [flip([0.05, 0.9, 0.9, 0.9, 0.9, 0.9]), flip([0.05, 0.05, 0.9, 0.9, 0.9, 0.9])],
        "label": [label_run([False] * 6), label_run([False] * 6)],
    }
    arm = result(ARM_CHAIN, runs)
    misses = arm.as_dict()["missed_searches"]
    assert misses["stable"] == ["need_lo"]
    assert misses["flaky"] == ["need_hi"]


def test_a_replicate_over_five_percent_fallbacks_is_reported_alone():
    many = [jev(0.9) for _ in range(20)]
    many[0] = jev_down()
    many[1] = jev_down()  # 2/20 = 10%
    qs = [facts(f"x{i}", needs=True) for i in range(20)]
    good = run("jev", {f.question_id: jev(0.9) for f in qs})
    bad = run("jev", {f.question_id: d for f, d in zip(qs, many)})
    arm = c.evaluate_arm(ARM_JEV, qs, {"jev": [good, bad]}, BANDS)
    assert arm.reported_alone == (1,)
    assert [r.replicate for r in arm.pooled] == [0]
    assert arm.as_dict()["reported_alone"] == [1]


def test_forced_jev_failure_does_not_gate_pooling(runs):
    runs["jev"] = [run("jev", {f.question_id: jev_down() for f in QUESTIONS})]
    arm = result(ARM_JEV_FAILURE, runs)
    assert arm.reported_alone == ()


def test_no_operating_point_is_chosen(runs):
    report = c.build_report(question_set={"name": "t"}, facts=QUESTIONS, runs=runs, bands=BANDS)
    assert report.as_dict()["operating_point"] is None


# -- calibration, health, the curve -----------------------------------------


def test_brier_score_and_reliability_exclude_ambiguous_questions():
    qs = [facts("a", needs=True), facts("b", needs=False), facts("amb", needs=False, tolerated=True)]
    r = run("jev", {"a": jev(0.8), "b": jev(0.2), "amb": jev(0.5)})
    cal = c.calibration(qs, r)
    assert cal["n"] == 2
    assert cal["brier"] == pytest.approx(((0.2) ** 2 + (0.2) ** 2) / 2, abs=1e-4)
    top = [b for b in cal["reliability"] if b["from"] == 0.8][0]
    assert (top["n"], top["fraction_needing_corpus"]) == (1, 1.0)


def test_decider_health_reports_failure_modes_latency_and_cost():
    r = run(
        "jev",
        {
            "a": jev(0.9, cost=0.002, latency=100),
            "b": jev_down(REASON_RATE_LIMITED),
            "c": jev_down(REASON_MALFORMED_RESPONSE),
            "d": jev(0.1, cost=0.004, latency=300),
        },
    )
    h = c.decider_health(r)
    assert h["fallback_rate"] == 0.5
    assert h["rate_limit_rate"] == 0.25 and h["malformed_rate"] == 0.25
    assert h["cost_usd"]["total"] == pytest.approx(0.006)
    assert h["cost_usd"]["calls_without_reported_cost"] == 2
    assert h["reported_alone"] is True


def test_the_curve_runs_every_threshold_and_sets_none(runs):
    rows = c.jev_curve(ARM_JEV, QUESTIONS, runs)
    assert [r["threshold"] for r in rows] == list(c.THRESHOLDS)
    missed = [r["per_replicate"][0]["missed"] for r in rows]
    over = [r["per_replicate"][0]["over_searches"] for r in rows]
    # a higher cutoff searches less: misses can only rise, over-searches only fall
    assert missed == sorted(missed)
    assert over == sorted(over, reverse=True)


# -- stored runs -------------------------------------------------------------


def test_a_stored_row_round_trips_to_a_decision():
    row = {
        "id": "q1", "route": "direct", "reason": "answered_directly", "anomalies": [],
        "latency_ms": 12, "input_tokens": 5, "output_tokens": None, "answer_present": False,
        "answer_chars": 0, "model": "m", "probability": 0.1, "cost_usd": 0.0003,
    }
    d = c.decision_from_row(row)
    assert (d.probability, d.cost_usd, d.latency_ms) == (0.1, 0.0003, 12)
    assert c.decision_from_row({k: v for k, v in row.items() if k != "cost_usd"}).cost_usd is None


def test_a_result_file_without_model_decisions_is_refused():
    with pytest.raises(ChainError, match="no model decisions"):
        c.run_from_result_file("jev", {"model": None}, "x.json")


def test_a_non_jev_file_is_refused_as_jev():
    data = {"model": {"per_question": [{"id": "q", "route": "direct", "reason": "answered_directly"}]}}
    with pytest.raises(ChainError, match="no probabilities"):
        c.run_from_result_file("jev", data, "x.json")


# -- collecting fresh runs ---------------------------------------------------


class FakeDecider:
    def __init__(self):
        self.seen = []

    def decide(self, question, *, resolved_question=None, prior_reader_questions=()):
        self.seen.append((question, resolved_question, tuple(prior_reader_questions)))
        return llm(False)


class Q:
    def __init__(self, id, question, resolved=None):
        self.id, self.question, self.resolved_question = id, question, resolved


def test_collect_run_sends_the_resolved_question_unless_ablated():
    questions = [Q("a", "what about it?", "what about the dryer?")]
    full, raw = FakeDecider(), FakeDecider()
    run_full = c.collect_run("label", full, questions)
    run_raw = c.collect_run("label", raw, questions, use_resolved=False)
    assert full.seen[0][1] == "what about the dryer?"
    assert raw.seen[0][1] is None
    assert (run_full.input_variant, run_raw.input_variant) == ("raw_and_resolved", "raw_only")


# -- the boundary -----------------------------------------------------------


def test_the_scorer_imports_nothing_that_reaches_the_answer_path():
    source = Path(c.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "apps.ai.composition",
        "apps.ai.orchestrator",
        "apps.ai.models",
        "apps.records",
        "django.db",
        "apps.ai.retrieval",
        "ShadowEvidenceDecision",
    ):
        assert forbidden not in source, forbidden


# -- proposal 12 §4, re-scored from the stored runs -------------------------

RUNS = Path(__file__).resolve().parents[5] / "docs" / "evaluation" / "runs"
STEM = "{}-evidence-proxy-starter.json"
JEV_RUNS = ["20261008-110112", "20261008-110304", "20261008-110450", "20261008-110632"]
LABEL_RUNS = ["20261008-093000", "20261008-093521", "20261008-094042", "20261008-094603"]
TOOL_RUNS = ["20261008-051409", "20261008-053345", "20261008-054102", "20261008-054438"]


def stored(decider, stems):
    out = []
    for stem in stems:
        path = RUNS / STEM.format(stem)
        if not path.exists():
            pytest.skip(f"{path.name} is not in this checkout")
        out.append(c.run_from_result_file(decider, json.loads(path.read_text("utf-8")), path.name))
    return out


@pytest.fixture(scope="module")
def stored_runs():
    runs = {
        "jev": stored("jev", JEV_RUNS),
        "label": stored("label", LABEL_RUNS),
        "tool": stored("tool", TOOL_RUNS),
    }
    path = RUNS / STEM.format(JEV_RUNS[0])
    rows = json.loads(path.read_text("utf-8"))["model"]["per_question"]
    return runs, c.facts_from_run_rows(rows)


def test_rescoring_reproduces_the_band_table(stored_runs):
    runs, fx = stored_runs
    table = c.band_table(fx, runs["jev"])
    got = [(r["needs_corpus"], r["does_not_need_corpus"], r["ambiguous"]) for r in table]
    assert got == [(3, 14, 0), (1, 6, 0), (5, 0, 0), (8, 0, 6), (29, 0, 4), (37, 0, 0)]
    assert [sum(x) for x in got] == [17, 7, 5, 14, 33, 37]
    assert sum(sum(x) for x in got) == 113


def test_rescoring_reproduces_the_rescue_table(stored_runs):
    runs, fx = stored_runs
    rows = {r["cutoff"]: r for r in c.rescue_table(fx, runs["jev"], runs["label"], runs["tool"])}
    shape = lambda r: (r["jev_misses"], r["label_rescues"], r["tool_rescues"], r["detector_rescues"])
    assert shape(rows[0.2]) == (4, 3, 3, 0)
    assert shape(rows[0.3]) == (9, 7, 5, 0)
    assert shape(rows[0.5]) == (17, 13, 11, 1)
    assert rows[0.2]["missed_by_all"] == 1
    assert rows[0.3]["missed_by_all"] == 2
    # Proposal 12 §4.2 prints 4 here. The runs give 3 (q12, q16, q40): 4 is the
    # number the *label* model alone misses, which adds q02. The doc cell is the
    # discrepancy, not this code.
    assert rows[0.5]["missed_by_all"] == 3
    assert rows[0.5]["missed_by_all_ids"] == ["q12", "q16", "q40"]


def test_the_full_chain_runs_over_the_stored_runs(stored_runs):
    runs, fx = stored_runs
    report = c.build_report(
        question_set={"name": "proxy-starter"}, facts=fx, runs=runs, bands=Bands(0.5, 0.2)
    )
    data = report.as_dict()
    assert {a["arm"] for a in data["arms"]} >= {ARM_CHAIN.name, ARM_JEV_FAILURE.name, ARM_CONTROL.name}
    chain_arm = next(a for a in data["arms"] if a["arm"] == ARM_CHAIN.name)
    jev_arm = next(a for a in data["arms"] if a["arm"] == ARM_JEV.name)
    # confirming Jev's direct candidates can only remove misses, never add
    assert len(chain_arm["missed_searches"]["stable"]) <= len(jev_arm["missed_searches"]["stable"])
    assert report.render()
