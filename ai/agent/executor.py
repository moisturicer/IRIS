"""Investigate and answer in one pinned AGENT Conversation (IR-727, IR-728, IR-729, ADR-049 §13-16).

The same model turns search, read, plan and draft, keeping every exchange
in order. Bounds close research while the final answer and one repair still
fit; the final turn keeps the tools declared with `tool_choice: none`. Only
a checked, completed answer is delivered: a failing draft is repaired up to
twice in the same Conversation, and if it still fails the latest draft goes out
whole, minus citations that name no source. A changed source is never repaired
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

from ai.runs import stream
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
from ai.agent.prompts import (  # noqa: F401 -- re-exported: callers and pinned tests name them here
    CHAT_INSTRUCTIONS, CHAT_PROMPT_VERSION, CHAT_TOOL_VERSION, CITED_INSTRUCTIONS, CITED_NOTE, CITED_PROMPT_VERSION,
    CITED_TOOL_VERSION, COHERENT_INSTRUCTIONS, DELIMITED_INSTRUCTIONS, DELIMITED_PROMPT_VERSION,
    DELIMITED_TOOL_VERSION, COHERENT_PROMPT_VERSION,
    COHERENT_TOOL_VERSION, COMPACT_REQUEST, EARLIER_TURN, EVIDENCE_INSTRUCTIONS,
    EVIDENCE_PROMPT_VERSION, EVIDENCE_TOOL_VERSION, FINAL_NOTE, HYBRID_INSTRUCTIONS, HYBRID_PROMPT_VERSION,
    HYBRID_TOOL_VERSION, INSTRUCTIONS, LISTING_INSTRUCTIONS, LISTING_PROMPT_VERSION, LISTING_TOOL_VERSION,
    MANUSCRIPT_INSTRUCTIONS, MANUSCRIPT_PROMPT_VERSION, MANUSCRIPT_TOOL_VERSION, METADATA_INSTRUCTIONS,
    METADATA_PROMPT_VERSION, METADATA_TOOL_VERSION, PAPER_CHAT_PREFIX, PROMPT_VERSION, PROMPTS,
    RECOVERY_INSTRUCTIONS, RECOVERY_PROMPT_VERSION, RECOVERY_TOOL_VERSION, RESEARCH_INSTRUCTIONS,
    RESEARCH_PROMPT_VERSION, RESEARCH_TOOL_VERSION, SELECTION_INSTRUCTIONS, SELECTION_PREFIX,
    SELECTION_PROMPT_VERSION, SELECTION_TOOL_VERSION, SELECTION_WITHDRAWN, TOOL_VERSION, quoted, unquoted,
)
from ai.agent.tools import (
    ASK_CLARIFICATION, ENDS_RUN, OUTAGES, READ_MANUSCRIPT, TOOL_UNAVAILABLE, Investigation, RunEnded,
)
from ai.domain.ports import LLMProvider, ProviderRejected, TransientProviderError, UnsupportedCapability
from ai.research.tools import EARLIER_COMMITTED, OK
from ai.runs import config as runs_config
from ai.runs.executor import Compacted, Result, RunContext, Unavailable

log = logging.getLogger(__name__)

#: The one purpose every attempt of this responsibility records.
PURPOSE = "agent"
#: `_Run.outcome` when the history held nothing older than the exchanges kept.
NOTHING_TO_COMPACT = "nothing_to_compact"

RESEARCH_TOOL_VERSIONS = (RESEARCH_TOOL_VERSION, METADATA_TOOL_VERSION, MANUSCRIPT_TOOL_VERSION,
                          RECOVERY_TOOL_VERSION, HYBRID_TOOL_VERSION, LISTING_TOOL_VERSION,
                          CHAT_TOOL_VERSION, EVIDENCE_TOOL_VERSION, COHERENT_TOOL_VERSION, CITED_TOOL_VERSION,
                          DELIMITED_TOOL_VERSION, SELECTION_TOOL_VERSION)
#: Pins that offer research-7's tools and never mention an unseen draft in a repair (IR-1004, IR-1166, IR-1168).
EVIDENCE_TOOL_VERSIONS = (EVIDENCE_TOOL_VERSION, COHERENT_TOOL_VERSION, CITED_TOOL_VERSION,
                          DELIMITED_TOOL_VERSION, SELECTION_TOOL_VERSION)
#: Versions that number earlier Turns and list what they cited (IR-1168).
CITED_TOOL_VERSIONS = (CITED_TOOL_VERSION, DELIMITED_TOOL_VERSION, SELECTION_TOOL_VERSION)
#: Versions that quote paper text wherever it reaches the model (IR-1196).
DELIMITED_TOOL_VERSIONS = (DELIMITED_TOOL_VERSION, SELECTION_TOOL_VERSION)
#: Versions that may be sent a passage the reader selected (IR-581).
SELECTION_TOOL_VERSIONS = (SELECTION_TOOL_VERSION,)
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
                 compaction: Optional[Compaction] = None, checks: str = "enforce", tool_concurrency: int = 1):
        if type(tool_concurrency) is not int or tool_concurrency < 1:
            raise ValueError("tool_concurrency must be a positive integer")
        #: Read-only calls in one tool group fetched at once; 1 runs them one by one (IR-1003).
        self.tool_concurrency = tool_concurrency
        self.provider = provider
        #: "enforce" refuses, repairs or trims a draft that fails the checks. "flag" delivers it,
        #: dropping a citation that cannot be bound to a source and noting any number or title it
        #: could not match. "advisory" delivers it and only logs the findings.
        self.checks = checks
        self.enforce_checks = checks == "enforce"
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

    async def compact(self, tools, context: RunContext) -> Compacted:
        """Condense the Conversation on the reader's request: IR-734's summary and handoff, no answer (IR-754).

        The same checks as `answer`, because the same AGENT and admission pay
        for it, and one summary attempt at most. Anything short of a committed
        handoff is `unavailable` and leaves the preceding context as it was.
        """
        if not self.supported() or self.compaction is None or context.commit_handoff is None:
            raise Unavailable("unsupported_pin")
        if not self.admitted():
            raise Unavailable("not_admitted")
        if not self.researches:
            raise Unavailable("unsupported_pin")
        if self.price is None and getattr(self.provider, "paid", True):
            raise Unavailable("price_unknown")
        try:
            return await _Run(self, COMPACT_REQUEST, tools, context).compact()
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


def _carried(history) -> frozenset:
    """Every source any entry of `history` depends on."""
    return frozenset(s for entry in history for s in getattr(entry, "dependencies", ()))



class _Fetches:
    """A tool group's read-only fetches, started together and folded in call order (IR-1003).

    Each fetch runs under a shared cap. Its journal entry waits until every
    earlier call has committed, so the journal reads as a sequential run would.
    Fetches start only for calls a sequential run would reach: within the tool
    limit and before the first clarification. Fewer than two starts none.
    """

    def __init__(self, investigation, calls, *, cap: int, limit: int):
        self.committed = [asyncio.Event() for _ in calls]
        self.tasks: dict[int, asyncio.Task] = {}
        if cap < 2:
            return
        started = {}
        for n, call in enumerate(calls[:max(0, limit)]):
            if call.name == ASK_CLARIFICATION.name:
                break
            fetch = investigation.fetcher(call)
            if fetch is not None:
                started[n] = fetch
        if len(started) < 2:
            for fetch in started.values():
                fetch.close()
            return
        gate = asyncio.Semaphore(cap)
        # Created in call order, so an earlier fetch always takes a slot first.
        for n, fetch in started.items():
            self.tasks[n] = asyncio.create_task(self._run(n, fetch, gate))

    async def _run(self, n, fetch, gate):
        token = EARLIER_COMMITTED.set(self.committed[n - 1] if n else None)
        try:
            async with gate:
                return await fetch
        finally:
            EARLIER_COMMITTED.reset(token)
            self.committed[n].set()

    def take(self, n):
        return self.tasks.pop(n, None)

    def done(self, n) -> None:
        self.committed[n].set()

    def cancel(self) -> None:
        """Whatever the fold did not reach: a sequential run would never have made it."""
        for task in self.tasks.values():
            task.cancel()
        self.tasks.clear()


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
        #: research-8 and research-9 offer research-7's tools (IR-1004, IR-1166).
        tool_set = CHAT_TOOL_VERSION if version in EVIDENCE_TOOL_VERSIONS else version
        self.investigation = Investigation(
            tools, clarify=not asked,
            metadata=tool_set in (METADATA_TOOL_VERSION, MANUSCRIPT_TOOL_VERSION, RECOVERY_TOOL_VERSION,
                                HYBRID_TOOL_VERSION, LISTING_TOOL_VERSION, CHAT_TOOL_VERSION),
            manuscripts=tool_set in (MANUSCRIPT_TOOL_VERSION, RECOVERY_TOOL_VERSION, HYBRID_TOOL_VERSION,
                                   LISTING_TOOL_VERSION, CHAT_TOOL_VERSION),
            recovery=tool_set in (RECOVERY_TOOL_VERSION, HYBRID_TOOL_VERSION, LISTING_TOOL_VERSION,
                                CHAT_TOOL_VERSION),
            hybrid=tool_set in (HYBRID_TOOL_VERSION, LISTING_TOOL_VERSION, CHAT_TOOL_VERSION),
            listing=tool_set in (LISTING_TOOL_VERSION, CHAT_TOOL_VERSION))
        #: research-7 names a Paper Chat's paper and repairs a failing answer twice (IR-995).
        self.chat = tool_set == CHAT_TOOL_VERSION
        self.repairs = 2
        #: research-8 and later repairs never mention the unseen draft (IR-1004, IR-1166).
        self.fresh_repairs = version in EVIDENCE_TOOL_VERSIONS
        #: research-10 numbers earlier Turns and lists what they cited (IR-1168).
        self.cites = version in CITED_TOOL_VERSIONS
        #: research-11 and later quote paper text wherever it reaches the model (IR-1196).
        self.delimit = self.investigation.delimit = version in DELIMITED_TOOL_VERSIONS
        #: research-12 is told about a selected passage; no earlier pin ever is (IR-581).
        self.selects = version in SELECTION_TOOL_VERSIONS
        #: Each earlier answer sent with its citation list -> the same answer without it.
        self.unlisted: dict = {}
        self.prior = context.prior[-self.bounds.history_turns:] if self.bounds.history_turns else ()
        self.steps = 0
        #: Sources the history carried when the answer was written (IR-994).
        self.carried_sources: frozenset = frozenset()
        # Whatever an earlier fence spent stays spent, the attempt it left uncertain included (IR-724).
        spent = context.spent or {}
        self.budget.restore(spent.get("input_tokens", 0), spent.get("output_tokens", 0),
                            attempts=spent.get("attempts", 0))
        self.task = checkpoint.task_key(question, context.prior, context.state or {},
                                        handoff=(context.handoff or {}).get("revision"),
                                        selection=(context.selection.to_json() if context.selection
                                                   else {"withdrawn": True} if context.selection_withdrawn
                                                   else None))
        # The compact handoff the history now opens with, and the original Turns still carried whole (IR-734).
        self.handoff = (context.handoff or {}).get("body")
        self.handoff_revision = (context.handoff or {}).get("revision")
        self.handoff_through = int((context.handoff or {}).get("through_ordinal") or 0)
        self.carried = [t.ordinal for t in self.prior]
        # Every summary attempt counts, those of earlier fences included.
        self.compactions = context.compactions
        self.compact_failed_at: Optional[int] = None
        #: How the last compaction attempt ended: "compacted", `NOTHING_TO_COMPACT`, or the reason it was kept.
        self.outcome: Optional[str] = None
        self.revision: Optional[int] = None
        self.condensed = 0

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
            fetches = _Fetches(self.investigation, calls, cap=self.agent.tool_concurrency,
                               limit=self.bounds.max_tool_calls - self.investigation.tool_calls)
            try:
                for n, call in enumerate(calls):
                    if self.investigation.tool_calls >= self.bounds.max_tool_calls:
                        # The exchange stays whole; the call is answered, not run.
                        results.append(ToolResult(call.id, json.dumps({"error": "tool_limit"}),
                                                  control_only=True))
                        fetches.done(n)
                        continue
                    room = self._room(history, results, calls[n:]) if call.name == READ_MANUSCRIPT.name else 0
                    outcome = await self.investigation.execute(call, room=room, fetched=fetches.take(n))
                    fetches.done(n)
                    if outcome.clarification is not None:
                        self._checked(outcome.clarification, clarification=True)
                        self.carried_sources = _carried([*history, *results])
                        return self._result(outcome.clarification, (), kind="clarification")
                    progressed = progressed or outcome.progress
                    results.append(ToolResult(call.id, outcome.content, outcome.dependencies,
                                              outcome.control_only, outcome.metadata_only))
            finally:
                fetches.cancel()
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
        scope = getattr(self.tools, "scope", None) if self.chat else None
        asked = [*also, *([scope] if scope is not None else [])]
        # The same read gives every paper an earlier Turn cited a fresh handle, if still readable (IR-1168).
        cited = [rid for turn in self.prior for rid, _ in turn.cited] if self.cites else []
        shown = await self.investigation.recall(state, also=[*asked, *cited])
        if cited and not asked and not any(state.get(k) for k in ("shown", "selected", "excluded")):
            # Citations alone open no state message.
            shown = {}
        if scope is not None and not any(shown.get(k) for k in ("shown", "selected", "excluded")):
            # The scope read alone opens no state message.
            shown = {}
        if handoff:
            # Earlier Turns arrive compacted (IR-734).
            summary = compacting.render(handoff, self.investigation.papers, passages=False, delimit=self.delimit)
            history.append(summary)
        plain, earlier = self._earlier(listed=False), self._earlier(listed=True)
        self.unlisted = {e: p for e, p in zip(earlier, plain) if e != p}
        closing = self._closing(shown, scope)
        if self.unlisted and self._overflows([*history, *earlier, *closing]):
            # A history that would not fit loses the citation lists before any Turn (IR-1168).
            earlier, self.unlisted = plain, {}
        return [*history, *earlier, *closing]

    def _without_lists(self, history: list) -> list:
        return [self.unlisted.get(e, e) if isinstance(e, ModelTurn) else e for e in history]

    def _earlier(self, *, listed: bool) -> list:
        """The carried Turns; under research-10 numbered, and with what they cited when `listed` (IR-1168)."""
        history: list = []
        for turn in self.prior:
            answer, sources = DELIVERED_MARKER.sub("", turn.answer), frozenset(turn.sources)
            question = compacting.reader(turn.question)
            if self.cites and turn.ordinal is not None:
                question = EARLIER_TURN.format(n=turn.ordinal) + question
                note, papers = self._cited(turn) if listed else ("", frozenset())
                answer += note
                sources |= frozenset(s for s in self.investigation.recalled_sources if s.record_id in papers)
            history += [User(question), ModelTurn(items=(Text(answer),), stop=StopReason.END, dependencies=sources)]
        return history

    def _cited(self, turn) -> tuple[str, frozenset]:
        """The papers `turn` cited that the reader can still read, with their pages, and their Record ids."""
        pages: dict[int, set] = {}
        for rid, page in turn.cited:
            if rid in self.investigation.papers:
                pages.setdefault(rid, set()).update({page} if page else ())
        parts = []
        for rid, numbers in pages.items():
            handle, title = self.investigation.papers[rid]
            ordered = sorted(numbers)
            where = (f", page {ordered[0]}" if len(ordered) == 1
                     else f", pages {', '.join(map(str, ordered))}" if ordered else "")
            parts.append(f"«{title}» (paper {handle}){where}")
        return (CITED_NOTE + "; ".join(parts) + "." if parts else ""), frozenset(pages)

    def _unmarked(self, text: str) -> str:
        return unquoted(text) if self.delimit else text

    def _title(self, title: str) -> str:
        return quoted(title) if self.delimit else title

    def _overflows(self, history) -> bool:
        """Whether `history` would fill the window or start a compaction (IR-1168)."""
        try:
            _, status = self.agent.estimate(self.request(history))
        except Unavailable as full:
            return full.code in WINDOW_FULL
        rule = self.agent.compaction
        return (rule is not None and self.context.commit_handoff is not None
                and self.compactions < rule.max_attempts and status.occupancy_tokens >= rule.threshold_tokens)

    def _closing(self, shown: dict, scope) -> list:
        """The state message, the Paper Chat note and the reader's question, in that order."""
        history: list = []
        if shown:
            if self.delimit:
                shown = {**shown, "shown": [{**p, "title": self._title(p["title"])} for p in shown.get("shown", ())]}
            history.append(User(STATE_PREFIX + json.dumps(shown, ensure_ascii=False),
                                self.investigation.recalled_sources))
        if scope is not None and scope in self.investigation.papers:
            handle, title = self.investigation.papers[scope]
            note = User(PAPER_CHAT_PREFIX + json.dumps({"paper": handle, "title": self._title(title)},
                                                       ensure_ascii=False),
                        self.investigation.recalled_sources)
            history.append(note)
        history += self._selection(scope)
        # The reader's words, unchanged unless they would pass for derived context.
        history.append(User(compacting.reader(self.question)))
        return history


    def _selection(self, scope) -> list:
        """The passage the reader asked about, rechecked at this claim; or that it is gone (IR-581)."""
        chosen = self.context.selection
        if not self.selects:
            return []
        if chosen is None:
            return [User(SELECTION_WITHDRAWN)] if self.context.selection_withdrawn else []
        body = {"page": chosen.page, "quote": quoted(chosen.quote) if self.delimit else chosen.quote}
        if scope is not None and scope in self.investigation.papers:
            body = {"paper": self.investigation.papers[scope][0], **body}
        return [User(SELECTION_PREFIX + json.dumps(body, ensure_ascii=False), self.investigation.recalled_sources)]

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

    async def compact(self) -> Compacted:
        """A manual compaction: one summary attempt over this run's own allowance (IR-754)."""
        if self.context.committed:
            # An earlier fence committed it; finish rather than summarize, and spend, again.
            revision = max(self.context.committed)
            await self._journal("compaction", {"outcome": "compacted", "revision": revision,
                                               "turns": 0, "exchanges": 0})
            return Compacted(revision, 0, self.budget.reported)
        if self.compactions:
            # A summary was sent and nothing committed; it is not retried by another worker.
            raise Unavailable("attempts_exhausted")
        await self._compacted(await self._open(), forced=True)
        if self.outcome == "compacted":
            return Compacted(self.revision, self.condensed, self.budget.reported)
        if self.outcome == NOTHING_TO_COMPACT:
            await self._journal("compaction", {"outcome": "kept", "reason": NOTHING_TO_COMPACT})
            return Compacted(None, 0, self.budget.reported)
        raise Unavailable(self.outcome or "unavailable")

    async def _compacted(self, history: list, *, forced: bool = False) -> list:
        """`history` with its older exchanges compacted once it reaches the threshold (IR-734).

        Anything short of a complete, committed handoff -- a refused, empty or
        malformed summary, or a Conversation that moved -- leaves `history` as
        it was. Every attempt counts against the run's own bound, allowance
        and deadline; a failed one is not retried until the history grows.

        `forced` is the reader's request (IR-754): no threshold applies, and
        only the summary must be affordable, since no answer follows it.
        """
        rule = self.agent.compaction
        if rule is None or self.context.commit_handoff is None:
            return history
        if not forced and (self.compactions >= rule.max_attempts or self.compact_failed_at == len(history)):
            return history
        occupancy = self.agent.occupancy(self.request(history))
        if occupancy is None:
            return await self._compaction_failed(history, "capacity_unknown") if forced else history
        if not forced and occupancy < rule.threshold_tokens:
            return history
        if not forced and self.unlisted:
            # The citation lists go before any Turn is compacted (IR-1168).
            history, self.unlisted = self._without_lists(history), {}
            occupancy = self.agent.occupancy(self.request(history))
            if occupancy is not None and occupancy < rule.threshold_tokens:
                return history
        cut = compacting.split(history, rule.keep_exchanges)
        if cut is None:
            self.outcome = NOTHING_TO_COMPACT
            return history
        try:
            request, status = self.agent.estimate_summary(self.request(cut.summary(), closed=True))
        except Unavailable:
            return await self._compaction_failed(history, "summary_exceeds_context")
        planned = [(status.occupancy_tokens, request.max_output_tokens)]
        if not forced:
            # The summary must leave the final answer and its repair affordable at today's size.
            cap = output_cap(self.agent.sender.capacity(request.pin), self.agent.reserves)
            planned += [(occupancy, cap), (occupancy + cap + self.agent.reserves.repair_tokens, cap)]
        if not self.budget.fits(planned):
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
                   "excluded": self._focus("excluded")}, entries=cut.summary())
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
        self.outcome, self.revision, self.condensed = "compacted", revision, len(cut.gone_turns)
        await self._journal("compaction", {"outcome": "compacted", "revision": revision,
                                           "turns": len(cut.gone_turns), "exchanges": len(cut.gone_exchanges)})
        rebuilt = cut.rebuilt(compacting.render(body, self.investigation.papers, passages=True,
                                                  delimit=self.delimit))
        # What the compacted exchanges showed is no longer in front of the model (IR-736).
        self.investigation.reshown(e.content for e in rebuilt if isinstance(e, ToolResult))
        return rebuilt

    async def _compaction_failed(self, history: list, reason: str) -> list:
        self.compact_failed_at = len(history)
        self.outcome = reason
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
        sink = stream.active()
        if sink is not None:
            await sink.attempt(phase, live=not self.agent.enforce_checks)
        send = self.agent.summarize if phase == "compact" else self.agent.send
        try:
            # The run's deadline bounds every send, admitted or not.
            turn = await asyncio.wait_for(send(request), max(0.0, self.deadline - time.monotonic()))
        except asyncio.TimeoutError:
            raise Unavailable("deadline") from None
        if sink is not None:
            await sink.settle(turn.stop is not StopReason.TOOLS)
        self.steps += phase == "gather"
        self.budget.spend(turn, status.occupancy_tokens, request.max_output_tokens)
        return turn

    async def _deliver(self, turn: ModelTurn, history: list) -> Result:
        self.carried_sources = _carried(history)
        text = self._unmarked(_final(turn))
        found = self._findings(text)
        if not found:
            return await self._commit(text)
        if not self.agent.enforce_checks:
            # Advisory: the answer stands as written, minus citations that cannot be bound to a source.
            log.info("agent draft findings (delivered): %s", ",".join(sorted(found)))
            text = assurance.bindable(text, self.investigation, excluded=self._focus("excluded"))
            note = self._note(found) if self.agent.checks == "flag" else ""
            return await self._commit(f"{text}\n\n{note}" if note else text)
        log.info("agent draft refused: %s", ",".join(sorted(found)))
        # A source that changed since it was read fences delivery; it is never repaired around.
        await self._recheck(text)
        drafts = [text]
        for attempt in range(1, self.repairs + 1):
            repaired = await self._repair(history, found)
            if repaired is None:
                break
            text_now, history = repaired
            text_now = self._unmarked(text_now)
            drafts.insert(0, text_now)
            found = self._findings(text_now)
            if not found:
                return await self._commit(text_now)
            log.info("agent repair refused: %s", ",".join(sorted(found)))
        # Out of repairs: the latest draft is delivered whole, never trimmed or refused. Citations that bind
        # to no source are removed; a sentence still stating an unsupported number or title is marked as such.
        text = assurance.qualified(drafts[0], self.investigation, prior=self.prior,
                                   excluded=self._focus("excluded"))
        return await self._commit(text or assurance.UNESTABLISHED)

    def _note(self, found: dict) -> str:
        """The numbers and titles a delivered answer states that no passage supports, as one line."""
        # A whole number no larger than the papers read is a position in a list, not a claim.
        listed = len(self.investigation.papers)
        shown = {**found, "unsupported_number": [n for n in found.get("unsupported_number", [])
                                                 if not (n.isdigit() and 0 < int(n) <= listed)]}
        return assurance.unmatched_note(shown)

    async def _repair(self, history: list, found) -> Optional[tuple[str, list]]:
        """One more turn in the same Conversation and the history ending with it; None if it cannot."""
        if not self.agent.reserves.repair_tokens:
            return None
        # `history` already ends with the draft; the feedback follows it.
        history = [*history, User(assurance.feedback(found, unseen=self.fresh_repairs))]
        request, status = self.agent.estimate(self.request(history, closed=True))
        if not self.budget.fits([(status.occupancy_tokens, request.max_output_tokens)]):
            return None
        repaired = await self._attempt(request, status, "repair")
        try:
            return final_answer(repaired), [*history, repaired]
        except NotFinal:
            return None

    async def _commit(self, text: str) -> Result:
        await self._recheck(text)
        answer, citations = assurance.deliver(text, self.investigation)
        if self.investigation.outages:
            # Said by the application, not left to the model; it is part of the stored Turn (IR-731).
            answer = f"{answer}\n\n{assurance.outage_limitation(self.investigation.outages)}"
        sink = stream.active()
        if sink is not None and self.agent.enforce_checks:
            # The answer is only known once the checks are done, so it is shown now, whole, and typed out by the page.
            await sink.final(answer)
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
        """Logs what a clarification fails; a check never refuses an answer, only a changed source does."""
        failures = sorted(self._findings(text, clarification=clarification))
        if failures:
            log.info("agent draft findings (delivered): %s", ",".join(failures))

    def _result(self, answer: str, citations, *, kind: str = "answer") -> Result:
        previous = self.context.state or {}
        shown = list(dict.fromkeys(c.record_id for c in citations)) or list(previous.get("shown", ()))
        state = {"shown": shown[:STATE_PAPERS], "selected": self._focus("selected"),
                 "excluded": self._focus("excluded")}
        facts = assurance.facts(answer, citations, self.investigation) if kind == "answer" else ()
        return Result(answer=answer, citations=tuple(citations), reported_units=self.budget.reported,
                      kind=kind, state=state, facts=facts, sources=self.carried_sources)
