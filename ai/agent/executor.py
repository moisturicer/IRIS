"""Investigate and answer in one pinned AGENT Conversation (IR-727, IR-728, IR-729, ADR-049 §13-16).

The same model turns search, read, plan and draft, keeping every exchange
in order. Bounds close research while the final answer and one repair still
fit; the final turn keeps the tools declared with `tool_choice: none`. Only
a checked, completed answer is delivered: a failing draft is repaired once in
the same Conversation, and a failing repair keeps only what each sentence's
own citations support, or nothing. A changed source is never repaired
around; it fences delivery. The pin is checked against what
this code and the provider support before anything is sent; a mismatch is
`unavailable`, never a substitute model or dialect.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import replace
from typing import Mapping, Optional

from ai.admission.errors import AdmissionDenied
from ai.admission.limits import Price
from ai.agent import assurance
from ai.agent.budget import Bounds, Budget, profiles as checked_profiles
from ai.agent.context import (
    CONTEXT_EXHAUSTED, REQUEST_BYTES_EXCEEDED, FittedAgentProvider, OverCapacity, Reserves, measure, output_cap,
)
from ai.agent.protocol import (
    AgentRequest, ModelTurn, NotFinal, Pin, StopReason, Text, ToolGroup, ToolResult, User, final_answer,
)
from ai.agent.tools import ENDS_RUN, READ_MANUSCRIPT, Investigation, RunEnded
from ai.domain.ports import LLMProvider, ProviderRejected, TransientProviderError, UnsupportedCapability
from ai.research.tools import OK
from ai.runs import config as runs_config
from ai.runs.executor import Result, RunContext, Unavailable

log = logging.getLogger(__name__)

PROMPT_VERSION = "agent-direct-1"
TOOL_VERSION = "none-1"
RESEARCH_PROMPT_VERSION = "agent-research-1"
RESEARCH_TOOL_VERSION = "research-1"
#: research-1 plus named papers and exact counts (IR-750); a research-1 run keeps its tool set.
METADATA_PROMPT_VERSION = "agent-research-2"
METADATA_TOOL_VERSION = "research-2"
#: research-2 plus whole-Manuscript reading (IR-733).
MANUSCRIPT_PROMPT_VERSION = "agent-research-3"
MANUSCRIPT_TOOL_VERSION = "research-3"
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
METADATA_INSTRUCTIONS = RESEARCH_INSTRUCTIONS + (
    " When the reader names a paper, find it with resolve_papers; when several papers match, ask "
    "which one they mean. For how many papers match an Area, PSCED area, record type, years or IP "
    "flag, use count_records: its total is exact over the papers this reader can see, so say it is "
    "of the records they can see. Never present the number of papers a search found as a total."
)
MANUSCRIPT_INSTRUCTIONS = METADATA_INSTRUCTIONS + (
    " To answer from a whole paper, including its middle and late sections, read it with "
    "read_manuscript: it returns the extracted text in document order as far as it fits and says which "
    "passages and pages it did not return; pass its continue_after handle to read on. Say plainly "
    "which parts you did not read, that figures and formulas were not interpreted, and that reading "
    "one paper is not a search of the repository."
)
FINAL_NOTE = (
    "Research is now closed. Answer the original question from what you have read, citing passages "
    "by handle, and say plainly what you could not find or read."
)

#: (prompt, tool) versions this code implements; a run pinned to any other is refused.
PROMPTS = {
    (PROMPT_VERSION, TOOL_VERSION): INSTRUCTIONS,
    (RESEARCH_PROMPT_VERSION, RESEARCH_TOOL_VERSION): RESEARCH_INSTRUCTIONS,
    (METADATA_PROMPT_VERSION, METADATA_TOOL_VERSION): METADATA_INSTRUCTIONS,
    (MANUSCRIPT_PROMPT_VERSION, MANUSCRIPT_TOOL_VERSION): MANUSCRIPT_INSTRUCTIONS,
}
RESEARCH_TOOL_VERSIONS = (RESEARCH_TOOL_VERSION, METADATA_TOOL_VERSION, MANUSCRIPT_TOOL_VERSION)
#: Of the bytes a read may fill, the share kept for JSON escaping of its text.
ESCAPE_SHARE = 0.9
#: Over-capacity codes that close research rather than end the run; the final answer must still fit.
WINDOW_FULL = (CONTEXT_EXHAUSTED, REQUEST_BYTES_EXCEEDED)
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
        return self.pin.tool_version in RESEARCH_TOOL_VERSIONS

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

    def room(self, request: AgentRequest, budget: Budget) -> int:
        """Bytes one more tool result may add to `request` (IR-733).

        It must leave every reserve free in the model's verified capacity, plus one
        more gathering exchange (its turn and its results' markers), and the final
        answer and one repair must still fit the run allowance with it carried.
        """
        capacity = self.sender.capacity(request.pin)
        if capacity is None:
            return 0
        cap = output_cap(capacity, self.reserves)
        status = measure(replace(request, max_output_tokens=cap), self.sender.dialect, capacity, self.reserves)
        exchange = self.reserves.output_tokens + self.reserves.next_result_tokens
        tokens = capacity.context_tokens - status.occupancy_tokens - self.reserves.total - exchange
        low, high = 0, max(0, tokens)
        while low < high:
            mid = (low + high + 1) // 2
            if budget.can_finish(status.occupancy_tokens + mid, cap, self.reserves):
                low = mid
            else:
                high = mid - 1
        room = min(low * capacity.min_bytes_per_token, capacity.max_request_bytes - status.request_bytes)
        return max(0, int(room * ESCAPE_SHARE))

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
        except ProviderRejected:
            raise Unavailable("provider_rejected") from None


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
        # The run's own pinned bounds when it has them, never this worker's (IR-862).
        self.bounds = context.bounds or agent.profiles[context.depth]
        self.budget = Budget(context.allowance, agent.price)
        self.deadline = time.monotonic() + context.remaining_seconds
        # One clarification at a time: not twice in a row, however much history is carried.
        asked = bool(context.prior) and context.prior[-1].kind == "clarification"
        version = agent.pin.tool_version
        self.investigation = Investigation(
            tools, clarify=not asked,
            metadata=version in (METADATA_TOOL_VERSION, MANUSCRIPT_TOOL_VERSION),
            manuscripts=version == MANUSCRIPT_TOOL_VERSION)
        self.prior = context.prior[-self.bounds.history_turns:] if self.bounds.history_turns else ()
        self.steps = 0

    def request(self, history, *, closed=False) -> AgentRequest:
        pin = self.agent.pin
        return AgentRequest(pin=pin, instructions=PROMPTS[(pin.prompt_version, pin.tool_version)],
                            history=tuple(history),
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
            try:
                request, status = self.agent.estimate(self.request(history))
            except Unavailable as full:
                # A window filled by what was read closes research; the answer is still owed (IR-733).
                if full.code not in WINDOW_FULL:
                    raise
                break
            # Another exchange must leave room to close research and answer; otherwise answer now.
            if self.steps and not self._room(history, [], []):
                break
            if not self.budget.can_gather(status.occupancy_tokens, request.max_output_tokens, self.agent.reserves):
                break
            turn = await self._attempt(request, status, "gather")
            history.append(turn)
            if turn.stop is not StopReason.TOOLS:
                # Only a turn that ended on its calls has them run; a truncated one is refused whole.
                return await self._deliver(turn, history)
            calls = [c for item in turn.items if isinstance(item, ToolGroup) for c in item.calls]
            results = []
            progressed = False
            for n, call in enumerate(calls):
                if self.investigation.tool_calls >= self.bounds.max_tool_calls:
                    # The exchange stays whole; the call is answered, not run.
                    results.append(ToolResult(call.id, json.dumps({"error": "tool_limit"})))
                    continue
                room = self._room(history, results, calls[n:]) if call.name == READ_MANUSCRIPT.name else 0
                outcome = await self.investigation.execute(call, room=room)
                if outcome.clarification is not None:
                    self._checked(outcome.clarification)
                    return self._result(outcome.clarification, (), kind="clarification")
                progressed = progressed or outcome.progress
                results.append(ToolResult(call.id, outcome.content))
            packed, _ = self.agent.pack(self.request(history), results)
            history = list(packed.history)
            self.investigation.packed(history[len(history) - len(results):])
            stale = 0 if progressed else stale + 1

        if self.steps:
            history.append(User(FINAL_NOTE))
        request, status = self.agent.estimate(self.request(history, closed=True))
        if not self.budget.can_finish(status.occupancy_tokens, request.max_output_tokens, self.agent.reserves):
            raise Unavailable("allowance_exhausted")
        turn = await self._attempt(request, status, "final")
        history.append(turn)
        return await self._deliver(turn, history)

    def _room(self, history, results, unanswered) -> int:
        """What a read may return now, leaving room to close research and answer.

        Measured after the results so far, with every later call answered and the
        closing note sent, so a read never leaves the final request over capacity.
        """
        rest = [ToolResult(c.id, "{}") for c in unanswered]
        closing = self.request([*history, *results, *rest, User(FINAL_NOTE)], closed=True)
        return self.agent.room(closing, self.budget)

    def _may_gather(self, stale: int) -> bool:
        return (self.steps < self.bounds.max_steps
                and self.investigation.tool_calls < self.bounds.max_tool_calls
                and stale < self.bounds.max_no_progress
                and self.deadline - time.monotonic() > self.bounds.final_seconds)

    async def _attempt(self, request: AgentRequest, status, phase: str) -> ModelTurn:
        if not await self.tools.journal("context", {
            "used_tokens": status.occupancy_tokens, "capacity_tokens": status.context_tokens,
        }):
            raise Unavailable("run_ended")
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

    async def _deliver(self, turn: ModelTurn, history: list) -> Result:
        text = _final(turn)
        found = self._findings(text)
        if not found:
            return await self._commit(text)
        log.info("agent draft refused: %s", ",".join(sorted(found)))
        # A source that changed since it was read fences delivery; it is never repaired around.
        await self._recheck(text)
        repaired = await self._repair(history, found)
        if repaired is not None:
            again = self._findings(repaired)
            if not again:
                return await self._commit(repaired)
            log.info("agent repair refused: %s", ",".join(sorted(again)))
        # No second repair: what each sentence supports on its own is kept, and the gap is said.
        for draft in (repaired, text):
            kept = draft and assurance.supported_units(
                draft, self.investigation, prior=self.prior, excluded=self._focus("excluded"))
            if kept:
                partial = f"{kept}\n\n{assurance.LIMITATION}"
                self._checked(partial)
                return await self._commit(partial)
        raise Unavailable("invalid_draft")

    async def _repair(self, history: list, found) -> Optional[str]:
        """One more turn in the same Conversation, inside the reserve held for it; None if it cannot."""
        if not self.agent.reserves.repair_tokens:
            return None
        # `history` already ends with the draft; the feedback follows it.
        history = [*history, User(assurance.feedback(found))]
        request, status = self.agent.estimate(self.request(history, closed=True))
        if not self.budget.fits([(status.occupancy_tokens, request.max_output_tokens)]):
            return None
        repaired = await self._attempt(request, status, "repair")
        try:
            return final_answer(repaired)
        except NotFinal:
            return None

    async def _commit(self, text: str) -> Result:
        await self._recheck(text)
        answer, citations = assurance.deliver(text, self.investigation)
        return self._result(answer, citations)

    async def _recheck(self, text: str) -> None:
        # A handle this run was never shown has no source to recheck; the checks refuse it.
        for handle in (h for h in assurance.cited(text) if h in self.investigation.passages):
            # Each cited source is still readable and unreplaced just before commit.
            now = await self.tools.open_passage(handle)
            if now.reason in ENDS_RUN:
                raise Unavailable(now.reason)
            before = self.investigation.passages[handle]
            if now.status != OK or not now.passages or now.passages[0].source != before.source:
                raise Unavailable("source_changed")
        # Each stated count is recomputed under current policy; a population that moved fences it (IR-750).
        for fact in assurance.stated_counts(text, self.investigation):
            now = await self.tools.count(dict(fact.filters), fact.group_by)
            if now.reason in ENDS_RUN:
                raise Unavailable(now.reason)
            if now.count is None or now.count != fact:
                raise Unavailable("source_changed")

    def _focus(self, name: str) -> list[int]:
        chosen = getattr(self.investigation, name)
        return list(chosen if chosen is not None else (self.context.state or {}).get(name, ()))

    def _findings(self, text: str) -> dict:
        return assurance.findings(text, self.investigation, prior=self.prior, excluded=self._focus("excluded"))

    def _checked(self, text: str) -> None:
        """A clarification or a salvaged answer that fails a check is never delivered."""
        failures = sorted(self._findings(text))
        if failures:
            log.info("agent draft refused: %s", ",".join(failures))
            raise Unavailable("invalid_draft")

    def _result(self, answer: str, citations, *, kind: str = "answer") -> Result:
        previous = self.context.state or {}
        shown = list(dict.fromkeys(c.record_id for c in citations)) or list(previous.get("shown", ()))
        state = {"shown": shown[:STATE_PAPERS], "selected": self._focus("selected"),
                 "excluded": self._focus("excluded")}
        facts = assurance.facts(answer, citations, self.investigation) if kind == "answer" else ()
        return Result(answer=answer, citations=tuple(citations), reported_units=self.budget.reported,
                      kind=kind, state=state, facts=facts)
