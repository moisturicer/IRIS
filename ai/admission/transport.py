"""An AGENT provider whose every physical attempt is admitted (IR-725).

Each send -- the first, and each retry -- is reserved in the shared ledger,
rechecked by the guard, sent with the completion cap it reserved, bounded
by what remains of the run's deadline, and settled. A retry is another
attempt within the same allowance; nothing retries out of sight.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Optional

from ai.agent.dialect import serialize
from ai.agent.protocol import ToolResult
from ai.domain.ports import LLMProvider, TransientProviderError, UnsupportedCapability
from ai.infrastructure.settings import settings

from . import errors, scope
from .errors import AdmissionDenied
from .guard import ProxyApproval, SendGuard
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
        self.guard = guard or SendGuard(
            ledger.dsn, ProxyApproval.from_json(settings.RUNS_PROXY_SEND_APPROVAL),
            stage=settings.RUNS_DEPLOYMENT_STAGE)
        self.retries = retries
        self.timeout_seconds = timeout_seconds
        self.lane = lane
        self.purpose = purpose

    def _policy(self, pin) -> dict:
        limits = self.ledger.limits
        return {"account": self.provider.account,
                "campaign": limits.campaign_key if limits else None,
                "routing": getattr(self.provider, "routing", None),
                "price": getattr(limits, "prices", {}).get(pin.model) if limits else None}

    async def eligible(self, pin, sources: frozenset) -> frozenset:
        """Which of `sources` a send for this run may carry now; nothing outside a run."""
        binding = scope.current()
        if binding is None or not sources:
            return frozenset()
        return await self.guard.eligible(binding, pin, frozenset(sources), **self._policy(pin))

    def accepts(self, pin) -> bool:
        return self.provider.accepts(pin)

    def capacity(self, pin):
        return self.provider.capacity(pin)

    @property
    def dialect(self):
        return self.provider.dialect

    async def generate_response(self, prompt: str, context: str = "") -> str:
        raise UnsupportedCapability("generate_response")

    async def converse(self, request):
        if self.ledger.limits is not None:
            limit = self.ledger.limits.max_output_tokens
            if request.max_output_tokens is None:
                request = replace(request, max_output_tokens=limit)
            elif request.max_output_tokens > limit:
                # Lowering it would break the reserve it was fitted with (IR-732).
                raise AdmissionDenied(errors.OUTPUT_CAP_EXCEEDED)
        for attempt in range(self.retries + 1):
            try:
                return await self._attempt(request)
            except TransientProviderError:
                if attempt == self.retries:
                    raise

    async def _attempt(self, request):
        binding = scope.current()
        payload = serialize(self.provider.encode(request) if hasattr(self.provider, "encode")
                            else self.provider.dialect.encode(request))
        ticket = await self.ledger.admit(Request(
            operation="llm", purpose=self.purpose, purpose_version=request.pin.prompt_version,
            lane=self.lane, account=self.provider.account, models=(request.pin.model,),
            input_tokens=estimate_tokens(payload), output_tokens=request.max_output_tokens or 0,
            timeout_seconds=self.timeout_seconds,
        ), binding)
        usage = Usage()
        try:
            # Tool results carry Record content: the guard must authorize them.
            evidence = [e for e in request.history if isinstance(e, ToolResult)
                        or getattr(e, "dependencies", frozenset())
                        or getattr(e, "unverified_provenance", False)]
            # A previous model turn may carry derived text or opaque state even
            # when the original tool result has left the fitted context.
            await self.guard.check(binding, request.pin, evidence, **self._policy(request.pin))
            # From here the vendor may bill it, whatever happens next.
            usage.sent = True
            with scope.admitted_send():
                turn = await asyncio.wait_for(self.provider.converse(request), ticket.timeout_seconds)
            usage.input_tokens, usage.output_tokens = turn.input_tokens, turn.output_tokens
            usage.model = request.pin.model
            sources = frozenset().union(*(e.dependencies for e in evidence)) if evidence else frozenset()
            return replace(turn, dependencies=sources) if sources else turn
        finally:
            await ticket.settle(usage)
