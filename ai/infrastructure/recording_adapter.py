"""A recording deterministic AGENT provider (IR-727).

Replays scripted wire responses through a real dialect and records every
outgoing payload. A scripted exception is raised after recording, and
`HANG` never answers (IR-725). A callable is given the payload and returns
the response, so a script can cite what the tools returned (IR-728). No network.
"""

from __future__ import annotations

import asyncio
import hashlib

from ai.agent.dialect import ChatCompletions
from ai.domain.ports import LLMProvider, UnsupportedCapability

#: A scripted response that never arrives.
HANG = object()


class RecordingAgentProvider(LLMProvider):
    adapter = "recording"
    #: Bills nothing, so it may run unadmitted (IR-725).
    paid = False

    def __init__(self, *, responses, endpoint="scripted", models=("scripted-model",),
                 capabilities=(), data_policies=("no-training",), dialect=ChatCompletions,
                 capacities=None):
        self.responses = list(responses)
        self.endpoint = endpoint
        self.models = frozenset(models)
        self.capabilities = frozenset(capabilities)
        self.data_policies = frozenset(data_policies)
        self.dialect = dialect
        #: Declared per model; a model with none has unknown capacity (IR-732).
        self.capacities = dict(capacities or {})
        self.requests: list[dict] = []

    def accepts(self, pin) -> bool:
        return (
            pin.adapter == self.adapter and pin.endpoint == self.endpoint
            and pin.model in self.models and pin.dialect == self.dialect.name
            and pin.data_policy in self.data_policies and set(pin.requires) <= self.capabilities
        )

    def capacity(self, pin):
        return self.capacities.get(pin.model) if self.accepts(pin) else None

    async def generate_response(self, prompt: str, context: str = "") -> str:
        raise UnsupportedCapability("generate_response")

    async def converse(self, request):
        if not self.accepts(request.pin):
            raise UnsupportedCapability("pin")
        payload = self.dialect.encode(request)
        self.requests.append(payload)
        if not self.responses:
            raise UnsupportedCapability("script_exhausted")
        response = self.responses.pop(0)
        if callable(response):
            response = response(payload)
        if response is HANG:
            await asyncio.Event().wait()
        if isinstance(response, Exception):
            raise response
        return self.dialect.decode(response, request.pin)

    @property
    def account(self) -> str:
        """A digest naming the vendor account; here, the scripted endpoint."""
        return hashlib.sha256(self.endpoint.encode()).hexdigest()[:32]
