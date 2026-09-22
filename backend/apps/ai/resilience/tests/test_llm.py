"""Resilience decorators around `LLMProvider` (IR-321).

No vendor account anywhere here: every provider is a small fake that raises a
classified `LLMUnavailable`, the same exception the real adapter raises
(IR-320), so these tests exercise exactly what a caller catches.
"""

from __future__ import annotations

import pytest

from apps.ai.providers.errors import ErrorKind
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.providers.ports import LLMProvider
from apps.ai.resilience.circuit import CircuitBreaker, CircuitOpen
from apps.ai.resilience.llm import (
    CircuitBreakingLLMProvider,
    FallbackLLMProvider,
    LLMProviderConfig,
    RetryingLLMProvider,
    breaker_for,
    build_resilient_llm,
    is_switchable_failure,
    reset_llm_breakers,
)


class _Sleeper:
    def __init__(self):
        self.delays = []

    def __call__(self, seconds):
        self.delays.append(seconds)


class _ScriptedLLM(LLMProvider):
    """Fails with a given kind for its first ``fail_times`` calls, then
    answers -- or never answers, when ``fail_times`` is ``None``."""

    def __init__(self, model="scripted-model", kind=ErrorKind.NETWORK, fail_times=0):
        self.model = model
        self._kind = kind
        self._remaining = fail_times
        self.calls = 0

    def generate(self, system, user):
        self.calls += 1
        if self._remaining is None or self._remaining > 0:
            if self._remaining is not None:
                self._remaining -= 1
            raise LLMUnavailable(f"{self.model} failed", kind=self._kind)
        return f"answer from {self.model}"


@pytest.fixture(autouse=True)
def _clean_breaker_registry():
    reset_llm_breakers()
    yield
    reset_llm_breakers()


class RetryingLLMProviderTests:
    def test_a_network_failure_is_retried_and_can_succeed(self):
        llm = _ScriptedLLM(kind=ErrorKind.NETWORK, fail_times=1)
        provider = RetryingLLMProvider(llm, attempts=2, sleep=_Sleeper())

        assert provider.generate("s", "u") == "answer from scripted-model"
        assert llm.calls == 2

    def test_a_timeout_failure_is_retried(self):
        llm = _ScriptedLLM(kind=ErrorKind.TIMEOUT, fail_times=1)
        provider = RetryingLLMProvider(llm, attempts=2, sleep=_Sleeper())

        assert provider.generate("s", "u") == "answer from scripted-model"

    def test_it_is_bounded_to_the_interactive_attempt_count_by_default(self):
        """Not `retry_with_backoff`'s own default of 3 -- a person is waiting
        on this call (IR-321's "one retry bound, not 3")."""
        llm = _ScriptedLLM(kind=ErrorKind.NETWORK, fail_times=None)
        provider = RetryingLLMProvider(llm, sleep=_Sleeper())

        with pytest.raises(LLMUnavailable):
            provider.generate("s", "u")
        assert llm.calls == 2

    @pytest.mark.parametrize(
        "kind",
        [ErrorKind.AUTH, ErrorKind.RATE_LIMIT, ErrorKind.CONTEXT_OVERFLOW, ErrorKind.UNKNOWN],
    )
    def test_kinds_other_than_network_and_timeout_are_never_retried(self, kind):
        """A bad key, an over-long prompt, a spent rate limit and an
        unclassified failure all fail the same way again -- asking twice
        costs latency for nothing, and for `rate_limit` makes it worse."""
        llm = _ScriptedLLM(kind=kind, fail_times=None)
        provider = RetryingLLMProvider(llm, attempts=3, sleep=_Sleeper())

        with pytest.raises(LLMUnavailable):
            provider.generate("s", "u")
        assert llm.calls == 1

    def test_the_model_property_proxies_the_wrapped_provider(self):
        llm = _ScriptedLLM(model="groq-model")
        assert RetryingLLMProvider(llm).model == "groq-model"


class CircuitBreakingLLMProviderTests:
    def test_a_healthy_provider_answers_normally(self):
        llm = _ScriptedLLM()
        provider = CircuitBreakingLLMProvider(llm, breaker=CircuitBreaker())
        assert provider.generate("s", "u") == "answer from scripted-model"

    def test_it_opens_after_the_failure_threshold_and_refuses_further_calls(self):
        llm = _ScriptedLLM(kind=ErrorKind.NETWORK, fail_times=None)
        breaker = CircuitBreaker(failure_threshold=2)
        provider = CircuitBreakingLLMProvider(llm, breaker=breaker)

        for _ in range(2):
            with pytest.raises(LLMUnavailable):
                provider.generate("s", "u")

        with pytest.raises(CircuitOpen):
            provider.generate("s", "u")
        # The circuit refused the third call outright -- the provider itself
        # was never asked.
        assert llm.calls == 2


