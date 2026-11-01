"""A recording deterministic AGENT provider (IR-727).

Replays scripted wire responses through a real dialect and records every
outgoing payload. No network: real transport waits on IR-725 and IR-732.
"""

from __future__ import annotations

from ai.agent.dialect import ChatCompletions
from ai.domain.ports import LLMProvider, UnsupportedCapability


class RecordingAgentProvider(LLMProvider):
    def __init__(self, *, responses, endpoint="scripted", models=("scripted-model",),
                 capabilities=(), dialect=ChatCompletions):
        self.responses = list(responses)
        self.endpoint = endpoint
        self.models = frozenset(models)
        self.capabilities = frozenset(capabilities)
        self.dialect = dialect
        self.requests: list[dict] = []

    async def generate_response(self, prompt: str, context: str = "") -> str:
        raise UnsupportedCapability("generate_response")

    async def converse(self, request):
        pin = request.pin
        if (pin.endpoint != self.endpoint or pin.model not in self.models
                or pin.dialect != self.dialect.name):
            raise UnsupportedCapability("pin")
        payload = self.dialect.encode(request)
        self.requests.append(payload)
        if not self.responses:
            raise UnsupportedCapability("script_exhausted")
        return self.dialect.decode(self.responses.pop(0), endpoint=self.endpoint, model=pin.model)
