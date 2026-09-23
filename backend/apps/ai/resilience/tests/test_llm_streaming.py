"""Streaming through the resilience decorators (IR-334).

IR-325 gave `LLMProvider` a `stream()` whose default buffers `generate()` into
one delta, and IR-321 wrapped every configured provider in decorators that
implemented only `generate()`. The two together meant that against the real
model, `/ai/ask/stream/` narrated retrieval incrementally and then delivered
the whole answer in a single `text_delta` — `ChatStreamView` recorded it as a
known limitation. These tests are what keeps that from coming back.

The rule they pin down: **retry and failover happen only before the first
delta.** After one, the reader has already seen text, and starting over would
either repeat it or write a second answer underneath the first.
"""

from __future__ import annotations

import pytest

from apps.ai.providers.errors import ErrorKind
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.providers.ports import LLMProvider, StreamDelta
from apps.ai.resilience.circuit import CircuitBreaker, CircuitOpen
from apps.ai.resilience.llm import (
    CircuitBreakingLLMProvider,
    FallbackLLMProvider,
    RetryingLLMProvider,
    reset_llm_breakers,
)


class _Sleeper:
    def __init__(self):
        self.delays = []

    def __call__(self, seconds):
        self.delays.append(seconds)


class _StreamingLLM(LLMProvider):
    """Yields `parts` as separate deltas.

    `fail_before_first` fails on opening, which is where a bad key, an
    exhausted quota or a refused connection surfaces. `fail_after_first`
    fails once text is already out — the case nothing may retry.
    """

    def __init__(
        self,
        model="streaming-model",
        parts=("Rainfall ", "gauges ", "feed it [1]."),
        kind=ErrorKind.NETWORK,
        fail_before_first=0,
        fail_after_first=False,
    ):
        self.model = model
        self._parts = tuple(parts)
        self._kind = kind
        self._remaining = fail_before_first
        self._fail_after_first = fail_after_first
        self.calls = 0

    def generate(self, system, user):
        raise AssertionError("the streaming path must not fall back to generate()")

    def stream(self, system, user):
        self.calls += 1
        if self._remaining is None or self._remaining > 0:
            if self._remaining is not None:
                self._remaining -= 1
            raise LLMUnavailable(f"{self.model} failed", kind=self._kind)
        for index, part in enumerate(self._parts):
            yield StreamDelta(text=part)
            if self._fail_after_first and index == 0:
                raise LLMUnavailable("dropped mid-answer", kind=ErrorKind.NETWORK)


def texts(provider) -> list[str]:
    return [delta.text for delta in provider.stream("s", "u")]


@pytest.fixture(autouse=True)
def _clean_breaker_registry():
    reset_llm_breakers()
    yield
    reset_llm_breakers()


class DeltasSurviveTheDecoratorsTests:
    """The regression that started this: three deltas in, one delta out."""

    def test_retry_passes_every_delta_through_separately(self):
        llm = _StreamingLLM()

        assert texts(RetryingLLMProvider(llm, sleep=_Sleeper())) == [
            "Rainfall ", "gauges ", "feed it [1]."
        ]

    def test_the_circuit_breaker_passes_every_delta_through_separately(self):
        llm = _StreamingLLM()

        assert texts(CircuitBreakingLLMProvider(llm)) == [
            "Rainfall ", "gauges ", "feed it [1]."
        ]

    def test_the_fallback_provider_passes_every_delta_through_separately(self):
        llm = _StreamingLLM()

        assert texts(FallbackLLMProvider([llm])) == [
            "Rainfall ", "gauges ", "feed it [1]."
        ]

    def test_the_whole_configured_stack_keeps_them_separate(self):
        """Retry inside circuit-breaking inside fallback — the shape
        `build_resilient_llm` composes."""
        llm = _StreamingLLM()
        stack = FallbackLLMProvider(
            [CircuitBreakingLLMProvider(RetryingLLMProvider(llm, sleep=_Sleeper()))]
        )

        assert len(texts(stack)) == 3

    def test_an_empty_stream_is_empty_rather_than_one_blank_delta(self):
        assert texts(RetryingLLMProvider(_StreamingLLM(parts=()), sleep=_Sleeper())) == []


