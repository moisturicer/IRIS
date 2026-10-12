"""Admission around one chat-model adapter (IR-545, ADR-041).

Sits *inside* `RetryingLLMProvider` and `FallbackLLMProvider`, directly on the
adapter, so every physical attempt is admitted on its own: the first try, the
retry, and each fallback model. The adapter has the SDK's own retries turned
off under enforcement (`bounded_attempts`), so no attempt happens out of sight.

A refusal raises `AdmissionDenied`, which the decorators above neither retry
nor fail over on, and which the answer paths turn into their explicit
unavailable state with whatever sources they hold.
"""

from __future__ import annotations

import json
import time
from typing import Callable, Iterator, Optional, Sequence

from apps.ai.providers.dialects import DEFAULT_DIALECT, VendorDialect
from apps.ai.providers.ports import LLMProvider, StreamDelta
from apps.ai.providers.tool_calling import (
    Message,
    ToolCallingLLM,
    ToolCompletion,
    ToolDefinition,
)

from . import scope
from .ledger import Request, admit, estimate_tokens, provider_attempt
from .limits import enforcing

#: What an attempt is charged to when no workload names a lane.
DEFAULT_LANE = "chat"


def _message_text(message: Message) -> str:
    return json.dumps(getattr(message, "__dict__", str(message)), default=str, ensure_ascii=False)


class AdmittedLLMProvider(LLMProvider, ToolCallingLLM):
    def __init__(
        self,
        adapter,
        *,
        lane: str = DEFAULT_LANE,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._adapter = adapter
        self._lane = lane
        self._clock = clock

    @property
    def model(self) -> str:
        return getattr(self._adapter, "model", "unknown")

    @property
    def dialect(self) -> VendorDialect:
        return getattr(self._adapter, "dialect", DEFAULT_DIALECT)

    def _request(self, texts: Sequence[str], timeout: Optional[float] = None) -> Request:
        adapter = self._adapter
        return Request(
            operation="llm",
            default_lane=self._lane,
            account=adapter.account,
            models=tuple(adapter.models) or (adapter.model,),
            input_tokens=estimate_tokens(*texts),
            output_tokens=adapter.max_tokens,
            # Raises `DeadlineExceeded` before anything is reserved once the
            # run's deadline has passed.
            timeout_seconds=adapter.call_timeout(timeout),
        )

    def generate(self, system: str, user: str) -> str:
        with provider_attempt(self._request((system, user))):
            return self._adapter.generate(system, user)

    def stream(self, system: str, user: str) -> Iterator[StreamDelta]:
        if not enforcing():
            yield from self._adapter.stream(system, user)
            return
        ticket = admit(self._request((system, user)))
        usage = scope.AttemptUsage()
        # The usage scope is entered around each pull, not across the yields:
        # under ASGI the next pull may run in another thread.
        deltas = scope.stepwise(
            self._adapter.stream(system, user), lambda: scope.attempt_usage(usage)
        )
        try:
            # A renewal is due once half the lease has gone, well before a
            # single read could outlast it.
            every = ticket.lease_seconds / 2
            renewed = self._clock()
            for delta in deltas:
                if self._clock() - renewed >= every:
                    ticket.renew()
                    renewed = self._clock()
                yield delta
        finally:
            # Close the vendor stream first, so it is over before its slot is
            # given back. A stream closed early -- the reader left, the
            # deadline passed -- is settled at whatever was reported so far.
            deltas.close()
            ticket.settle(usage)

    def complete_with_tools(
        self,
        system: str,
        user: str,
        tools: Sequence[ToolDefinition],
        *,
        timeout_seconds: Optional[float] = None,
    ) -> ToolCompletion:
        schema = json.dumps([tool.__dict__ for tool in tools], default=str, ensure_ascii=False)
        with provider_attempt(self._request((system, user, schema), timeout_seconds)):
            return self._adapter.complete_with_tools(
                system, user, tools, timeout_seconds=timeout_seconds
            )

    def converse_with_tools(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
        *,
        timeout_seconds: Optional[float] = None,
    ) -> ToolCompletion:
        texts = [_message_text(message) for message in messages]
        texts.append(json.dumps([tool.__dict__ for tool in tools], default=str, ensure_ascii=False))
        with provider_attempt(self._request(texts, timeout_seconds)):
            return self._adapter.converse_with_tools(
                messages, tools, timeout_seconds=timeout_seconds
            )
