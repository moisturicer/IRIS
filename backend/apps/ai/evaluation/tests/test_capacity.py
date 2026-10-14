"""IR-550: how a burst of submissions is counted, and when a burst may start.

Pure: no database, no vendor. Every submission stays in the denominator,
whatever happened to it, and only a real, cold, simultaneous burst of at
least one hundred distinct questions can say anything about capacity.
"""

import pytest

from apps.ai.evaluation.capacity import (
    Burst,
    Submission,
    classify_stream,
    plan_burst,
    summarize,
)


def _ok(i, ms):
    return Submission(question=f"q{i}", outcome="generated", submitted_ms=0, final_ms=ms)


def _burst(submissions, **kwargs):
    options = {"provider": "real", "cache": "cold", "simultaneous": True}
    options.update(kwargs)
    return Burst(submissions=tuple(submissions), **options)


def test_every_submission_is_in_the_denominator_whatever_happened_to_it():
    rows = [_ok(i, 2_000) for i in range(95)] + [
        Submission("q95", "rejected", 0, None),
        Submission("q96", "failed", 0, 3_000),
        Submission("q97", "timeout", 0, None),
        Submission("q98", "unfinished", 0, None),
        Submission("q99", "unavailable", 0, 1_000),
    ]
    report = summarize(_burst(rows))
    assert report["submitted"] == 100
    assert report["successes_under_goal"] == 95
    assert report["goal_rate"] == 0.95
    assert report["goal_met"] is True
    assert report["outcomes"] == {"generated": 95, "rejected": 1, "failed": 1,
                                  "timeout": 1, "unfinished": 1, "unavailable": 1}


def test_latency_counts_from_the_original_submission_including_the_queue():
    late = Submission("q0", "generated", submitted_ms=1_000, final_ms=11_500)
    report = summarize(_burst([late] + [_ok(i, 500) for i in range(1, 100)]))
    assert report["successes_under_goal"] == 99


def test_previews_unavailable_and_inconclusive_are_never_successes():
    rows = [Submission(f"q{i}", outcome, 0, 100) for i, outcome in
            enumerate(["preview_only", "unavailable", "inconclusive", "no_results", "partial"])]
    report = summarize(_burst(rows))
    assert report["successes_under_goal"] == 0
    assert report["goal_rate"] == 0.0


def test_a_final_response_past_the_thirty_second_deadline_is_a_deadline_violation():
    rows = [Submission("q0", "generated", 0, 30_001), Submission("q1", "unavailable", 0, 29_000)]
    report = summarize(_burst(rows))
    assert report["deadline_violations"] == ["q0"]
    assert report["successes_under_goal"] == 0


def test_only_a_real_cold_simultaneous_burst_of_a_hundred_distinct_questions_is_a_capacity_claim():
    hundred = [_ok(i, 1_000) for i in range(100)]
    assert summarize(_burst(hundred))["claim"] == "measured_goal_met"
    assert summarize(_burst(hundred, provider="fake"))["claim"] == "control_only"
    assert summarize(_burst(hundred, cache="warm"))["claim"] == "control_only"
    assert summarize(_burst(hundred, simultaneous=False))["claim"] == "unverified"
    assert summarize(_burst(hundred[:99]))["claim"] == "unverified"
    repeated = hundred[:99] + [_ok(0, 1_000)]
    report = summarize(_burst(repeated))
    assert report["distinct"] == 99
    assert report["claim"] == "unverified"


def test_a_real_burst_that_misses_the_goal_says_so():
    rows = [_ok(i, 1_000) for i in range(90)] + [_ok(i, 12_000) for i in range(90, 100)]
    report = summarize(_burst(rows))
    assert report["goal_met"] is False
    assert report["claim"] == "measured_goal_missed"


def test_latency_percentiles_are_over_responses_that_arrived_and_say_how_many():
    rows = [_ok(i, (i + 1) * 100) for i in range(20)] + [Submission("x", "timeout", 0, None)]
    report = summarize(_burst(rows))
    assert report["latency_ms"]["n"] == 20
    assert report["latency_ms"]["p50"] == 1_000
    assert report["latency_ms"]["p95"] == 1_900


def test_an_empty_burst_is_unverified_and_has_no_rate():
    report = summarize(_burst([]))
    assert report["goal_rate"] is None
    assert report["claim"] == "unverified"


SPENDABLE = {"attempts": 360, "input_tokens": 375_000, "output_tokens": 60_000,
             "cost_micros": 11_250_000, "active_ms": 2_700_000}
CHARGED = {"attempts": 10, "input_tokens": 5_000, "output_tokens": 1_000,
           "cost_micros": 250_000, "active_ms": 60_000}


def test_a_burst_that_fits_the_spendable_campaign_may_start():
    per_run = {"attempts": 3, "input_tokens": 3_000, "output_tokens": 500,
               "cost_micros": 100_000, "active_ms": 20_000}
    plan = plan_burst(100, per_run=per_run, spendable=SPENDABLE, charged=CHARGED)
    assert plan["fits"] is True
    assert plan["blocking"] == []


def test_a_burst_that_would_reach_the_reserve_does_not_start_and_capacity_stays_unverified():
    per_run = {"attempts": 4, "input_tokens": 3_000, "output_tokens": 500,
               "cost_micros": 120_000, "active_ms": 20_000}
    plan = plan_burst(100, per_run=per_run, spendable=SPENDABLE, charged=CHARGED)
    assert plan["fits"] is False
    assert set(plan["blocking"]) == {"attempts", "cost_micros"}
    assert plan["claim"] == "unverified"


def test_a_limit_with_no_per_run_cap_cannot_be_planned_and_blocks():
    per_run = {"attempts": 1, "input_tokens": 1, "output_tokens": 1, "cost_micros": 1,
               "active_ms": None}
    plan = plan_burst(100, per_run=per_run, spendable=SPENDABLE, charged=CHARGED)
    assert plan["fits"] is False
    assert plan["blocking"] == ["active_ms"]


@pytest.mark.parametrize("status,events,expected", [
    (503, [], "rejected"),
    (500, [], "failed"),
    (200, [("done", {"mode": "generative", "listing": None})], "generated"),
    (200, [("done", {"mode": "generative",
                     "listing": {"completeness": "inconclusive"}})], "inconclusive"),
    (200, [("done", {"mode": "unavailable"})], "unavailable"),
    (200, [("done", {"mode": "partial"})], "partial"),
    (200, [("done", {"mode": "no_results"})], "no_results"),
    (200, [("capacity_limited", {}), ("done", {"mode": "generative"})], "unavailable"),
    (200, [("run_failed", {"state": "expired", "reason": "deadline_exceeded"})], "timeout"),
    (200, [("run_failed", {"state": "failed", "reason": "unavailable"})], "failed"),
    (200, [("run_cancelled", {"state": "cancelled"})], "cancelled"),
    (200, [("candidates_selected", {})], "preview_only"),
    (200, [("run_queued", {})], "unfinished"),
])
def test_a_stream_is_classified_by_what_the_reader_finally_received(status, events, expected):
    assert classify_stream(status, events) == expected
