"""The circuit breaker (IR-132).

Pure: the clock is injected, so every state transition is testable without
sleeping. A resilience component whose tests take real seconds is a component
whose tests get skipped.
"""

import pytest

from apps.ai.resilience.circuit import CircuitBreaker, CircuitOpen, CircuitState


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _breaker(clock, **kwargs):
    kwargs.setdefault("failure_threshold", 3)
    kwargs.setdefault("reset_after_seconds", 30)
    return CircuitBreaker(clock=clock, **kwargs)


class ClosedTests:
    def test_a_new_breaker_is_closed(self):
        assert _breaker(_Clock()).state is CircuitState.CLOSED

    def test_a_success_passes_through_and_returns_its_value(self):
        assert _breaker(_Clock()).call(lambda: "value") == "value"

    def test_failures_below_the_threshold_leave_it_closed(self):
        breaker = _breaker(_Clock(), failure_threshold=3)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                breaker.call(_raise)
        assert breaker.state is CircuitState.CLOSED

    def test_a_success_resets_the_failure_count(self):
        """Otherwise a healthy dependency trips eventually, just slowly: two
        failures an hour apart are not an outage."""
        breaker = _breaker(_Clock(), failure_threshold=3)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                breaker.call(_raise)
        breaker.call(lambda: "ok")
        with pytest.raises(RuntimeError):
            breaker.call(_raise)
        assert breaker.state is CircuitState.CLOSED


class OpenTests:
    def test_the_threshold_opens_it(self):
        breaker = _breaker(_Clock(), failure_threshold=3)
        for _ in range(3):
            with pytest.raises(RuntimeError):
                breaker.call(_raise)
        assert breaker.state is CircuitState.OPEN

    def test_an_open_breaker_refuses_without_calling_the_dependency(self):
        """The whole point: a failing dependency must stop consuming the
        connection pool and the caller's patience."""
        breaker = _breaker(_Clock(), failure_threshold=1)
        with pytest.raises(RuntimeError):
            breaker.call(_raise)

        calls = []
        with pytest.raises(CircuitOpen):
            breaker.call(lambda: calls.append(1))
        assert calls == [], "the dependency was called while the circuit was open"

    def test_it_stays_open_until_the_reset_window_elapses(self):
        clock = _Clock()
        breaker = _breaker(clock, failure_threshold=1, reset_after_seconds=30)
        with pytest.raises(RuntimeError):
            breaker.call(_raise)

        clock.advance(29)
        with pytest.raises(CircuitOpen):
            breaker.call(lambda: "ok")


class HalfOpenTests:
    def test_after_the_window_one_trial_call_is_allowed(self):
        clock = _Clock()
        breaker = _breaker(clock, failure_threshold=1, reset_after_seconds=30)
        with pytest.raises(RuntimeError):
            breaker.call(_raise)

        clock.advance(31)
        assert breaker.call(lambda: "recovered") == "recovered"
        assert breaker.state is CircuitState.CLOSED

    def test_a_failed_trial_reopens_without_waiting_for_the_threshold_again(self):
        """A dependency that is still down must not get another N attempts
        before the circuit reopens."""
        clock = _Clock()
        breaker = _breaker(clock, failure_threshold=3, reset_after_seconds=30)
        for _ in range(3):
            with pytest.raises(RuntimeError):
                breaker.call(_raise)

        clock.advance(31)
        with pytest.raises(RuntimeError):
            breaker.call(_raise)

        assert breaker.state is CircuitState.OPEN
        with pytest.raises(CircuitOpen):
            breaker.call(lambda: "ok")


def _raise():
    raise RuntimeError("dependency is down")