class SwitchableFailureTests:
    def test_rate_limit_network_and_timeout_are_switchable(self):
        for kind in (ErrorKind.RATE_LIMIT, ErrorKind.NETWORK, ErrorKind.TIMEOUT):
            assert is_switchable_failure(LLMUnavailable("x", kind=kind))

    def test_auth_context_overflow_and_unknown_are_not_switchable(self):
        """Auth gives up immediately rather than silently trying a second
        key -- regressing this would reopen the ADR-021 "no silent
        fall-through" failure mode. Context overflow and an unclassified
        failure both fail identically against a second provider, so
        switching would hide a real error behind another attempt."""
        for kind in (ErrorKind.AUTH, ErrorKind.CONTEXT_OVERFLOW, ErrorKind.UNKNOWN):
            assert not is_switchable_failure(LLMUnavailable("x", kind=kind))

    def test_an_open_circuit_is_switchable_with_no_kind_to_read(self):
        assert is_switchable_failure(CircuitOpen("open"))


class FallbackLLMProviderTests:
    def test_it_answers_from_the_primary_when_healthy(self):
        primary = _ScriptedLLM(model="primary")
        fallback = _ScriptedLLM(model="fallback")
        provider = FallbackLLMProvider([primary, fallback])

        assert provider.generate("s", "u") == "answer from primary"
        assert provider.last_model_used == "primary"
        assert fallback.calls == 0

    def test_a_rate_limit_switches_to_the_next_provider(self):
        primary = _ScriptedLLM(model="primary", kind=ErrorKind.RATE_LIMIT, fail_times=None)
        fallback = _ScriptedLLM(model="fallback")
        provider = FallbackLLMProvider([primary, fallback])

        assert provider.generate("s", "u") == "answer from fallback"
        assert provider.last_model_used == "fallback"

    def test_an_auth_failure_gives_up_without_trying_the_next_provider(self):
        """Never silently retries a bad key against a second account --
        that would hide a real misconfiguration behind an apparently
        working answer (ADR-021's "no silent fall-through" rule)."""
        primary = _ScriptedLLM(model="primary", kind=ErrorKind.AUTH, fail_times=None)
        fallback = _ScriptedLLM(model="fallback")
        provider = FallbackLLMProvider([primary, fallback])

        with pytest.raises(LLMUnavailable):
            provider.generate("s", "u")
        assert fallback.calls == 0

    def test_every_provider_failing_reraises_the_last_failure(self):
        primary = _ScriptedLLM(model="primary", kind=ErrorKind.NETWORK, fail_times=None)
        fallback = _ScriptedLLM(model="fallback", kind=ErrorKind.NETWORK, fail_times=None)
        provider = FallbackLLMProvider([primary, fallback])

        with pytest.raises(LLMUnavailable, match="fallback failed"):
            provider.generate("s", "u")

    def test_it_needs_at_least_one_provider(self):
        with pytest.raises(ValueError):
            FallbackLLMProvider([])


class BreakerRegistryTests:
    def test_the_same_key_returns_the_same_breaker(self):
        assert breaker_for("groq") is breaker_for("groq")

    def test_different_keys_return_different_breakers(self):
        assert breaker_for("groq") is not breaker_for("openrouter")

    def test_state_survives_a_fresh_composition_root(self):
        """`composition_root()` builds a new `CompositionRoot()` per request
        when nothing is installed -- a breaker built inside `llm()` would
        never accumulate a failure past that one request. The registry is
        what makes the failure count below actually add up."""
        llm = _ScriptedLLM(kind=ErrorKind.NETWORK, fail_times=None)
        breaker = breaker_for("shared-key")
        breaker._failure_threshold = 2  # noqa: SLF001 -- test-only introspection

        for _ in range(2):
            provider = CircuitBreakingLLMProvider(llm, breaker=breaker_for("shared-key"))
            with pytest.raises(LLMUnavailable):
                provider.generate("s", "u")

        provider = CircuitBreakingLLMProvider(llm, breaker=breaker_for("shared-key"))
        with pytest.raises(CircuitOpen):
            provider.generate("s", "u")


class BuildResilientLLMTests:
    def test_a_single_config_is_wrapped_but_not_fallback_composed(self):
        provider = build_resilient_llm(
            [LLMProviderConfig(base_url="https://a.test", api_key="k", model="m")]
        )
        assert isinstance(provider, CircuitBreakingLLMProvider)

    def test_more_than_one_config_composes_a_fallback(self):
        provider = build_resilient_llm(
            [
                LLMProviderConfig(base_url="https://a.test", api_key="k1", model="a"),
                LLMProviderConfig(base_url="https://b.test", api_key="k2", model="b"),
            ]
        )
        assert isinstance(provider, FallbackLLMProvider)

    def test_it_refuses_an_empty_config_list(self):
        with pytest.raises(ValueError):
            build_resilient_llm([])
