"""A structured completion record for every model call (IR-387).

No vendor account and no Django settings needed: `CompletionLoggingLLMProvider`
wraps a plain `LLMProvider` fake and a `Profile` built by hand, so these
assert the decorator's own behaviour directly rather than through
`profile_for`'s settings resolution (that seam is `test_fallback.py`'s).
"""

from __future__ import annotations

import logging
from typing import Iterator

import pytest

from apps.ai.inference.completions import (
    CIRCUIT_OPEN,
    LOGGER_NAME,
    CompletionLoggingLLMProvider,
)
from apps.ai.inference.profiles import DataPolicy, Profile, Vendor
from apps.ai.inference.tasks import InferenceTask
from apps.ai.providers.errors import ErrorKind
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.providers.ports import LLMProvider, StreamDelta
from apps.ai.resilience.circuit import CircuitOpen
from apps.ai.resilience.llm import FallbackLLMProvider


#: `apps` sets `propagate: False` in `config/settings/base.py`, so records
#: logged under it never reach the root logger caplog captures at by default.
#:
#: This toggles `apps`'s own propagation back on for the test, rather than
#: attaching `caplog.handler` directly to this module's logger (the older
#: fixture shape `apps/ai/answers/tests/test_service.py` uses): pytest 9
#: changed `caplog` to auto-attach its handler to every *non-propagating*
#: logger it finds -- `apps` included -- specifically to fix this exact
#: problem, so a manual attachment here would double-deliver every record
#: under pytest 9 while still being required for pytest 8, which has no such
#: fix. Restoring propagation instead works unchanged on both: the record
#: reaches root -- where caplog always attaches -- exactly once either way.
_APPS_LOGGER = "apps"


@pytest.fixture(autouse=True)
def _wire_caplog_to_the_completion_logger(caplog):
    apps_logger = logging.getLogger(_APPS_LOGGER)
    original_propagate = apps_logger.propagate
    apps_logger.propagate = True
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    try:
        yield
    finally:
        apps_logger.propagate = original_propagate


def _profile(model: str = "first", fallback_models: tuple[str, ...] = ()) -> Profile:
    return Profile(
        task=InferenceTask.ANSWER,
        vendor=Vendor.GROQ,
        model=model,
        fallback_models=fallback_models,
        base_url="https://api.groq.com/openai/v1",
        api_key="a-key",
        reasoning_visible=False,
        data_policy=DataPolicy.NO_TRAINING,
    )


class _ScriptedLLM(LLMProvider):
    """Answers, fails, or streams exactly what a test hands it."""

    def __init__(
        self,
        model: str = "first",
        reply: str = "An answer.",
        failure: Exception | None = None,
        stream_deltas: Iterator[StreamDelta] | None = None,
    ):
        self.model = model
        self._reply = reply
        self._failure = failure
        self._stream_deltas = stream_deltas

    def generate(self, system: str, user: str) -> str:
        if self._failure is not None:
            raise self._failure
        return self._reply

    def stream(self, system: str, user: str) -> Iterator[StreamDelta]:
        if self._failure is not None:
            raise self._failure
        for delta in self._stream_deltas or ():
            yield delta


def _log(caplog):
    [record] = [r for r in caplog.records if r.name == LOGGER_NAME]
    return record


class GenerateSuccessTests:
    def test_a_clean_call_logs_the_task_vendor_and_model(self, caplog):
        caplog.set_level("INFO", logger=LOGGER_NAME)
        llm = CompletionLoggingLLMProvider(_ScriptedLLM(model="first"), _profile())

        assert llm.generate(system="s", user="u") == "An answer."

        record = _log(caplog)
        assert record.inference_task == "answer"
        assert record.vendor == "groq"
        assert record.model == "first"
        assert record.fallback_fired is False
        assert record.reasoning_present is False
        assert record.error_kind is None

    def test_generate_never_reports_reasoning_present(self, caplog):
        """`generate()` returns text only -- reasoning is `stream()`'s own
        channel (`StreamDelta.reasoning`), so this can never be true here."""
        caplog.set_level("INFO", logger=LOGGER_NAME)
        llm = CompletionLoggingLLMProvider(_ScriptedLLM(), _profile())

        llm.generate(system="s", user="u")

        assert _log(caplog).reasoning_present is False


class GenerateFailureTests:
    @pytest.mark.parametrize(
        "kind",
        [ErrorKind.AUTH, ErrorKind.RATE_LIMIT, ErrorKind.NETWORK, ErrorKind.TIMEOUT,
         ErrorKind.CONTEXT_OVERFLOW, ErrorKind.UNKNOWN],
    )
    def test_a_vendor_failure_logs_its_kind_and_still_raises(self, caplog, kind):
        caplog.set_level("INFO", logger=LOGGER_NAME)
        failure = LLMUnavailable("vendor said no", kind=kind)
        llm = CompletionLoggingLLMProvider(
            _ScriptedLLM(model="first", failure=failure), _profile()
        )

        with pytest.raises(LLMUnavailable):
            llm.generate(system="s", user="u")

        record = _log(caplog)
        assert record.error_kind == kind.value
        assert record.model == "first"

    def test_an_open_circuit_logs_circuit_open_not_unknown(self, caplog):
        """`CircuitOpen` carries no `.kind` -- nothing was tried, so this must
        not be mislabelled the same as an unclassified vendor failure."""
        caplog.set_level("INFO", logger=LOGGER_NAME)
        llm = CompletionLoggingLLMProvider(
            _ScriptedLLM(failure=CircuitOpen("breaker open")), _profile()
        )

        with pytest.raises(CircuitOpen):
            llm.generate(system="s", user="u")

        assert _log(caplog).error_kind == CIRCUIT_OPEN


