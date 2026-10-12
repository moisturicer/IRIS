"""A metered fake adapter and enforced settings, for admission tests (IR-545).

The fake talks to no vendor and costs nothing. It behaves like the real
adapter only where admission looks: it carries a model list, a completion cap,
an account and a call timeout, it marks the moment a request would be sent,
and it reports the usage a vendor would.
"""

from __future__ import annotations

from typing import Iterator, Optional, Sequence

from apps.ai.admission.scope import mark_sent, report_usage
from apps.ai.providers.errors import ErrorKind
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.providers.ports import StreamDelta
from apps.ai.providers.tool_calling import ToolCallingLLM, ToolCompletion

#: The proposed IR-551 campaign (pilot README §7), for tests only. None of
#: these figures is approved; a test sets them so it has something to count.
CAMPAIGN = {
    "AI_ADMISSION_CAMPAIGN": "test-campaign",
    "AI_ADMISSION_CAMPAIGN_MAX_ATTEMPTS": "480",
    "AI_ADMISSION_CAMPAIGN_MAX_INPUT_TOKENS": "500000",
    "AI_ADMISSION_CAMPAIGN_MAX_OUTPUT_TOKENS": "80000",
    "AI_ADMISSION_CAMPAIGN_MAX_COST_USD": "15",
    "AI_ADMISSION_CAMPAIGN_MAX_ACTIVE_MINUTES": "60",
    "AI_ADMISSION_RESERVE_FRACTION": "0.25",
    "AI_ADMISSION_RUN_MAX_ATTEMPTS": "12",
    "AI_ADMISSION_RUN_MAX_INPUT_TOKENS": "60000",
    "AI_ADMISSION_RUN_MAX_OUTPUT_TOKENS": "8000",
    "AI_ADMISSION_RUN_MAX_COST_USD": "0.50",
    "AI_ADMISSION_LANE_CONCURRENCY": (
        '{"chat": 8, "research": 3, "ingestion": 2, "embedding": 4, "reranking": 4,'
        ' "overview": 1, "shadow": 1}'
    ),
    "AI_ADMISSION_ACCOUNT_CONCURRENCY": "10",
    "AI_ADMISSION_PRICES": (
        '{"cheap": {"input": 1.0, "output": 2.0}, "dear": {"input": 3.0, "output": 15.0},'
        ' "voyage-context-4": {"input": 0.18, "output": 0}, "rerank-3": {"input": 0.05, "output": 0}}'
    ),
    "AI_ADMISSION_MAX_OUTPUT_TOKENS": "500",
    "AI_ADMISSION_QUEUE_DEPTH": "100",
    "AI_ADMISSION_QUEUE_PER_USER": "2",
    "AI_ADMISSION_LEASE_GRACE_SECONDS": "5",
}


def enforce(settings, **overrides) -> None:
    """Turn admission on with the test campaign, then apply ``overrides``."""
    settings.AI_PROVIDER_ADMISSION = "enforce"
    settings.AI_ADMISSION_RESERVE_RELEASED = False
    for name, value in {**CAMPAIGN, **overrides}.items():
        setattr(settings, name, value)


class MeteredAdapter(ToolCallingLLM):
    """Stands where `OpenAICompatibleAdapter` stands, behind admission."""

    def __init__(
        self,
        *,
        model: str = "cheap",
        fallback_models: Sequence[str] = (),
        max_tokens: Optional[int] = 500,
        account: str = "acct-a",
        timeout: float = 10.0,
        text: str = "Rainfall gauges feed the model [1].",
        deltas: Sequence[str] = ("Rainfall gauges ", "feed the model [1]."),
        usage: Optional[tuple[int, int]] = (120, 30),
        stream_usage: Optional[tuple[int, int]] = None,
        fail_before_send: Optional[Exception] = None,
        fail_after_send: Optional[Exception] = None,
    ) -> None:
        self.model = model
        self.models = (model, *fallback_models) if fallback_models else ()
        self.max_tokens = max_tokens
        self.account = account
        self._timeout = timeout
        self._text = text
        self._deltas = tuple(deltas)
        self._usage = usage
        self._stream_usage = stream_usage
        self._fail_before_send = fail_before_send
        self._fail_after_send = fail_after_send
        self.sent = 0
        self.timeouts: list[float] = []

    def call_timeout(self, explicit: Optional[float] = None) -> float:
        from apps.ai.providers.deadline import bounded
        from apps.ai.providers.openai_compatible import DeadlineExceeded

        seconds = bounded(explicit or self._timeout)
        if seconds <= 0:
            raise DeadlineExceeded("the run's deadline has passed")
        self.timeouts.append(seconds)
        return seconds

    def _send(self) -> None:
        if self._fail_before_send is not None:
            raise self._fail_before_send
        mark_sent()
        self.sent += 1
        if self._fail_after_send is not None:
            raise self._fail_after_send

    def generate(self, system: str, user: str) -> str:
        self._send()
        if self._usage is not None:
            report_usage(input_tokens=self._usage[0], output_tokens=self._usage[1], model=self.model)
        return self._text

    def stream(self, system: str, user: str) -> Iterator[StreamDelta]:
        self._send()
        for text in self._deltas:
            yield StreamDelta(text=text)
        if self._stream_usage is not None:
            report_usage(
                input_tokens=self._stream_usage[0], output_tokens=self._stream_usage[1],
                model=self.model,
            )

    def complete_with_tools(self, system, user, tools, *, timeout_seconds=None) -> ToolCompletion:
        self._send()
        return ToolCompletion(text=self._text, reasoning="", tool_calls=())

    def converse_with_tools(self, messages, tools, *, timeout_seconds=None) -> ToolCompletion:
        self._send()
        return ToolCompletion(text=self._text, reasoning="", tool_calls=())


def network_failure() -> LLMUnavailable:
    return LLMUnavailable("connection reset", kind=ErrorKind.NETWORK)
