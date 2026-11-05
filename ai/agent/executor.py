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
from ai.agent import assurance, checkpoint, compaction as compacting
from ai.agent.budget import Bounds, Budget, profiles as checked_profiles
from ai.agent.compaction import STATE_PREFIX, Compaction, Handoff
from ai.agent.context import (
    CONTEXT_EXHAUSTED, REQUEST_BYTES_EXCEEDED, FittedAgentProvider, OverCapacity, Reserves, measure, output_cap,
)
from ai.agent.protocol import (
    AgentRequest, ModelTurn, NotFinal, Pin, StopReason, Text, ToolGroup, ToolResult, User, final_answer,
)
from ai.agent.tools import ENDS_RUN, OUTAGES, READ_MANUSCRIPT, TOOL_UNAVAILABLE, Investigation, RunEnded
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
#: research-3 plus recovery of original Turns after compaction (IR-735).
RECOVERY_PROMPT_VERSION = "agent-research-4"
RECOVERY_TOOL_VERSION = "research-4"
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
RECOVERY_INSTRUCTIONS = MANUSCRIPT_INSTRUCTIONS + (
    " Earlier Turns of a long conversation may arrive as a derived summary. A summary is not evidence and "
    "never a source for an exact value, quotation, page or number. When the reader asks for an exact "
    "detail from an earlier Turn, reread that Turn with recover_turn by its number, or read the paper "
    "again, and cite the passage handles it returns. If recovery is unavailable, say that you cannot "
    "confirm the detail."
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
    (RECOVERY_PROMPT_VERSION, RECOVERY_TOOL_VERSION): RECOVERY_INSTRUCTIONS,
}
RESEARCH_TOOL_VERSIONS = (RESEARCH_TOOL_VERSION, METADATA_TOOL_VERSION, MANUSCRIPT_TOOL_VERSION,
                          RECOVERY_TOOL_VERSION)
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
                 profiles: Optional[Mapping[str, Bounds]] = None, price: Optional[Price] = None,
                 compaction: Optional[Compaction] = None):
        self.provider = provider
        self.pin = pin
        self.reserves = reserves
        #: None never compacts: a full window then closes research, as before (IR-734).
        self.compaction = compaction
        self.summarizer = FittedAgentProvider(provider, compaction.summary_reserves(reserves)) if compaction else None
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
        if self.compaction and not self.compaction.fits(self.sender.capacity(self.pin), self.reserves):
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

    def occupancy(self, request: AgentRequest) -> Optional[int]:
        """The estimated occupancy of `request` whether or not it fits; None with capacity unknown."""
        capacity = self.sender.capacity(request.pin)
        if capacity is None:
            return None
        sized = replace(request, max_output_tokens=output_cap(capacity, self.reserves))
        return measure(sized, self.sender.dialect, capacity, self.reserves).occupancy_tokens

    def estimate_summary(self, request: AgentRequest):
        return _fitted(self.summarizer.estimate, request)

    async def summarize(self, request: AgentRequest) -> ModelTurn:
        """A compaction summary: the same AGENT and admission, its own completion cap (IR-734)."""
        return await self.send(request, sender=self.summarizer)

    async def send(self, request: AgentRequest, *, sender=None) -> ModelTurn:
        try:
            return await (sender or self.sender).converse(request)
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
            metadata=version in (METADATA_TOOL_VERSION, MANUSCRIPT_TOOL_VERSION, RECOVERY_TOOL_VERSION),
            manuscripts=version in (MANUSCRIPT_TOOL_VERSION, RECOVERY_TOOL_VERSION),
            recovery=version == RECOVERY_TOOL_VERSION)
        self.prior = context.prior[-self.bounds.history_turns:] if self.bounds.history_turns else ()
        self.steps = 0
        # Whatever an earlier fence spent stays spent, the attempt it left uncertain included (IR-724).
        spent = context.spent or {}
        self.budget.restore(spent.get("input_tokens", 0), spent.get("output_tokens", 0),
                            attempts=spent.get("attempts", 0))
        self.task = checkpoint.task_key(question, context.prior, context.state or {},
                                        handoff=(context.handoff or {}).get("revision"))
        # The compact handoff the history now opens with, and the original Turns still carried whole (IR-734).
        self.handoff = (context.handoff or {}).get("body")
        self.handoff_revision = (context.handoff or {}).get("revision")
        self.handoff_through = int((context.handoff or {}).get("through_ordinal") or 0)
        self.carried = [t.ordinal for t in self.prior]
        # Every summary attempt counts, those of earlier fences included.
        self.compactions = context.compactions
        self.compact_failed_at: Optional[int] = None

    def request(self, history, *, closed=False) -> AgentRequest:
        pin = self.agent.pin
        return AgentRequest(pin=pin, instructions=PROMPTS[(pin.prompt_version, pin.tool_version)],
                            history=tuple(history),
                            tools=self.investigation.specs(), tool_choice="none" if closed else "auto")

    async def run(self) -> Result:
        resumed = await self._resume()
        history, stale = resumed if resumed is not None else (await self._open(), 0)
        while self._may_gather(stale):
            history = await self._compacted(history)
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
                    self._checked(outcome.clarification, clarification=True)
                    return self._result(outcome.clarification, (), kind="clarification")
                progressed = progressed or outcome.progress
                results.append(ToolResult(call.id, outcome.content))
            packed, _ = self.agent.pack(self.request(history), results)
            history = list(packed.history)
            self.investigation.packed(history[len(history) - len(results):])
            stale = 0 if progressed else stale + 1
            await self._save(history, stale)

        history = await self._compacted(history)
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

    async def _open(self) -> list:
        history: list = []
        state = self.context.state or {}
        handoff = self.handoff
        if handoff and self.context.state is not None:
            # What is shown, selected and excluded now, not when the handoff was written.
            handoff = {**handoff, **{k: list(state.get(k, ())) for k in ("shown", "selected", "excluded")}}
        # One read gives the handoff's papers the same handles the state message uses.
        also = [*handoff["shown"], *handoff["selected"], *handoff["excluded"]] if handoff else ()
        shown = await self.investigation.recall(state, also=also)
        if handoff:
            # Earlier Turns arrive compacted (IR-734).
            history.append(compacting.render(handoff, self.investigation.papers, passages=False))
        for turn in self.prior:
            answer = DELIVERED_MARKER.sub("", turn.answer)
            history += [User(compacting.reader(turn.question)), ModelTurn(items=(Text(answer),), stop=StopReason.END)]
        if shown:
            history.append(User(STATE_PREFIX + json.dumps(shown, ensure_ascii=False)))
        # The reader's words, unchanged unless they would pass for derived context.
        history.append(User(compacting.reader(self.question)))
        return history

    async def _resume(self) -> Optional[tuple[list, int]]:
        """The Conversation an earlier fence completed, verified now; None to start afresh (IR-724).

        A step that no longer matches this run, or whose evidence the reader
        can no longer read as it was read, is rebuilt from the reader's
        question and the Conversation instead. Either way what was spent stays
        spent and the steps taken stay taken, so the bounds are not renewed.
        """
        saved = self.context.checkpoint
        if not saved:
            return None
        self.steps = max(self.steps, int(saved.get("step") or 0))
        restored = checkpoint.load(saved.get("body"), pin=self.agent.pin, bounds=self.bounds, task=self.task)
        # Opaque state may depend on the exact prefix and tool schemas, not only on the pin (ADR-049 §20).
        if restored is not None and restored.prefix != self._prefix():
            restored = None
        if restored is not None and not self._resumable(restored.compaction):
            restored = None
        reason = "incompatible" if restored is None else await self.tools.reauthorize(
            restored.handles(), restored.counted(), turns=restored.turns())
        if reason in ENDS_RUN:
            raise Unavailable(reason)
        if reason is not None:
            await self._journal("recovery", {"outcome": "rebuilt", "reason": reason, "step": self.steps})
            return None
        restored.apply(self.investigation)
        if restored.compaction:
            state = restored.compaction
            self.handoff, self.handoff_revision = state["body"], state["revision"]
            self.handoff_through, self.carried = int(state["through"]), list(state["carried"])
        self.steps = max(self.steps, restored.steps)
        spent = restored.budget
        self.budget.restore(spent["input"], spent["output"], spent["reported"], spent["attempts"])
        await self._journal("recovery", {"outcome": "resumed", "step": self.steps})
        return restored.history, restored.stale

    async def _compacted(self, history: list) -> list:
        """`history` with its older exchanges compacted once it reaches the threshold (IR-734).

        Anything short of a complete, committed handoff -- a refused, empty or
        malformed summary, or a Conversation that moved -- leaves `history` as
        it was. Every attempt counts against the run's own bound, allowance
        and deadline; a failed one is not retried until the history grows.
        """
        rule = self.agent.compaction
        if rule is None or self.context.commit_handoff is None:
            return history
        if self.compactions >= rule.max_attempts or self.compact_failed_at == len(history):
            return history
        occupancy = self.agent.occupancy(self.request(history))
        if occupancy is None or occupancy < rule.threshold_tokens:
            return history
        cut = compacting.split(history, rule.keep_exchanges)
        if cut is None:
            return history
        try:
            request, status = self.agent.estimate_summary(self.request(cut.summary(), closed=True))
        except Unavailable:
            return await self._compaction_failed(history, "summary_exceeds_context")
        # The summary must leave the final answer and its repair affordable at today's size.
        cap = output_cap(self.agent.sender.capacity(request.pin), self.agent.reserves)
        if not self.budget.fits([(status.occupancy_tokens, request.max_output_tokens), (occupancy, cap),
                                 (occupancy + cap + self.agent.reserves.repair_tokens, cap)]):
            return await self._compaction_failed(history, "allowance")
        self.compactions += 1
        turn = await self._attempt(request, status, "compact")
        try:
            summary = compacting.parse(final_answer(turn))
        except NotFinal:
            summary = None
        if summary is None:
            return await self._compaction_failed(history, "invalid_summary")
        compacted = [o for o in self.carried[:len(cut.gone_turns)] if o is not None]
        state = self.context.state or {}
        body = compacting.build(
            summary, previous=self.handoff, compacted=compacted, passages=self.investigation.passages,
            plan=self.investigation.plan,
            state={"shown": state.get("shown", ()), "selected": self._focus("selected"),
                   "excluded": self._focus("excluded")})
        through = max([self.handoff_through, *compacted])
        outcome, revision = await self.context.commit_handoff(Handoff(
            body=body, through_ordinal=through, turns=tuple(body["turns"]), sources=tuple(body["sources"]),
            binding=self.agent.pin.binding(),
            usage={"input_tokens": turn.input_tokens, "output_tokens": turn.output_tokens}))
        if outcome == "fenced":
            raise Unavailable("run_ended")
        if outcome != "committed":
            return await self._compaction_failed(history, outcome)
        self.handoff, self.handoff_revision = body, revision
        self.handoff_through = through
        self.carried = self.carried[len(cut.gone_turns):]
        await self._journal("compaction", {"outcome": "compacted", "revision": revision,
                                           "turns": len(cut.gone_turns), "exchanges": len(cut.gone_exchanges)})
        rebuilt = cut.rebuilt(compacting.render(body, self.investigation.papers, passages=True))
        # What the compacted exchanges showed is no longer in front of the model (IR-736).
        self.investigation.reshown(e.content for e in rebuilt if isinstance(e, ToolResult))
        return rebuilt

    async def _compaction_failed(self, history: list, reason: str) -> list:
        self.compact_failed_at = len(history)
        await self._journal("compaction", {"outcome": "kept", "reason": reason})
        return history

    def _resumable(self, compaction: Optional[dict]) -> bool:
        """A saved history opens only with a handoff that is committed and still this run's to use (IR-734)."""
        if not compaction:
            return self.handoff_revision is None
        if not (isinstance(compaction, dict) and compacting.well_formed(compaction.get("body"))
                and type(compaction.get("through")) is int and isinstance(compaction.get("carried"), list)):
            return False
        revision = compaction.get("revision")
        return revision in self.context.committed or revision == self.handoff_revision

    def _prefix(self) -> str:
        """The digest of the instructions and tool schemas every request of this run is sent under."""
        request = self.request(())
        return checkpoint.prefix_digest(request.instructions, request.tools)

    async def _save(self, history: list, stale: int) -> None:
        """Keep this completed step for a worker that takes the run over (IR-724)."""
        if self.context.save is None:
            return
        compaction = None if self.handoff is None else {
            "revision": self.handoff_revision, "through": self.handoff_through, "carried": self.carried,
            "body": self.handoff,
        }
        body = checkpoint.dump(pin=self.agent.pin, bounds=self.bounds, task=self.task, history=history,
                               investigation=self.investigation, budget=self.budget,
                               steps=self.steps, stale=stale, compaction=compaction, prefix=self._prefix())
        if not await self.context.save(self.steps, body):
            raise Unavailable("run_ended")

    async def _journal(self, name: str, data: dict) -> None:
        if not await self.tools.journal(name, data):
            raise Unavailable("run_ended")

    def _may_gather(self, stale: int) -> bool:
        return (self.steps < self.bounds.max_steps
                and self.investigation.tool_calls < self.bounds.max_tool_calls
                and stale < self.bounds.max_no_progress
                and self.deadline - time.monotonic() > self.bounds.final_seconds)

    async def _handoff_current(self) -> None:
        """A handoff in the history stands only while its Turns and sources are readable now (IR-735).

        Checked before every send and the commit, so revoked or replaced
        material cannot reach the model or the reader through a summary. The run
        stops safely rather than keep context it can no longer vouch for.
        """
        if self.handoff is None:
            return
        reason = await self.tools.handoff_current(self.handoff["turns"], self.handoff["sources"])
        if reason in ENDS_RUN:
            raise Unavailable(reason)
        if reason is not None:
            raise Unavailable("source_changed")

    async def _attempt(self, request: AgentRequest, status, phase: str) -> ModelTurn:
        await self._handoff_current()
        if not await self.tools.journal("context", {
            "used_tokens": status.occupancy_tokens, "capacity_tokens": status.context_tokens,
        }):
            raise Unavailable("run_ended")
        # Recorded before sending; a stopped run admits no further attempt.
        if not await self.tools.journal("model", {"purpose": PURPOSE, "phase": phase, "step": self.steps + 1}):
            raise Unavailable("run_ended")
        send = self.agent.summarize if phase == "compact" else self.agent.send
        try:
            # The run's deadline bounds every send, admitted or not.
            turn = await asyncio.wait_for(send(request), max(0.0, self.deadline - time.monotonic()))
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
        if self.investigation.outages:
            # Said by the application, not left to the model; it is part of the stored Turn (IR-731).
            answer = f"{answer}\n\n{assurance.outage_limitation(self.investigation.outages)}"
        return self._result(answer, citations)

    async def _recheck(self, text: str) -> None:
        try:
            await self._handoff_current()
            await self._recheck_sources(text)
        except OUTAGES as failure:
            # A source that cannot be reached cannot be vouched for; nothing is delivered (IR-731).
            log.warning("agent recheck failed: %s", type(failure).__name__)
            raise Unavailable(TOOL_UNAVAILABLE) from None

    async def _recheck_sources(self, text: str) -> None:
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

    def _findings(self, text: str, *, clarification: bool = False) -> dict:
        return assurance.findings(text, self.investigation, prior=self.prior, excluded=self._focus("excluded"),
                                  clarification=clarification)

    def _checked(self, text: str, *, clarification: bool = False) -> None:
        """A clarification or a salvaged answer that fails a check is never delivered."""
        failures = sorted(self._findings(text, clarification=clarification))
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
