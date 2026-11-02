"""Fit the complete outgoing request within verified model capacity (IR-732, ADR-049 §17).

Measures the payload the dialect will actually send, never the typed request.
Occupancy is a token estimate from bytes; paid spend stays with admission's
byte-based reservation (IR-725), and the run allowance is not consulted here.
"""

from __future__ import annotations

import json
import logging
import math
from collections import deque
from dataclasses import asdict, dataclass, replace
from typing import Optional

from ai.agent.protocol import (
    AgentRequest, BrokenExchange, ModelTurn, Opaque, ToolGroup, ToolResult, User,
)
from ai.admission import scope
from ai.agent.dialect import serialize
from ai.domain.ports import LLMProvider, UnsupportedCapability

log = logging.getLogger(__name__)

FITS = "fits"
CAPACITY_UNKNOWN = "capacity_unknown"
RESERVE_EXCEEDS_OUTPUT = "reserve_exceeds_output"
RESERVE_EXCEEDS_CONTEXT = "reserve_exceeds_context"
REQUEST_BYTES_EXCEEDED = "request_bytes_exceeded"
CONTEXT_EXHAUSTED = "context_exhausted"
COMPACTION_REQUIRED = "compaction_required"


@dataclass(frozen=True)
class Capacity:
    """What an adapter has verified for one model at its endpoint; nothing defaults."""

    #: Input plus generated tokens, one request.
    context_tokens: int
    #: Answer tokens, plus reasoning when `max_reasoning_tokens` is None.
    max_output_tokens: int
    #: A separately budgeted reasoning limit; None counts reasoning as output.
    max_reasoning_tokens: Optional[int]
    max_request_bytes: int
    #: The tokenizer's floor; 1.0 bounds any byte-level tokenizer.
    min_bytes_per_token: float
    #: Tokens the provider adds around each message.
    framing_tokens_per_message: int

    def __post_init__(self):
        for name in ("context_tokens", "max_output_tokens", "max_request_bytes", "min_bytes_per_token"):
            if not getattr(self, name) > 0:
                raise ValueError(f"capacity {name} must be positive")
        if self.max_reasoning_tokens is not None and self.max_reasoning_tokens < 0:
            raise ValueError("capacity max_reasoning_tokens must not be negative")
        if self.framing_tokens_per_message < 0:
            raise ValueError("capacity framing_tokens_per_message must not be negative")


@dataclass(frozen=True)
class Reserves:
    """Held back before any evidence is admitted."""

    output_tokens: int
    reasoning_tokens: int
    #: Room for the next tool result to arrive.
    next_result_tokens: int
    #: What one repair adds to the prompt; 0 allows none. Never more than one.
    repair_tokens: int

    def __post_init__(self):
        if self.output_tokens <= 0:
            raise ValueError("reserve output_tokens must be positive")
        for name in ("reasoning_tokens", "next_result_tokens", "repair_tokens"):
            if getattr(self, name) < 0:
                raise ValueError(f"reserve {name} must not be negative")

    @property
    def total(self) -> int:
        return self.output_tokens + self.reasoning_tokens + self.next_result_tokens + self.repair_tokens


@dataclass(frozen=True)
class Status:
    """Numbers and an outcome only: safe to log, never content."""

    outcome: str
    #: Token figures are estimates from bytes, never a tokenizer's count.
    estimated: bool = True
    request_bytes: int = 0
    max_request_bytes: int = 0
    occupancy_tokens: int = 0
    reserved_tokens: int = 0
    context_tokens: int = 0
    instructions_bytes: int = 0
    tools_bytes: int = 0
    history_bytes: int = 0
    evidence_bytes: int = 0
    opaque_bytes: int = 0
    framing_bytes: int = 0
    #: Tool results replaced by an explicit marker because they did not fit.
    withheld_results: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


class OverCapacity(Exception):
    """Nothing was sent; `status` says why in numbers."""

    def __init__(self, code: str, status: Status):
        super().__init__(code)
        self.code = code
        self.status = status


def _bytes(value) -> int:
    return len(json.dumps(value, default=str, ensure_ascii=False).encode("utf-8"))


def _known(capacity: Optional[Capacity]) -> Capacity:
    if capacity is None:
        raise OverCapacity(CAPACITY_UNKNOWN, Status(outcome=CAPACITY_UNKNOWN))
    return capacity


def output_cap(capacity: Capacity, reserves: Reserves) -> int:
    """The completion cap to send: reasoning rides inside it unless budgeted apart."""
    if capacity.max_reasoning_tokens is None:
        return reserves.output_tokens + reserves.reasoning_tokens
    return reserves.output_tokens


def measure(request: AgentRequest, dialect, capacity: Capacity, reserves: Reserves) -> Status:
    """The serialized request, split by what it carries; framing is the remainder."""
    payload = dialect.encode(request)
    total = len(serialize(payload).encode("utf-8"))
    instructions = _bytes(request.instructions)
    tools = _bytes(payload["tools"]) if "tools" in payload else 0
    history = evidence = opaque = 0
    for entry in request.history:
        if isinstance(entry, User):
            history += _bytes(entry.text)
        elif isinstance(entry, ToolResult):
            evidence += _bytes(entry.content)
        elif isinstance(entry, ModelTurn):
            if entry.text:
                history += _bytes(entry.text)
            for item in entry.items:
                if isinstance(item, Opaque):
                    opaque += _bytes(item.payload)
    messages = len(payload.get("messages", ()))
    occupancy = math.ceil(total / capacity.min_bytes_per_token) + messages * capacity.framing_tokens_per_message
    return Status(
        outcome=FITS, request_bytes=total, max_request_bytes=capacity.max_request_bytes,
        occupancy_tokens=occupancy, reserved_tokens=reserves.total, context_tokens=capacity.context_tokens,
        instructions_bytes=instructions, tools_bytes=tools, history_bytes=history, evidence_bytes=evidence,
        opaque_bytes=opaque, framing_bytes=total - instructions - tools - history - evidence - opaque,
    )


