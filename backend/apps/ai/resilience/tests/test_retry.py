"""Bounded retry (IR-132). `sleep` is injected, so the schedule is asserted
rather than lived through."""

import pytest

from apps.ai.providers.errors import ErrorKind
from apps.ai.resilience.rate_limit import RateLimited
from apps.ai.resilience.retry import retry_with_backoff


class _Sleeper:
    def __init__(self):
        self.delays = []

    def __call__(self, seconds):
        self.delays.append(seconds)


class RetryTests:
    def test_a_success_is_returned_without_sleeping(self):
        sleeper = _Sleeper()
        assert retry_with_backoff(lambda: "ok", sleep=sleeper) == "ok"
        assert sleeper.delays == []

    def test_a_transient_failure_is_retried_and_can_succeed(self):
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("transient")
            return "recovered"

        assert retry_with_backoff(flaky, attempts=3, sleep=_Sleeper()) == "recovered"
        assert len(calls) == 3

    def test_delays_double(self):
        sleeper = _Sleeper()
        with pytest.raises(RuntimeError):
            retry_with_backoff(_raise, attempts=4, base_delay=0.5, sleep=sleeper)
        assert sleeper.delays == [0.5, 1.0, 2.0]

    def test_it_gives_up_after_the_attempt_budget(self):
        calls = []

        def always_fails():
            calls.append(1)
            raise RuntimeError("down")

        with pytest.raises(RuntimeError):
            retry_with_backoff(always_fails, attempts=3, sleep=_Sleeper())
        assert len(calls) == 3

    def test_the_original_exception_is_reraised_not_wrapped(self):
        """The caller's circuit breaker counts the real exception; wrapping it
        would hide what failed from the thing deciding whether to trip."""
        with pytest.raises(RuntimeError, match="down"):
            retry_with_backoff(_raise, attempts=2, sleep=_Sleeper())

    def test_a_rate_limit_is_never_retried(self):
        """Asking again makes the outage worse, and the answer will be the
        same until the window turns over."""
        calls = []

        def limited():
            calls.append(1)
            raise RateLimited("spent")

        with pytest.raises(RateLimited):
            retry_with_backoff(
                limited, attempts=5, give_up_on=(RateLimited,), sleep=_Sleeper()
            )
        assert len(calls) == 1

    def test_zero_attempts_is_rejected_rather_than_silently_doing_nothing(self):
        with pytest.raises(ValueError):
            retry_with_backoff(lambda: "ok", attempts=0)

    def test_a_classified_kind_can_be_given_up_on_without_naming_the_exception_type(self):
        """The vendor boundary raises one exception type for many failures
        (IR-320) -- ``give_up_on_kind`` lets a caller give up on the ones that
        won't get better without importing that type here, which would make
        this module depend on which adapter sits behind the port."""
        calls = []

        def rate_limited():
            calls.append(1)
            raise _Classified("spent", ErrorKind.RATE_LIMIT)

        with pytest.raises(_Classified):
            retry_with_backoff(
                rate_limited,
                attempts=5,
                give_up_on_kind=(ErrorKind.RATE_LIMIT,),
                sleep=_Sleeper(),
            )
        assert len(calls) == 1

    def test_an_unlisted_kind_is_still_retried(self):
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 2:
                raise _Classified("dropped", ErrorKind.NETWORK)
            return "recovered"

        result = retry_with_backoff(
            flaky,
            attempts=3,
            give_up_on_kind=(ErrorKind.RATE_LIMIT,),
            sleep=_Sleeper(),
        )
        assert result == "recovered"
        assert len(calls) == 2

    def test_an_exception_with_no_kind_never_matches_give_up_on_kind(self):
        """A plain exception -- nothing a classified adapter boundary raised
        -- has no ``.kind`` to read, so this is a no-op for it rather than an
        error."""
        calls = []

        def always_fails():
            calls.append(1)
            raise RuntimeError("down")

        with pytest.raises(RuntimeError):
            retry_with_backoff(
                always_fails,
                attempts=3,
                give_up_on_kind=(ErrorKind.RATE_LIMIT,),
                sleep=_Sleeper(),
            )
        assert len(calls) == 3


class _Classified(RuntimeError):
    """A stand-in for the shape `LLMUnavailable`/`VoyageError` share: one
    exception type carrying a `.kind`."""

    def __init__(self, message, kind):
        super().__init__(message)
        self.kind = kind


def _raise():
    raise RuntimeError("down")