class RetryStopsAtTheFirstDeltaTests:
    def test_a_transient_failure_before_any_delta_is_retried(self):
        llm = _StreamingLLM(fail_before_first=1)
        provider = RetryingLLMProvider(llm, attempts=2, sleep=_Sleeper())

        assert texts(provider) == ["Rainfall ", "gauges ", "feed it [1]."]
        assert llm.calls == 2

    def test_a_failure_after_a_delta_is_not_retried(self):
        """Retrying here would put a second answer underneath the words the
        reader is already looking at. The partial is `answer_stream`'s to
        persist (IR-328), not this decorator's to paper over."""
        llm = _StreamingLLM(fail_after_first=True)
        provider = RetryingLLMProvider(llm, attempts=2, sleep=_Sleeper())

        produced = []
        with pytest.raises(LLMUnavailable):
            for delta in provider.stream("s", "u"):
                produced.append(delta.text)

        assert produced == ["Rainfall "]
        assert llm.calls == 1

    @pytest.mark.parametrize(
        "kind",
        [ErrorKind.AUTH, ErrorKind.RATE_LIMIT, ErrorKind.CONTEXT_OVERFLOW,
         ErrorKind.UNKNOWN],
    )
    def test_kinds_that_never_retry_still_never_retry_while_streaming(self, kind):
        llm = _StreamingLLM(kind=kind, fail_before_first=1)
        provider = RetryingLLMProvider(llm, attempts=2, sleep=_Sleeper())

        with pytest.raises(LLMUnavailable):
            texts(provider)
        assert llm.calls == 1


class CircuitBreakerTests:
    def test_an_open_circuit_refuses_to_open_a_stream_at_all(self):
        breaker = CircuitBreaker(failure_threshold=1)
        llm = _StreamingLLM(fail_before_first=None)
        provider = CircuitBreakingLLMProvider(llm, breaker=breaker)

        with pytest.raises(LLMUnavailable):
            texts(provider)
        with pytest.raises(CircuitOpen):
            texts(provider)
        assert llm.calls == 1

    def test_a_failure_to_open_counts_against_the_breaker(self):
        breaker = CircuitBreaker(failure_threshold=2)
        provider = CircuitBreakingLLMProvider(
            _StreamingLLM(fail_before_first=None), breaker=breaker
        )

        for _ in range(2):
            with pytest.raises(LLMUnavailable):
                texts(provider)

        with pytest.raises(CircuitOpen):
            texts(provider)

    def test_a_stream_that_started_does_not_count_against_the_breaker(self):
        """A vendor that produced a first token is not the down vendor this
        breaker exists to stop us calling."""
        breaker = CircuitBreaker(failure_threshold=1)
        provider = CircuitBreakingLLMProvider(
            _StreamingLLM(fail_after_first=True), breaker=breaker
        )

        with pytest.raises(LLMUnavailable):
            texts(provider)

        # Still closed: the next call is attempted rather than refused.
        assert texts(CircuitBreakingLLMProvider(_StreamingLLM(), breaker=breaker))


class FailoverStopsAtTheFirstDeltaTests:
    def test_a_switchable_failure_before_any_delta_tries_the_next_provider(self):
        down = _StreamingLLM(model="primary", fail_before_first=None,
                             kind=ErrorKind.RATE_LIMIT)
        up = _StreamingLLM(model="secondary", parts=("from the spare.",))
        provider = FallbackLLMProvider([down, up])

        assert texts(provider) == ["from the spare."]
        assert provider.last_model_used == "secondary"

    def test_a_failure_after_a_delta_does_not_fail_over(self):
        primary = _StreamingLLM(model="primary", fail_after_first=True)
        spare = _StreamingLLM(model="secondary", parts=("a whole second answer.",))
        provider = FallbackLLMProvider([primary, spare])

        produced = []
        with pytest.raises(LLMUnavailable):
            for delta in provider.stream("s", "u"):
                produced.append(delta.text)

        assert produced == ["Rainfall "]
        assert spare.calls == 0

    def test_a_non_switchable_failure_is_raised_rather_than_switched_on(self):
        """ADR-021's no-silent-fall-through rule: a bad key is still a bad key
        on the next provider, and switching would hide the misconfiguration."""
        down = _StreamingLLM(model="primary", fail_before_first=None,
                             kind=ErrorKind.AUTH)
        spare = _StreamingLLM(model="secondary")
        provider = FallbackLLMProvider([down, spare])

        with pytest.raises(LLMUnavailable):
            texts(provider)
        assert spare.calls == 0
