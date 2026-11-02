"""IR-607: the private stage classifier on run rows the controller writes. Pure."""

from apps.ai.evaluation.replay import research_stage


def run(status, stop_reason="ready", *steps):
    return [{"id": "r", "status": status, "stop_reason": stop_reason,
             "steps": [{"kind": k, "tool": t, "status": s} for k, t, s in steps]}]


PLAN = ("plan", "", "ok")


def test_a_turn_that_recovered_from_a_tool_outage_and_answered_is_answered():
    rows = run("generated", "ready", PLAN, ("tool", "search_research", "unavailable"),
               ("tool", "search_research", "ok"), ("answer", "", "generated"))
    assert research_stage(rows)["stage"] == "answered"


def test_an_answer_model_outage_is_a_provider_failure():
    rows = run("unavailable", "ready", PLAN, ("tool", "search_research", "ok"),
               ("answer", "", "unavailable"))
    assert research_stage(rows)["stage"] == "provider_failure"
    planner = run("unavailable", "planner_unavailable", ("plan", "", "unavailable"))
    assert research_stage(planner)["stage"] == "provider_failure"


def test_a_budget_or_cancelled_stop_is_not_a_provider_failure():
    for reason in ("cancelled", "max_tool_calls", "answer_reserve"):
        assert research_stage(run("unavailable", reason, PLAN))["stage"] == "other"


def test_a_search_outage_ending_in_no_sources_is_not_an_empty_search():
    rows = run("no_sources", "ready", PLAN, ("tool", "search_research", "unavailable"),
               ("answer", "", "no_sources"))
    assert research_stage(rows)["stage"] == "provider_failure"


def test_only_paper_finding_tools_count_as_candidates():
    rows = run("no_sources", "ready", PLAN, ("tool", "aggregate_records", "ok"),
               ("answer", "", "no_sources"))
    assert research_stage(rows) | {"research_runs": None} == {
        "stage": "no_candidates", "candidate_steps": 0, "research_runs": None}