class FallbackFiredTests:
    """`fallback_fired` and the post-fallback model are read off the wrapped
    provider, the same way `answers/service.py` already does (IR-385)."""

    def test_no_fallback_reports_the_configured_model_and_false(self, caplog):
        caplog.set_level("INFO", logger=LOGGER_NAME)
        llm = CompletionLoggingLLMProvider(_ScriptedLLM(model="first"), _profile("first"))

        llm.generate(system="s", user="u")

        record = _log(caplog)
        assert record.model == "first"
        assert record.fallback_fired is False

    def test_a_fired_fallback_names_the_model_that_actually_answered(self, caplog):
        caplog.set_level("INFO", logger=LOGGER_NAME)
        first = _ScriptedLLM(
            model="first", failure=LLMUnavailable("down", kind=ErrorKind.NETWORK)
        )
        second = _ScriptedLLM(model="second", reply="Answered by second.")
        inner = FallbackLLMProvider([first, second])
        llm = CompletionLoggingLLMProvider(inner, _profile("first", ("second",)))

        assert llm.generate(system="s", user="u") == "Answered by second."

        record = _log(caplog)
        assert record.model == "second"
        assert record.fallback_fired is True

    def test_exhausting_the_list_names_the_last_model_tried_not_the_first(
        self, caplog
    ):
        """`FallbackLLMProvider.last_model_used` is set only on success, so a
        call where every model failed cannot be read through it -- that
        would report the model configured first as the one whose failure
        this record describes, when it was actually the last one tried
        (IR-387: 'the model actually used ... not the one configured
        first' applies to a failed call too, not only a successful one)."""
        caplog.set_level("INFO", logger=LOGGER_NAME)
        first = _ScriptedLLM(
            model="first", failure=LLMUnavailable("down", kind=ErrorKind.RATE_LIMIT)
        )
        second = _ScriptedLLM(
            model="second", failure=LLMUnavailable("also down", kind=ErrorKind.RATE_LIMIT)
        )
        inner = FallbackLLMProvider([first, second])
        llm = CompletionLoggingLLMProvider(inner, _profile("first", ("second",)))

        with pytest.raises(LLMUnavailable):
            llm.generate(system="s", user="u")

        record = _log(caplog)
        assert record.model == "second"
        assert record.fallback_fired is True
        assert record.error_kind == ErrorKind.RATE_LIMIT.value


class StreamTests:
    def test_reasoning_arriving_on_any_delta_is_reported(self, caplog):
        caplog.set_level("INFO", logger=LOGGER_NAME)
        deltas = [StreamDelta(reasoning="thinking..."), StreamDelta(text="answer")]
        llm = CompletionLoggingLLMProvider(
            _ScriptedLLM(stream_deltas=iter(deltas)), _profile()
        )

        collected = list(llm.stream(system="s", user="u"))

        assert collected == deltas
        assert _log(caplog).reasoning_present is True

    def test_no_reasoning_delta_reports_false(self, caplog):
        caplog.set_level("INFO", logger=LOGGER_NAME)
        deltas = [StreamDelta(text="answer")]
        llm = CompletionLoggingLLMProvider(
            _ScriptedLLM(stream_deltas=iter(deltas)), _profile()
        )

        list(llm.stream(system="s", user="u"))

        assert _log(caplog).reasoning_present is False

    def test_a_failure_mid_stream_still_logs_a_record(self, caplog):
        caplog.set_level("INFO", logger=LOGGER_NAME)
        failure = LLMUnavailable("dropped", kind=ErrorKind.NETWORK)
        llm = CompletionLoggingLLMProvider(
            _ScriptedLLM(model="first", failure=failure), _profile()
        )

        with pytest.raises(LLMUnavailable):
            list(llm.stream(system="s", user="u"))

        record = _log(caplog)
        assert record.error_kind == ErrorKind.NETWORK.value
        assert record.model == "first"


class NoContentLeaksIntoTheRecordTests:
    def test_the_question_and_answer_text_are_not_in_the_log(self, caplog):
        caplog.set_level("INFO", logger=LOGGER_NAME)
        llm = CompletionLoggingLLMProvider(
            _ScriptedLLM(reply="a very specific secret answer"), _profile()
        )

        llm.generate(system="secret system prompt", user="secret question")

        record = _log(caplog)
        assert "secret" not in record.getMessage()
        assert not hasattr(record, "question")
        assert not hasattr(record, "answer")
