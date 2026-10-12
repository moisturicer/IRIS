"""Lane and run scopes around generators (IR-545). No database."""

from contextvars import copy_context

from apps.ai.admission import scope


def test_a_workload_is_current_inside_each_step_and_nowhere_else():
    def inner():
        yield scope.lane_for("default")
        yield scope.lane_for("default")
        return "done"

    steps = scope.stepwise(inner(), lambda: scope.workload("research"))
    assert next(steps) == "research"
    assert scope.lane_for("default") == "default", "nothing leaks between steps"
    assert next(steps) == "research"


def test_the_return_value_survives_yield_from():
    def inner():
        yield 1
        return "the answer"

    def outer():
        result = yield from scope.stepwise(inner(), lambda: scope.workload("research"))
        yield result

    assert list(outer()) == [1, "the answer"]


def test_each_step_may_run_in_a_fresh_context_as_under_asgi():
    def inner():
        yield scope.lane_for("default")
        yield scope.lane_for("default")

    steps = scope.stepwise(inner(), lambda: scope.workload("chat"))
    # Each pull in its own copied context, the way asgiref runs a sync iterator.
    assert copy_context().run(next, steps) == "chat"
    assert copy_context().run(next, steps) == "chat"


def test_close_runs_inside_the_scope():
    closed_in = []

    def inner():
        try:
            yield 1
            yield 2
        finally:
            closed_in.append(scope.lane_for("default"))

    steps = scope.stepwise(inner(), lambda: scope.workload("chat"))
    next(steps)
    steps.close()
    assert closed_in == ["chat"]


def test_an_outer_run_keeps_its_key_and_collects_denials():
    outer = scope.new_run("ask:outer")
    inner = scope.new_run()
    with scope.run(outer):
        with scope.run(inner) as current:
            assert current is outer
            scope.note_denial("lane_busy")
    assert outer.denials == ["lane_busy"] and inner.denials == []


def test_usage_reports_go_to_the_current_attempt_only():
    scope.report_usage(input_tokens=5, output_tokens=5)  # no attempt: ignored
    usage = scope.AttemptUsage()
    with scope.attempt_usage(usage):
        scope.mark_sent()
        scope.report_usage(input_tokens=7, output_tokens=3, model="cheap")
    assert (usage.sent, usage.input_tokens, usage.output_tokens, usage.model) == (True, 7, 3, "cheap")
    assert usage.reported
