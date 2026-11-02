"""Answer a direct question through the pinned AGENT contract (IR-727).

One model turn; `tools` is accepted and unused until the tool loop (IR-728). The pin is checked
against what this code and the provider support before anything is sent;
a mismatch is `unavailable`, never a substitute model or dialect.
"""

from __future__ import annotations

import asyncio

from ai.admission.errors import AdmissionDenied
from ai.agent.context import FittedAgentProvider, OverCapacity, Reserves
from ai.agent.protocol import AgentRequest, NotFinal, Pin, User, final_answer
from ai.domain.ports import LLMProvider, TransientProviderError, UnsupportedCapability
from ai.runs import config as runs_config
from ai.runs.executor import Result, Unavailable

PROMPT_VERSION = "agent-direct-1"
TOOL_VERSION = "none-1"
INSTRUCTIONS = (
    "You are the IRIS research assistant. Answer the reader's question directly. "
    "Say plainly when general background is not a finding from the repository."
)

#: The versions this code implements; a run pinned to any other is refused.
SUPPORTED = {
    "prompt_version": PROMPT_VERSION, "tool_version": TOOL_VERSION,
    "public_version": runs_config.PROTOCOL, "state_version": runs_config.SCHEMA,
}


class AgentExecutor:
    name = "agent"
    version = "1"
    reserved_units = 0

    def __init__(self, provider: LLMProvider, pin: Pin, reserves: Reserves):
        self.provider = provider
        self.pin = pin
        #: Every request is fitted to the pinned model's verified capacity (IR-732).
        self.sender = FittedAgentProvider(provider, reserves)

    @property
    def capacity_status(self):
        """The last request's capacity status, or None before any."""
        return self.sender.statuses[-1] if self.sender.statuses else None

    def supported(self) -> bool:
        return (all(getattr(self.pin, k) == v for k, v in SUPPORTED.items())
                and self.provider.accepts(self.pin))

    def admitted(self) -> bool:
        """A provider that may bill is reached only through admission (IR-725)."""
        return getattr(self.provider, "admitted", False) or not getattr(self.provider, "paid", True)

    async def answer(self, question: str, tools=None) -> Result:
        if not self.supported():
            raise Unavailable("unsupported_pin")
        if not self.admitted():
            raise Unavailable("not_admitted")
        request = AgentRequest(pin=self.pin, instructions=INSTRUCTIONS, history=(User(question),))
        try:
            turn = await self.sender.converse(request)
        except OverCapacity as refused:
            # The status, numbers only, is logged by the sender.
            raise Unavailable(refused.code) from None
        except UnsupportedCapability:
            raise Unavailable("unsupported_pin") from None
        except AdmissionDenied as refused:
            raise Unavailable(refused.reason) from None
        except asyncio.TimeoutError:
            raise Unavailable("provider_timeout") from None
        except TransientProviderError:
            raise Unavailable("provider_failed") from None
        try:
            text = final_answer(turn)
        except NotFinal as refused:
            raise Unavailable(refused.code) from None
        return Result(answer=text, reported_units=(turn.input_tokens or 0) + (turn.output_tokens or 0))
