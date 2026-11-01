"""Answer a direct question through the pinned AGENT contract (IR-727).

One model turn, no tools: the tool loop is IR-728. The pin is checked
against what this code and the provider support before anything is sent;
a mismatch is `unavailable`, never a substitute model or dialect.
"""

from __future__ import annotations

from ai.agent.protocol import AgentRequest, NotFinal, Pin, User, final_answer
from ai.domain.ports import LLMProvider, UnsupportedCapability
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

    def __init__(self, provider: LLMProvider, pin: Pin):
        self.provider = provider
        self.pin = pin

    def supported(self) -> bool:
        pin, provider = self.pin, self.provider
        dialect = getattr(provider.dialect, "name", None)
        return (
            all(getattr(pin, k) == v for k, v in SUPPORTED.items())
            and pin.endpoint == provider.endpoint and pin.model in provider.models
            and pin.dialect == dialect and set(pin.requires) <= set(provider.capabilities)
        )

    async def answer(self, question: str) -> Result:
        if not self.supported():
            raise Unavailable("unsupported_pin")
        request = AgentRequest(pin=self.pin, instructions=INSTRUCTIONS, history=(User(question),))
        try:
            turn = await self.provider.converse(request)
        except UnsupportedCapability:
            raise Unavailable("unsupported_pin") from None
        try:
            text = final_answer(turn)
        except NotFinal as refused:
            raise Unavailable(refused.code) from None
        return Result(answer=text, reported_units=(turn.input_tokens or 0) + (turn.output_tokens or 0))