def fit(request: AgentRequest, dialect, capacity: Optional[Capacity], reserves: Reserves,
        *, compaction: bool = False) -> tuple[AgentRequest, Status]:
    """The request with its output cap set, or `OverCapacity`; never a clipped one."""
    capacity = _known(capacity)
    request = replace(request, max_output_tokens=output_cap(capacity, reserves))
    status = measure(request, dialect, capacity, reserves)
    code = _refusal(status, capacity, reserves, compaction)
    if code:
        raise OverCapacity(code, replace(status, outcome=code))
    return request, status


def pack(request: AgentRequest, results, dialect, capacity: Optional[Capacity], reserves: Reserves,
         *, compaction: bool = False) -> tuple[AgentRequest, Status]:
    """Answer the trailing tool group whole, in order, withholding any result that does not fit.

    A withheld result becomes a marker saying so, never a clipped excerpt. If
    even the markers do not fit, the group is refused as `fit` refuses.
    """
    results = tuple(results)
    capacity = _known(capacity)
    pending = _pending_calls(request)
    if [r.call_id for r in results] != pending:
        raise BrokenExchange(pending[0] if pending else results[0].call_id)
    admitted: list[ToolResult] = []
    withheld = 0
    for n, result in enumerate(results):
        # Room is kept for the markers of every result still to come.
        rest = [_withheld(r) for r in results[n + 1:]]
        trial = replace(request, history=(*request.history, *admitted, result, *rest),
                        max_output_tokens=output_cap(capacity, reserves))
        if _refusal(measure(trial, dialect, capacity, reserves), capacity, reserves, compaction) is None:
            admitted.append(result)
            continue
        withheld += 1
        admitted.append(_withheld(result))
    packed, status = fit(replace(request, history=(*request.history, *admitted)), dialect, capacity,
                         reserves, compaction=compaction)
    return packed, replace(status, withheld_results=withheld)


def _withheld(result: ToolResult) -> ToolResult:
    return ToolResult(result.call_id, json.dumps({
        "withheld": "exceeds_context", "bytes": len(result.content.encode("utf-8")), "coverage": "none",
    }))


def _pending_calls(request: AgentRequest) -> list[str]:
    """The trailing tool group's call ids not yet answered."""
    pending: list[str] = []
    for entry in request.history:
        if isinstance(entry, ToolResult) and pending and pending[0] == entry.call_id:
            pending.pop(0)
        elif isinstance(entry, ModelTurn):
            pending = [c.id for i in entry.items if isinstance(i, ToolGroup) for c in i.calls]
        elif isinstance(entry, User):
            pending = []
    return pending


def _refusal(status: Status, capacity: Capacity, reserves: Reserves, compaction: bool) -> Optional[str]:
    if capacity.max_reasoning_tokens is None:
        generated_fits = reserves.output_tokens + reserves.reasoning_tokens <= capacity.max_output_tokens
    else:
        generated_fits = (reserves.output_tokens <= capacity.max_output_tokens
                          and reserves.reasoning_tokens <= capacity.max_reasoning_tokens)
    if not generated_fits:
        return RESERVE_EXCEEDS_OUTPUT
    if reserves.total >= capacity.context_tokens:
        return RESERVE_EXCEEDS_CONTEXT
    if status.request_bytes > capacity.max_request_bytes:
        return COMPACTION_REQUIRED if compaction else REQUEST_BYTES_EXCEEDED
    if status.occupancy_tokens + reserves.total > capacity.context_tokens:
        return COMPACTION_REQUIRED if compaction else CONTEXT_EXHAUSTED
    return None


class FittedAgentProvider(LLMProvider):
    """Sends a request only once it fits the pinned model's verified capacity."""

    def __init__(self, provider: LLMProvider, reserves: Reserves, *, compaction: bool = False):
        self.provider = provider
        self.reserves = reserves
        #: Whether the caller can compact (IR-734); until then a full window refuses.
        self.compaction = compaction
        #: Recent statuses, newest last; bounded, and each is logged with its run.
        self.statuses: deque[Status] = deque(maxlen=64)

    @property
    def dialect(self):
        return self.provider.dialect

    @property
    def paid(self) -> bool:
        return getattr(self.provider, "paid", True)

    @property
    def admitted(self) -> bool:
        return getattr(self.provider, "admitted", False)

    def accepts(self, pin) -> bool:
        return self.provider.accepts(pin)

    def capacity(self, pin) -> Optional[Capacity]:
        return self.provider.capacity(pin)

    async def generate_response(self, prompt: str, context: str = "") -> str:
        raise UnsupportedCapability("generate_response")

    def pack(self, request, results) -> tuple[AgentRequest, Status]:
        """`pack` against the pinned model's capacity; the status is recorded."""
        return self._recorded(pack, request, results)

    async def converse(self, request):
        request, _ = self._recorded(fit, request)
        return await self.provider.converse(request)

    def _recorded(self, check, request, *args):
        try:
            fitted, status = check(request, *args, self.provider.dialect, self.provider.capacity(request.pin),
                                   self.reserves, compaction=self.compaction)
        except OverCapacity as refused:
            self._record(refused.status)
            raise
        self._record(status)
        return fitted, status

    def _record(self, status: Status) -> None:
        self.statuses.append(status)
        binding = scope.current()
        log.info("agent capacity run=%s %s", binding.run_id if binding else None, status.as_dict())
