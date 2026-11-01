"""A recording deterministic AGENT provider (IR-727).

Replays scripted wire responses through a real dialect and records every
outgoing payload. No network: real transport waits on IR-725 and IR-732.
"""

from __future__ import annotations

from ai.agent.dialect import ChatCompletions
from ai.domain.ports import LLMProvider, UnsupportedCapability


class RecordingAgentProvider(LLMProvider):
    adapter = "recording"

    def __init__(self, *, responses, endpoint="scripted", models=("scripted-model",),
                 capabilities=(), data_policies=("no-training",), dialect=ChatCompletions):
        self.responses = list(responses)
        self.endpoint = endpoint
        self.models = frozenset(models)
        self.capabilities = frozenset(capabilities)
        self.data_policies = frozenset(data_policies)
        self.dialect = dialect
        self.requests: list[dict] = []

    def accepts(self, pin) -> bool:
        return (
            pin.adapter == self.adapter and pin.endpoint == self.endpoint
            and pin.model in self.models and pin.dialect == self.dialect.name
            and pin.data_policy in self.data_policies and set(pin.requires) <= self.capabilities
        )

    async def generate_response(self, prompt: str, context: str = "") -> str:
        raise UnsupportedCapability("generate_response")

    async def converse(self, request):
        if not self.accepts(request.pin):
            raise UnsupportedCapability("pin")
        payload = self.dialect.encode(request)
        self.requests.append(payload)
        if not self.responses:
            raise UnsupportedCapability("script_exhausted")
        return self.dialect.decode(self.responses.pop(0), request.pin)
