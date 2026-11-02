"""Investigate and answer in one pinned AGENT Conversation (IR-727, IR-728, ADR-049 §13-16).

The same model turns search, read, plan and draft, keeping every exchange
in order. Bounds close research while the final answer and one repair still
fit; the final turn keeps the tools declared with `tool_choice: none`. Only
a checked, completed answer is delivered. The pin is checked against what
this code and the provider support before anything is sent; a mismatch is
`unavailable`, never a substitute model or dialect.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Mapping, Optional

from ai.admission.errors import AdmissionDenied
from ai.admission.limits import Price
from ai.agent import assurance
from ai.agent.budget import Bounds, Budget, profiles as checked_profiles
from ai.agent.context import FittedAgentProvider, OverCapacity, Reserves
from ai.agent.protocol import (
    AgentRequest, ModelTurn, NotFinal, Pin, StopReason, Text, ToolGroup, ToolResult, User, final_answer,
)
from ai.agent.tools import ENDS_RUN, Investigation, RunEnded
from ai.domain.ports import LLMProvider, TransientProviderError, UnsupportedCapability
from ai.research.tools import OK
from ai.runs import config as runs_config
from ai.runs.executor import Result, RunContext, Unavailable

log = logging.getLogger(__name__)

PROMPT_VERSION = "agent-direct-1"
TOOL_VERSION = "none-1"
RESEARCH_PROMPT_VERSION = "agent-research-1"
RESEARCH_TOOL_VERSION = "research-1"
#: The one purpose every attempt of this responsibility records.
PURPOSE = "agent"

INSTRUCTIONS = (
    "You are the IRIS research assistant. Answer the reader's question directly. "
    "Say plainly when general background is not a finding from the repository."
)
RESEARCH_INSTRUCTIONS = (
    "You are the IRIS research assistant for CIT-U's repository. Answer the reader's question. "
    "Use the tools to search and read papers when the question needs repository evidence; answer "
    "simple or general questions directly and say plainly that general background is not a finding "
    "from the repository. Cite every repository finding with its passage handle in square brackets, "
    "for example [P0123456789abcdef0123]; use no other brackets. Mark paper titles as «title». "
    "Compare methods and results only under comparable conditions, and report disagreements between "
    "papers rather than flattening them. A search returns a sample of matching passages, never the "
    "whole repository. For complex research keep a short task list with update_plan. When the reader "
    "picks or rules out papers, record it with update_focus. A conversation state message lists the "
    "papers already shown, in order; resolve references such as 'the second one' against it. Ask a "
    "clarifying question only when ambiguity blocks useful research."
)
FINAL_NOTE = (
    "Research is now closed. Answer the original question from what you have read, citing passages "
    "by handle, and say plainly what you could not find or read."
)

#: (prompt, tool) versions this code implements; a run pinned to any other is refused.
PROMPTS = {
    (PROMPT_VERSION, TOOL_VERSION): INSTRUCTIONS,
    (RESEARCH_PROMPT_VERSION, RESEARCH_TOOL_VERSION): RESEARCH_INSTRUCTIONS,
}
SUPPORTED = {"public_version": runs_config.PROTOCOL, "state_version": runs_config.SCHEMA}
STATE_PAPERS = 50
#: A delivered Turn's renumbered markers, kept out of the history so the model cannot copy them.
DELIVERED_MARKER = re.compile(r"\s*\[\d+\]")


class AgentExecutor:
    name = "agent"
    version = "1"
    reserved_units = 0
    #: The run service passes a `RunContext` (IR-728).
    takes_context = True

    def __init__(self, provider: LLMProvider, pin: Pin, reserves: Reserves, *,
                 profiles: Optional[Mapping[str, Bounds]] = None, price: Optional[Price] = None):
        self.provider = provider
        self.pin = pin
        self.reserves = reserves
        #: Research needs configured bounds per depth; none are defaulted.
        self.profiles = checked_profiles(profiles) if profiles is not None else None
        #: The pinned model's price; a paid provider without one cannot bound cost.
        self.price = price
        #: Every request is fitted to the pinned model's verified capacity (IR-732).
        self.sender = FittedAgentProvider(provider, reserves)

    @property
    def capacity_status(self):
        """The last request's capacity status, or None before any."""
        return self.sender.statuses[-1] if self.sender.statuses else None

    @property
    def researches(self) -> bool:
        return self.pin.tool_version == RESEARCH_TOOL_VERSION

    def supported(self) -> bool:
        if (self.pin.prompt_version, self.pin.tool_version) not in PROMPTS:
            return False
        if self.researches and self.profiles is None:
            return False
        return (all(getattr(self.pin, k) == v for k, v in SUPPORTED.items())
                and self.provider.accepts(self.pin))

    def admitted(self) -> bool:
        """A provider that may bill is reached only through admission (IR-725)."""
        return getattr(self.provider, "admitted", False) or not getattr(self.provider, "paid", True)

    async def answer(self, question: str, tools=None, context: Optional[RunContext] = None) -> Result:
        if not self.supported():
            raise Unavailable("unsupported_pin")
        if not self.admitted():
            raise Unavailable("not_admitted")
        if not self.researches:
            return await self._direct(question)
        if tools is None or context is None:
            raise Unavailable("unsupported_pin")
        if self.price is None and getattr(self.provider, "paid", True):
            raise Unavailable("price_unknown")
        try:
            return await _Run(self, question, tools, context).run()
        except RunEnded as ended:
            raise Unavailable(ended.reason) from None

    async def _direct(self, question: str) -> Result:
        request = AgentRequest(pin=self.pin, instructions=INSTRUCTIONS, history=(User(question),))
        turn = await self.send(request)
        text = _final(turn)
        return Result(answer=text, reported_units=(turn.input_tokens or 0) + (turn.output_tokens or 0))

    def estimate(self, request: AgentRequest):
        return _fitted(self.sender.estimate, request)

    def pack(self, request: AgentRequest, results):
        return _fitted(self.sender.pack, request, results)

    async def send(self, request: AgentRequest) -> ModelTurn:
        try:
            return await self.sender.converse(request)
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


