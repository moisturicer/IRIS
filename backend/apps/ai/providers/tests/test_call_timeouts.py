"""Every model call carries an explicit timeout (IR-511, ADR-038 §5).

The default bounds a call when no run is in progress; a run's deadline
shortens it to the time left. No vendor account and no network.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import openai
import pytest

from apps.ai.providers.deadline import model_call_deadline, time_left
from apps.ai.providers.errors import ErrorKind
from apps.ai.providers.openai_compatible import LLMUnavailable, OpenAICompatibleAdapter
from apps.ai.providers.tool_calling import ToolDefinition, UserMessage
from apps.ai.resilience.circuit import CircuitBreaker, CircuitOpen
from apps.ai.resilience.llm import CircuitBreakingLLMProvider, RetryingLLMProvider

pytestmark = pytest.mark.django_required

SEARCH = ToolDefinition(name="search_corpus", description="Search.")


def _timeout_error():
    return openai.APITimeoutError(request=httpx.Request("POST", "https://x.test"))


class _Client:
    def __init__(self, fail=None, chunks=("a", "b")):
        self.calls: list[dict] = []
        self._fail = fail
        self._chunks = chunks
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._fail:
            raise self._fail
        if kwargs.get("stream"):
            return (
                SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=t))]
                )
                for t in self._chunks
            )
        message = SimpleNamespace(content="text", tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)


def _every_call(adapter):
    adapter.generate("s", "u")
    list(adapter.stream("s", "u"))
    adapter.complete_with_tools("s", "u", [SEARCH])
    adapter.converse_with_tools([UserMessage("u")], [SEARCH])


class TheDeadlineTests:
    def test_outside_a_run_there_is_no_time_left_to_read(self):
        assert time_left() is None

    def test_a_run_reports_what_is_left_and_restores_on_exit(self):
        with model_call_deadline(30):
            assert 29 < time_left() <= 30
        assert time_left() is None

    def test_a_nested_deadline_never_extends_the_outer_one(self):
        with model_call_deadline(5):
            with model_call_deadline(60):
                assert time_left() <= 5
            with model_call_deadline(1):
                assert time_left() <= 1


class EveryCallIsBoundedTests:
    def test_with_no_run_every_call_gets_the_default(self, settings):
        settings.LLM_TIMEOUT_SECONDS = 33
        client = _Client()

        _every_call(OpenAICompatibleAdapter(client=client))

        assert [c["timeout"] for c in client.calls] == [33, 33, 33, 33]

    def test_an_adapter_may_set_its_own_default(self, settings):
        settings.LLM_TIMEOUT_SECONDS = 33
        client = _Client()

        OpenAICompatibleAdapter(client=client, timeout_seconds=8).generate("s", "u")

        assert client.calls[0]["timeout"] == 8

    def test_inside_a_run_the_time_left_caps_every_call(self, settings):
        settings.LLM_TIMEOUT_SECONDS = 120
        client = _Client()

        with model_call_deadline(10):
            _every_call(OpenAICompatibleAdapter(client=client))

        assert all(0 < c["timeout"] <= 10 for c in client.calls)

    def test_a_shorter_explicit_timeout_still_wins_inside_a_run(self):
        client = _Client()

        with model_call_deadline(60):
            OpenAICompatibleAdapter(client=client).complete_with_tools(
                "s", "u", [SEARCH], timeout_seconds=2
            )

        assert client.calls[0]["timeout"] == 2

    @pytest.mark.parametrize(
        "call",
        [
            lambda a: a.generate("s", "u"),
            lambda a: list(a.stream("s", "u")),
            lambda a: a.complete_with_tools("s", "u", [SEARCH]),
            lambda a: a.converse_with_tools([UserMessage("u")], [SEARCH]),
        ],
        ids=["generate", "stream", "one-shot", "conversation"],
    )
    def test_a_spent_deadline_fails_as_a_timeout_without_calling(self, call):
        client = _Client()

        with model_call_deadline(0):
            with pytest.raises(LLMUnavailable) as raised:
                call(OpenAICompatibleAdapter(client=client))

        assert raised.value.kind is ErrorKind.TIMEOUT
        assert client.calls == []

    def test_a_stream_that_outlives_the_deadline_stops_as_a_timeout(self):
        clock = iter([0.0, 0.0, 1.0, 99.0, 99.0])

        def tick():
            return next(clock)

        client = _Client(chunks=("a", "b", "c"))
        adapter = OpenAICompatibleAdapter(client=client)
        received = []

        with model_call_deadline(10, clock=tick):
            with pytest.raises(LLMUnavailable) as raised:
                for delta in adapter.stream("s", "u"):
                    received.append(delta.text)

        assert raised.value.kind is ErrorKind.TIMEOUT
        assert received == ["a"]


class ASlowModelIsATransientFailureTests:
    def test_a_vendor_timeout_is_the_timeout_kind(self):
        adapter = OpenAICompatibleAdapter(client=_Client(fail=_timeout_error()))

        with pytest.raises(LLMUnavailable) as raised:
            adapter.generate("s", "u")

        assert raised.value.kind is ErrorKind.TIMEOUT

    @pytest.mark.parametrize(
        "call",
        [
            lambda p: p.generate("s", "u"),
            lambda p: list(p.stream("s", "u")),
            lambda p: p.converse_with_tools([UserMessage("u")], [SEARCH]),
        ],
        ids=["generate", "stream", "conversation"],
    )
    def test_retry_tries_again_on_a_timeout(self, call):
        client = _Client(fail=_timeout_error())
        provider = RetryingLLMProvider(
            OpenAICompatibleAdapter(client=client), attempts=2, sleep=lambda _: None
        )

        with pytest.raises(LLMUnavailable):
            call(provider)

        assert len(client.calls) == 2

    def test_repeated_timeouts_open_the_breaker(self):
        client = _Client(fail=_timeout_error())
        breaker = CircuitBreaker(failure_threshold=2)
        provider = CircuitBreakingLLMProvider(
            OpenAICompatibleAdapter(client=client), breaker=breaker
        )

        for _ in range(2):
            with pytest.raises(LLMUnavailable):
                provider.generate("s", "u")
        with pytest.raises(CircuitOpen):
            provider.generate("s", "u")

        assert len(client.calls) == 2
