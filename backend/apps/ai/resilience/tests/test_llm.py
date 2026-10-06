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
    build_task_llm,
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

    def test_it_proxies_last_model_used_and_last_attempted_model(self):
        """`build_task_llm` (IR-386) puts this breaker *around* a task's
        whole `FallbackLLMProvider` rather than inside it one model at a
        time, so a completion record (IR-387) reading these off whatever
        `CompositionRoot.llm_for` hands out needs them to reach one level
        in -- the same reason `.model` and `.dialect` already do."""
        primary = _ScriptedLLM(model="primary", kind=ErrorKind.RATE_LIMIT, fail_times=None)
        spare = _ScriptedLLM(model="spare")
        inner = FallbackLLMProvider([primary, spare])
        provider = CircuitBreakingLLMProvider(inner, breaker=CircuitBreaker())

        assert provider.generate("s", "u") == "answer from spare"

        assert provider.last_model_used == "spare"
        assert provider.last_attempted_model == "spare"

    def test_last_model_used_is_none_for_a_lone_provider(self):
        """The single-model shape `build_task_llm` returns when a Profile
        has no fallback list -- nothing underneath ever had this
        attribute, so the proxy must not invent a value."""
        provider = CircuitBreakingLLMProvider(_ScriptedLLM(), breaker=CircuitBreaker())

        assert provider.last_model_used is None
        assert provider.last_attempted_model is None


class SwitchableFailureTests:
    def test_rate_limit_network_and_timeout_are_switchable(self):
        for kind in (ErrorKind.RATE_LIMIT, ErrorKind.NETWORK, ErrorKind.TIMEOUT):
            assert is_switchable_failure(LLMUnavailable("x", kind=kind))

    def test_auth_context_overflow_and_unknown_are_not_switchable(self):
        """Auth gives up immediately rather than silently trying a second
        key -- regressing this would reopen the ADR-036 "no silent
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
        working answer (ADR-036's "no silent fall-through" rule)."""
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

    def test_last_attempted_model_names_the_one_that_answered(self):
        """On success, the last attempt and the answering model agree --
        `last_attempted_model` is not a second, diverging source of truth
        for this case, only for the one `last_model_used` cannot cover."""
        primary = _ScriptedLLM(model="primary")
        provider = FallbackLLMProvider([primary])

        provider.generate("s", "u")

        assert provider.last_attempted_model == "primary"
        assert provider.last_attempted_model == provider.last_model_used

    def test_last_attempted_model_survives_total_exhaustion(self):
        """`last_model_used` is set only on success (see the class
        docstring), so it cannot name the model an exhausted list's failure
        belongs to -- IR-387 needs exactly that for a completion record
        built from the exception."""
        primary = _ScriptedLLM(model="primary", kind=ErrorKind.NETWORK, fail_times=None)
        fallback = _ScriptedLLM(model="fallback", kind=ErrorKind.NETWORK, fail_times=None)
        provider = FallbackLLMProvider([primary, fallback])

        with pytest.raises(LLMUnavailable):
            provider.generate("s", "u")

        assert provider.last_attempted_model == "fallback"
        assert provider.last_model_used is None


