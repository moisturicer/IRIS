"""An AGENT provider whose every physical attempt is admitted (IR-725).

Each send -- the first, and each retry -- is reserved in the shared ledger,
rechecked by the guard, sent with the completion cap it reserved, bounded
by what remains of the run's deadline, and settled. A retry is another
attempt within the same allowance; nothing retries out of sight.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from typing import Optional

from ai.agent.protocol import ToolResult
from ai.domain.ports import LLMProvider, TransientProviderError, UnsupportedCapability

from . import scope
from .guard import SendGuard
from .ledger import Ledger, Request, Usage, estimate_tokens

RESEARCH_LANE = "research"


class AdmittedAgentProvider(LLMProvider):
    #: What `AgentExecutor` requires of a paid provider.
    admitted = True

    def __init__(self, provider: LLMProvider, ledger: Ledger, *, guard: Optional[SendGuard] = None,
                 retries: int = 0, timeout_seconds: Optional[float] = None,
                 lane: str = RESEARCH_LANE, purpose: str = "answer"):
        self.provider = provider
        self.ledger = ledger
        self.guard = guard or SendGuard(ledger.dsn)
        self.retries = retries
        self.timeout_seconds = timeout_seconds
        self.lane = lane
        self.purpose = purpose

    def accepts(self, pin) -> bool:
        return self.provider.accepts(pin)

    async def generate_response(self, prompt: str, context: str = "") -> str:
        raise UnsupportedCapability("generate_response")

    async def converse(self, request):
        if self.ledger.limits is not None:
            request = replace(request, max_output_tokens=self.ledger.limits.max_output_tokens)
        for attempt in range(self.retries + 1):
            try:
                return await self._attempt(request)
            except TransientProviderError:
                if attempt == self.retries:
                    raise

    async def _attempt(self, request):
        binding = scope.current()
        payload = json.dumps(self.provider.dialect.encode(request), default=str, ensure_ascii=False)
        ticket = await self.ledger.admit(Request(
            operation="llm", purpose=self.purpose, purpose_version=request.pin.prompt_version,
            lane=self.lane, account=self.provider.account, models=(request.pin.model,),
            input_tokens=estimate_tokens(payload), output_tokens=request.max_output_tokens or 0,
            timeout_seconds=self.timeout_seconds,
        ), binding)
        usage = Usage()
        try:
            # Tool results carry Record content: the guard must authorize them.
            evidence = [e for e in request.history if isinstance(e, ToolResult)]
            await self.guard.check(binding, request.pin, evidence)
            # From here the vendor may bill it, whatever happens next.
            usage.sent = True
            turn = await asyncio.wait_for(self.provider.converse(request), ticket.timeout_seconds)
            usage.input_tokens, usage.output_tokens = turn.input_tokens, turn.output_tokens
            usage.model = request.pin.model
            return turn
        finally:
            await ticket.settle(usage)
