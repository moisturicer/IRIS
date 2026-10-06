"""The tool-calling port through the resilience decorators (IR-465).

The reason the port is abstract is that a defaulted method would be bypassed by
every decorator, and the feature would never run in a real configuration. These
assert each decorator actually does its job for `complete_with_tools`, not only
that the method exists: retry, circuit and model fallback behave exactly as
they do for `generate`.
"""

from __future__ import annotations

import pytest

from apps.ai.providers.errors import ErrorKind
from apps.ai.providers.fakes import ScriptedLLM, ScriptedToolCallingLLM
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.providers.tool_calling import ToolCallingLLM, ToolCompletion, ToolDefinition
from apps.ai.resilience.circuit import CircuitBreaker, CircuitOpen
from apps.ai.resilience.llm import (
    CircuitBreakingLLMProvider,
    FallbackLLMProvider,
    RetryingLLMProvider,
    reset_llm_breakers,
)

TOOLS = (ToolDefinition(name="search_corpus", description="Search."),)
CALL = ScriptedToolCallingLLM.calling


class _Provider(ScriptedToolCallingLLM):
    def __init__(self, model, script):
        super().__init__(script)
        self.model = model


def _lost(kind):
    return LLMUnavailable("lost", kind=kind)


@pytest.fixture(autouse=True)
def _clean_breakers():
    reset_llm_breakers()
    yield
    reset_llm_breakers()


class RetryingTests:
    def test_a_timeout_is_retried_and_the_second_try_is_returned(self):
        inner = _Provider("m", [_lost(ErrorKind.TIMEOUT), CALL()])
        retrying = RetryingLLMProvider(inner, attempts=2, sleep=lambda s: None)

        completion = retrying.complete_with_tools("s", "u", TOOLS)

        assert completion.tool_calls[0].name == "search_corpus"
        assert len(inner.tool_requests) == 2

    @pytest.mark.parametrize("kind", [ErrorKind.RATE_LIMIT, ErrorKind.AUTH])
    def test_a_failure_retrying_cannot_fix_is_not_retried(self, kind):
        inner = _Provider("m", [_lost(kind), CALL()])
        retrying = RetryingLLMProvider(inner, attempts=3, sleep=lambda s: None)

        with pytest.raises(LLMUnavailable):
            retrying.complete_with_tools("s", "u", TOOLS)
        assert len(inner.tool_requests) == 1

    def test_the_timeout_and_tools_are_forwarded(self):
        inner = _Provider("m", [CALL()])
        RetryingLLMProvider(inner).complete_with_tools(
            "sys", "usr", TOOLS, timeout_seconds=4.0
        )
        (request,) = inner.tool_requests
        assert (request.system, request.user) == ("sys", "usr")
        assert request.tools == TOOLS and request.timeout_seconds == 4.0


class CircuitBreakingTests:
    def test_failures_open_the_circuit_and_later_calls_are_refused(self):
        inner = _Provider("m", [_lost(ErrorKind.NETWORK)] * 2 + [CALL()])
        breaker = CircuitBreaker(failure_threshold=2)
        guarded = CircuitBreakingLLMProvider(inner, breaker=breaker)

        for _ in range(2):
            with pytest.raises(LLMUnavailable):
                guarded.complete_with_tools("s", "u", TOOLS)
        with pytest.raises(CircuitOpen):
            guarded.complete_with_tools("s", "u", TOOLS)

        assert len(inner.tool_requests) == 2

    def test_a_tool_call_and_a_text_call_share_one_breaker(self):
        """One breaker per task: a vendor down for answers is down for the
        decision, and the other way round."""
        inner = _Provider("m", [_lost(ErrorKind.NETWORK)])
        inner.generate = lambda s, u: (_ for _ in ()).throw(_lost(ErrorKind.NETWORK))
        guarded = CircuitBreakingLLMProvider(inner, breaker=CircuitBreaker(failure_threshold=2))

        with pytest.raises(LLMUnavailable):
            guarded.generate("s", "u")
        with pytest.raises(LLMUnavailable):
            guarded.complete_with_tools("s", "u", TOOLS)
        with pytest.raises(CircuitOpen):
            guarded.complete_with_tools("s", "u", TOOLS)

    def test_a_success_is_returned_untouched(self):
        completion = ScriptedToolCallingLLM.answering("hi")
        guarded = CircuitBreakingLLMProvider(
            _Provider("m", [completion]), breaker=CircuitBreaker()
        )
        assert guarded.complete_with_tools("s", "u", TOOLS) is completion


class FallbackTests:
    def test_a_rate_limit_moves_to_the_next_model_and_records_who_answered(self):
        first = _Provider("first", [_lost(ErrorKind.RATE_LIMIT)])
        second = _Provider("second", [CALL()])
        fallback = FallbackLLMProvider([first, second])

        completion = fallback.complete_with_tools("s", "u", TOOLS)

        assert completion.tool_calls
        assert fallback.last_model_used == "second"
        assert fallback.last_attempted_model == "second"
        assert len(first.tool_requests) == len(second.tool_requests) == 1

    def test_a_failure_another_model_cannot_fix_stops_the_walk(self):
        first = _Provider("first", [_lost(ErrorKind.AUTH)])
        second = _Provider("second", [CALL()])

        with pytest.raises(LLMUnavailable):
            FallbackLLMProvider([first, second]).complete_with_tools("s", "u", TOOLS)
        assert second.tool_requests == []

    def test_exhausting_the_list_raises_the_last_failure(self):
        fallback = FallbackLLMProvider(
            [
                _Provider("a", [_lost(ErrorKind.RATE_LIMIT)]),
                _Provider("b", [_lost(ErrorKind.TIMEOUT)]),
            ]
        )
        with pytest.raises(LLMUnavailable) as caught:
            fallback.complete_with_tools("s", "u", TOOLS)
        assert caught.value.kind is ErrorKind.TIMEOUT
        assert fallback.last_attempted_model == "b"


class NothingFallsBackToTextTests:
    """A decorator over a provider that cannot carry a tool call refuses, so a
    routing decision never quietly becomes `generate`."""

    @pytest.mark.parametrize(
        "decorator",
        [
            lambda inner: RetryingLLMProvider(inner),
            lambda inner: CircuitBreakingLLMProvider(inner, breaker=CircuitBreaker()),
            lambda inner: FallbackLLMProvider([inner]),
        ],
        ids=["retrying", "circuit-breaking", "fallback"],
    )
    def test_a_text_only_provider_is_refused_loudly(self, decorator):
        text_only = ScriptedLLM()
        assert not isinstance(text_only, ToolCallingLLM)

        with pytest.raises(TypeError, match="does not implement ToolCallingLLM"):
            decorator(text_only).complete_with_tools("s", "u", TOOLS)
        assert text_only.calls == []


def test_the_decorators_are_tool_calling_providers():
    for decorator in (RetryingLLMProvider, CircuitBreakingLLMProvider, FallbackLLMProvider):
        assert issubclass(decorator, ToolCallingLLM)
        assert "complete_with_tools" in vars(decorator), (
            f"{decorator.__name__} must implement the method itself; inheriting "
            "one is how a decorator ends up bypassing it"
        )


def test_the_completion_type_is_what_comes_through():
    assert isinstance(
        RetryingLLMProvider(_Provider("m", [CALL()])).complete_with_tools("s", "u", TOOLS),
        ToolCompletion,
    )