class BreakerRegistryTests:
    def test_the_same_key_returns_the_same_breaker(self):
        assert breaker_for("groq") is breaker_for("groq")

    def test_different_keys_return_different_breakers(self):
        assert breaker_for("groq") is not breaker_for("openrouter")

    def test_state_survives_a_fresh_composition_root(self):
        """`composition_root()` builds a new `CompositionRoot()` per request
        when nothing is installed -- a breaker built inside `llm_for()` would
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


class BuildTaskLLMTests:
    """`build_task_llm` is what an Inference task's Profile is built with
    (IR-386): one breaker for the whole model list, keyed on the caller's own
    scope rather than on any one model's identity.
    """

    def test_a_single_config_is_wrapped_in_one_breaker(self):
        provider = build_task_llm(
            [LLMProviderConfig(base_url="https://a.test", api_key="k", model="m")],
            breaker_key="task:one",
        )

        assert isinstance(provider, CircuitBreakingLLMProvider)
        # Not double-wrapped: a single model has no fallback list to sit
        # under the breaker, so it is the retrying candidate directly.
        assert isinstance(provider._provider, RetryingLLMProvider)  # noqa: SLF001

    def test_more_than_one_config_puts_the_fallback_under_the_breaker(self):
        provider = build_task_llm(
            [
                LLMProviderConfig(base_url="https://a.test", api_key="k", model="a"),
                LLMProviderConfig(base_url="https://a.test", api_key="k", model="b"),
            ],
            breaker_key="task:two",
        )

        assert isinstance(provider, CircuitBreakingLLMProvider)
        assert isinstance(provider._provider, FallbackLLMProvider)  # noqa: SLF001

    def test_it_refuses_an_empty_config_list(self):
        with pytest.raises(ValueError):
            build_task_llm([], breaker_key="task:empty")

    def test_the_same_breaker_key_is_reused_across_builds(self):
        config = [LLMProviderConfig(base_url="https://a.test", api_key="k", model="m")]

        first = build_task_llm(config, breaker_key="task:shared")
        second = build_task_llm(config, breaker_key="task:shared")

        assert first._breaker is second._breaker  # noqa: SLF001

    def test_two_breaker_keys_stay_independent_even_at_the_same_model(self):
        """The scenario IR-386 names: two tasks configured identically at the
        same vendor and model must not end up sharing a breaker."""
        config = [LLMProviderConfig(base_url="https://a.test", api_key="k", model="m")]

        answer = build_task_llm(config, breaker_key="task:answer")
        summary = build_task_llm(config, breaker_key="task:summary")

        assert answer._breaker is not summary._breaker  # noqa: SLF001


class FallbackExhaustionOpensTheBreakerTests:
    """The breaker built around a fallback list only sees a failure when the
    whole list is exhausted -- not when the first model in it fails and a
    later one answers (IR-386's "not the first model's failure" rule).
    """

    def test_one_models_failure_with_a_working_fallback_does_not_open_it(self):
        primary = _ScriptedLLM(model="primary", kind=ErrorKind.RATE_LIMIT, fail_times=None)
        spare = _ScriptedLLM(model="spare")
        breaker = CircuitBreaker(failure_threshold=1)
        provider = CircuitBreakingLLMProvider(
            FallbackLLMProvider([primary, spare]), breaker=breaker
        )

        # The list answered, via the spare -- one switch-worthy failure
        # inside it is not a failure of the call as a whole.
        assert provider.generate("s", "u") == "answer from spare"
        assert provider.generate("s", "u") == "answer from spare"

    def test_exhausting_every_model_counts_as_one_failure_toward_the_breaker(self):
        primary = _ScriptedLLM(model="primary", kind=ErrorKind.NETWORK, fail_times=None)
        spare = _ScriptedLLM(model="spare", kind=ErrorKind.NETWORK, fail_times=None)
        breaker = CircuitBreaker(failure_threshold=2)
        provider = CircuitBreakingLLMProvider(
            FallbackLLMProvider([primary, spare]), breaker=breaker
        )

        for _ in range(2):
            with pytest.raises(LLMUnavailable):
                provider.generate("s", "u")

        # Two exhausted attempts crossed the threshold -- a third is refused
        # outright, without either model being asked again.
        with pytest.raises(CircuitOpen):
            provider.generate("s", "u")


class OneTasksBreakerLeavesAnotherUntouchedTests:
    """The acceptance criterion in its own terms: tripping one task's breaker
    must not refuse another task's calls, even against the same fake vendor
    behaviour (IR-386)."""

    def test_an_open_breaker_on_one_key_does_not_affect_another(self):
        down = _ScriptedLLM(kind=ErrorKind.NETWORK, fail_times=None)
        healthy = _ScriptedLLM(model="healthy")

        answer_breaker = breaker_for("task:answer")
        answer_breaker._failure_threshold = 1  # noqa: SLF001 -- test-only
        summary_breaker = breaker_for("task:summary")

        answer_provider = CircuitBreakingLLMProvider(down, breaker=answer_breaker)
        summary_provider = CircuitBreakingLLMProvider(healthy, breaker=summary_breaker)

        with pytest.raises(LLMUnavailable):
            answer_provider.generate("s", "u")
        # `answer`'s breaker is now open.
        with pytest.raises(CircuitOpen):
            answer_provider.generate("s", "u")

        # `summary`, sharing nothing but the process, is unaffected.
        assert summary_provider.generate("s", "u") == "answer from healthy"

    def test_reset_clears_every_tasks_breaker_not_just_one(self):
        """`reset_llm_breakers` is a blanket clear of the whole registry
        (see its own docstring) -- it needs no per-task awareness to already
        cover task-keyed breakers, but a regression that scoped it to one
        namespace would leak state between tests, so this pins the promise
        down explicitly."""
        for key in ("task:answer", "task:summary"):
            breaker = breaker_for(key)
            breaker._failure_threshold = 1  # noqa: SLF001
            provider = CircuitBreakingLLMProvider(
                _ScriptedLLM(kind=ErrorKind.NETWORK, fail_times=None), breaker=breaker
            )
            with pytest.raises(LLMUnavailable):
                provider.generate("s", "u")
            with pytest.raises(CircuitOpen):
                provider.generate("s", "u")

        reset_llm_breakers()

        for key in ("task:answer", "task:summary"):
            assert breaker_for(key).state.value == "closed"