def _fitted(check, *args):
    try:
        return check(*args)
    except OverCapacity as refused:
        raise Unavailable(refused.code) from None


def _final(turn: ModelTurn) -> str:
    try:
        return final_answer(turn)
    except NotFinal as refused:
        raise Unavailable(refused.code) from None


class _Run:
    """One run's investigation; nothing here outlives it."""

    def __init__(self, agent: AgentExecutor, question: str, tools, context: RunContext):
        self.agent = agent
        self.question = question
        self.tools = tools
        self.context = context
        self.bounds = agent.profiles[context.depth]
        self.budget = Budget(context.allowance, agent.price)
        self.deadline = time.monotonic() + context.remaining_seconds
        # One clarification at a time: not twice in a row, however much history is carried.
        asked = bool(context.prior) and context.prior[-1].kind == "clarification"
        self.investigation = Investigation(tools, clarify=not asked)
        self.prior = context.prior[-self.bounds.history_turns:] if self.bounds.history_turns else ()
        self.steps = 0

    def request(self, history, *, closed=False) -> AgentRequest:
        return AgentRequest(pin=self.agent.pin, instructions=RESEARCH_INSTRUCTIONS, history=tuple(history),
                            tools=self.investigation.specs(), tool_choice="none" if closed else "auto")

    async def run(self) -> Result:
        history: list = []
        for turn in self.prior:
            answer = DELIVERED_MARKER.sub("", turn.answer)
            history += [User(turn.question), ModelTurn(items=(Text(answer),), stop=StopReason.END)]
        shown = await self.investigation.recall(self.context.state or {})
        if shown:
            history.append(User("[IRIS conversation state] " + json.dumps(shown, ensure_ascii=False)))
        # The reader's words, unchanged, whatever queries the agent forms.
        history.append(User(self.question))

        stale = 0
        while self._may_gather(stale):
            request, status = self.agent.estimate(self.request(history))
            if not self.budget.can_gather(status.occupancy_tokens, request.max_output_tokens, self.agent.reserves):
                break
            turn = await self._attempt(request, status, "gather")
            history.append(turn)
            if turn.stop is not StopReason.TOOLS:
                # Only a turn that ended on its calls has them run; a truncated one is refused whole.
                return await self._deliver(turn)
            calls = [c for item in turn.items if isinstance(item, ToolGroup) for c in item.calls]
            results = []
            progressed = False
            for call in calls:
                if self.investigation.tool_calls >= self.bounds.max_tool_calls:
                    # The exchange stays whole; the call is answered, not run.
                    results.append(ToolResult(call.id, json.dumps({"error": "tool_limit"})))
                    continue
                outcome = await self.investigation.execute(call)
                if outcome.clarification is not None:
                    self._checked(outcome.clarification)
                    return self._result(outcome.clarification, (), kind="clarification")
                progressed = progressed or outcome.progress
                results.append(ToolResult(call.id, outcome.content))
            packed, _ = self.agent.pack(self.request(history), results)
            history = list(packed.history)
            stale = 0 if progressed else stale + 1

        if self.steps:
            history.append(User(FINAL_NOTE))
        request, status = self.agent.estimate(self.request(history, closed=True))
        if not self.budget.can_finish(status.occupancy_tokens, request.max_output_tokens, self.agent.reserves):
            raise Unavailable("allowance_exhausted")
        return await self._deliver(await self._attempt(request, status, "final"))

    def _may_gather(self, stale: int) -> bool:
        return (self.steps < self.bounds.max_steps
                and self.investigation.tool_calls < self.bounds.max_tool_calls
                and stale < self.bounds.max_no_progress
                and self.deadline - time.monotonic() > self.bounds.final_seconds)

    async def _attempt(self, request: AgentRequest, status, phase: str) -> ModelTurn:
        # Recorded before sending; a stopped run admits no further attempt.
        if not await self.tools.journal("model", {"purpose": PURPOSE, "phase": phase, "step": self.steps + 1}):
            raise Unavailable("run_ended")
        try:
            # The run's deadline bounds every send, admitted or not.
            turn = await asyncio.wait_for(self.agent.send(request), max(0.0, self.deadline - time.monotonic()))
        except asyncio.TimeoutError:
            raise Unavailable("deadline") from None
        self.steps += phase == "gather"
        self.budget.spend(turn, status.occupancy_tokens, request.max_output_tokens)
        return turn

    async def _deliver(self, turn: ModelTurn) -> Result:
        text = _final(turn)
        self._checked(text)
        for handle in assurance.cited(text):
            # Each cited source is still readable and unreplaced just before commit.
            now = await self.tools.open_passage(handle)
            if now.reason in ENDS_RUN:
                raise Unavailable(now.reason)
            before = self.investigation.passages[handle]
            if now.status != OK or not now.passages or now.passages[0].source != before.source:
                raise Unavailable("source_changed")
        answer, citations = assurance.deliver(text, self.investigation)
        return self._result(answer, citations)

    def _focus(self, name: str) -> list[int]:
        chosen = getattr(self.investigation, name)
        return list(chosen if chosen is not None else (self.context.state or {}).get(name, ()))

    def _checked(self, text: str) -> None:
        failures = assurance.check(text, self.investigation, prior=self.prior,
                                   excluded=self._focus("excluded"))
        if failures:
            # IR-729 repairs in the same Conversation; until then nothing unchecked is delivered.
            log.info("agent draft refused: %s", ",".join(failures))
            raise Unavailable("invalid_draft")

    def _result(self, answer: str, citations, *, kind: str = "answer") -> Result:
        previous = self.context.state or {}
        shown = list(dict.fromkeys(c.record_id for c in citations)) or list(previous.get("shown", ()))
        state = {"shown": shown[:STATE_PAPERS], "selected": self._focus("selected"),
                 "excluded": self._focus("excluded")}
        return Result(answer=answer, citations=tuple(citations), reported_units=self.budget.reported,
                      kind=kind, state=state)
