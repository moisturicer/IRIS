"""The bounded conversational controller (IR-593, ADR-042, spec Â§2, Â§7).

PLAN chooses tool calls, a clarification or ready-to-compose; only the
application runs tools, through the general registry; ANSWER writes prose.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field, replace
from typing import Optional

from django.conf import settings

from apps.ai.admission import scope as admission_scope
from apps.ai.answers.citations import GroundedAnswer, UNAVAILABLE
from apps.ai.answers.events import RetrievalStarted
from apps.ai.answers.service import UNAVAILABLE_TEXT
from apps.ai.conversation_state import ContextState, committed_state
from apps.ai.history import estimate_tokens
from apps.ai.inference import InferenceTask
from apps.ai.models import DocumentChunk
from apps.ai.providers.deadline import bounded, model_call_deadline
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.providers.tool_calling import (
    AssistantMessage, SystemMessage, ToolCallingLLM, ToolResultMessage, UserMessage,
)
from apps.ai.research.audit import RunAudit, Step, argument_digest
from apps.ai.research.budget import BudgetExhausted
from apps.ai.research.context import RunContext
from apps.ai.research.prompts import conversation_state, planner_history
from apps.ai.research.registry import ToolRun, general_tools
from apps.ai.research.results import Status, ToolStatus, population_snapshot
from apps.ai.research.synthesis import LedgerRetriever
from apps.ai.research.tools.common import disclosable, visible_record_ids
from apps.ai.resilience.circuit import CircuitOpen

from . import prompts
from .budget import ControllerBudget, NotConfigured
from .compose import CLARIFY, EVIDENCE, AnswerComposer, ReadyToCompose
from .versions import CONTROLLER_ENGINE, pin

logger = logging.getLogger(__name__)

#: Reads that may run side by side under the same scope (spec Â§7).
READS = frozenset({"read_papers", "extract_evidence"})
#: Envelope codes that mean the model sent a call it could not have sent.
_MALFORMED = frozenset({"invalid_arguments", "unknown_tool", "invalid_reference"})
_CORRECTION = json.dumps({"status": "unavailable", "limitations": ["malformed_call"]})


@dataclass(frozen=True)
class Outcome:
    """The controller's result: the composed answer and the state it leaves."""

    answer: GroundedAnswer
    stop_reason: str
    context: Optional[ContextState] = None
    research_run_id: Optional[str] = None


@dataclass
class _Gathered:
    envelopes: list
    signatures: set
    limitations: list
    facts: set = field(default_factory=set)
    revoked: bool = False
    malformed: int = 0
    stalls: int = 0


class Controller:
    def __init__(self, root, *, composer=None, clock=time.monotonic):
        self.root = root
        self.composer = composer or AnswerComposer(root)
        self.clock = clock

    def run(self, asked, user):
        """Yield neutral progress; return an `Outcome`."""
        yield RetrievalStarted()
        try:
            budget = ControllerBudget.from_settings()
        except NotConfigured as exc:
            logger.warning("controller not configured: %s", exc)
            return Outcome(_unavailable(), "not_configured")
        ctx = self._context(asked, user, budget)
        run = ToolRun.start(ctx, self.root, scoped_handles=True)
        audit = RunAudit(ctx, self.clock)
        registry = general_tools()
        gathered = _Gathered([], set(), [])
        try:
            with model_call_deadline(ctx.budget.wall_clock_seconds, clock=self.clock):
                decision, reason = self._gather(asked, run, registry, budget, audit, gathered)
                if reason == "cancelled":
                    audit.finish(status=UNAVAILABLE, reason=reason,
                                 prompt_tokens=run.spend.prompt_tokens)
                    return Outcome(_unavailable(), reason, research_run_id=ctx.run_id)
                ready = self._ready(asked, run, decision, reason, budget, gathered)
                answer = self.composer.compose(ready)
        except Exception:
            audit.finish(status="failed", reason="failed", prompt_tokens=run.spend.prompt_tokens)
            raise
        audit.append(Step("answer", answer.state))
        audit.finish(status=answer.state, reason=reason, prompt_tokens=run.spend.prompt_tokens,
                     validation_codes=answer.validation)
        logger.info("controller run finished run_id=%s stop_reason=%s tool_calls=%s",
                    ctx.run_id, reason, run.spend.tool_calls)
        return Outcome(answer, reason, self._next_state(asked, decision, answer), ctx.run_id)

    # -- the loop -------------------------------------------------------------

    def _context(self, asked, user, budget) -> RunContext:
        ctx = RunContext.for_request(
            user=user, root=self.root, lane="research", conversation=asked.conversation,
            budget=budget.run_budget(), context_revision=asked.context_revision,
        )
        # Paper Chat stays on its paper unless the reader widened it.
        scope = asked.scope_record.pk if asked.scope_record is not None else None
        return replace(ctx, scope_record_id=scope)

    def _gather(self, asked, run, registry, budget, audit, gathered):
        model = self.root.llm_for(InferenceTask.PLAN)
        if not isinstance(model, ToolCallingLLM):
            return prompts.Decision(), "planner_unavailable"
        previous: list = []
        seen_ids: set = set()
        while True:
            if _cancelled():
                return prompts.Decision(), "cancelled"
            try:
                run.spend.begin_round()
            except BudgetExhausted as exc:
                return prompts.Decision(), str(exc)
            body = self._body(asked, run, budget, gathered)
            if gathered.revoked:
                # The last exchange may quote what just lost access.
                previous, gathered.revoked = [], False
            messages = [SystemMessage(prompts.SYSTEM), UserMessage(body), *previous]
            tools = registry.definitions()
            estimate = estimate_tokens(json.dumps([asdict(m) for m in messages]) + str(tools))
            seconds = run.spend.remaining_seconds - budget.reserved_seconds
            # The answer and its repair are reserved before any research call.
            if (run.spend.remaining_prompt_tokens - estimate < budget.reserved_tokens
                    or seconds <= 0):
                return prompts.Decision(), "answer_reserve"
            try:
                run.spend.charge_prompt_tokens(estimate)
                started = self.clock()
                completion = model.converse_with_tools(
                    messages, tools,
                    timeout_seconds=bounded(min(settings.AI_RESEARCH_PLAN_TIMEOUT_SECONDS, seconds)),
                )
            except BudgetExhausted as exc:
                return prompts.Decision(), str(exc)
            except (LLMUnavailable, CircuitOpen, TimeoutError):
                audit.append(Step("plan", "unavailable"))
                return prompts.Decision(), "planner_unavailable"
            audit.append(Step("plan", "ok", latency_ms=self._ms(started),
                              input_tokens=completion.input_tokens,
                              output_tokens=completion.output_tokens))
            calls = completion.tool_calls
            if not calls:
                return prompts.decision_from(completion.text, gathered=bool(gathered.envelopes)), "ready"
            ids_ok = all(isinstance(c.id, str) and c.id and len(c.id) <= 128 and c.id not in seen_ids
                         for c in calls) and len({c.id for c in calls}) == len(calls)
            if not ids_ok:
                gathered.malformed += 1
                audit.append(Step("tool", ToolStatus.REJECTED.value, tool="invalid"))
                if gathered.malformed >= 2:
                    return prompts.Decision(), "malformed_call"
                previous = [UserMessage(_CORRECTION)]
                continue
            seen_ids.update(c.id for c in calls)
            replies, stop = self._execute(run, registry, calls, budget, audit, gathered)
            if stop:
                return prompts.Decision(), stop
            previous = [AssistantMessage(tool_calls=calls),
                        *(ToolResultMessage(c.id, reply) for c, reply in zip(calls, replies))]

    def _execute(self, run, registry, calls, budget, audit, gathered):
        """Run one round's calls; reads go in waves no wider than the bound."""
        replies, repeats = [], 0
        known = _known(run, gathered)
        for wave in _waves(calls, budget.max_concurrent_reads):
            for call in wave:
                if _cancelled():
                    return replies, "cancelled"
                if run.spend.remaining_seconds <= budget.reserved_seconds:
                    return replies, "answer_reserve"
                signature = (call.name, argument_digest(call.arguments))
                repeats += signature in gathered.signatures
                gathered.signatures.add(signature)
                started = self.clock()
                envelope = registry.invoke(run, call.name, call.arguments)
                audit.append(Step("tool", envelope.status.value, tool=call.name[:64],
                                  argument_digest=signature[1], duplicate=envelope.trace.duplicate,
                                  latency_ms=self._ms(started)))
                if "budget_exhausted" in envelope.limitations:
                    return replies, "max_tool_calls"
                if set(envelope.limitations) & _MALFORMED:
                    gathered.malformed += 1
                    if gathered.malformed >= 2:
                        return replies, "malformed_call"
                elif envelope.status is Status.UNAVAILABLE:
                    gathered.limitations.extend(envelope.limitations)
                if not envelope.trace.duplicate and _informative(envelope):
                    gathered.envelopes.append(envelope)
                    gathered.facts.update(_fact_key(f) for f in envelope.facts)
                replies.append(json.dumps(envelope.public(), ensure_ascii=False))
        # No new evidence or fact: repeats stop at once, anything else after
        # two such rounds. No LLM judge decides this (spec §7).
        progress = _known(run, gathered) != known
        gathered.stalls = 0 if progress else gathered.stalls + 1
        if not progress and (repeats == len(calls) or gathered.stalls >= 2):
            return replies, "no_progress"
        return replies, None

    def _body(self, asked, run, budget, gathered) -> str:
        current = _current(run, gathered.envelopes)
        if len(current) != len(gathered.envelopes):
            gathered.envelopes[:] = current
            gathered.revoked = True
        payload = {
            "request": asked.question,
            "scope": "paper" if run.ctx.scope_record_id is not None else "corpus",
            "recent_history": [{"question": t.question, "answer": t.answer}
                               for t in planner_history(run.ctx)],
            "results": [e.public() for e in current],
            "remaining": {
                "rounds": budget.max_rounds - run.spend.rounds,
                "tool_calls": budget.max_tool_calls - run.spend.tool_calls,
            },
        }
        if asked.resolved_question and asked.resolved_question != asked.question:
            payload["request_in_context"] = asked.resolved_question
        state = conversation_state(run)
        if state is not None:
            payload["conversation_state"] = state
        return json.dumps(payload, ensure_ascii=False)

    # -- the hand-off ---------------------------------------------------------

    def _ready(self, asked, run, decision, reason, budget, gathered) -> ReadyToCompose:
        envelopes = _current(run, gathered.envelopes)
        # Gated again here: access may have changed since the last tool call.
        passages = tuple(LedgerRetriever(run).retrieve(asked.question, run.ctx.user).passages)
        limitations = list(dict.fromkeys(gathered.limitations))
        if reason != "ready":
            limitations.append(f"stopped_{reason}")
        facts = tuple(dict(f) for e in envelopes for f in e.facts)
        return ReadyToCompose(
            question=asked.question, resolved_question=asked.resolved_question,
            intent=decision.intent, basis=EVIDENCE if envelopes else decision.basis,
            passages=passages, facts=facts, limitations=tuple(limitations),
            stop_reason=reason, history=list(asked.history), clarify_about=decision.about,
            repair_attempts=budget.repair_attempts, pins=pin(CONTROLLER_ENGINE),
            current=_still_current(run),
        )

    @staticmethod
    def _next_state(asked, decision, answer) -> Optional[ContextState]:
        """What this Turn displayed: papers cited in order, or a pending question."""
        if asked.conversation is None:
            return None
        state = committed_state(asked.conversation)
        if decision.topic:
            state = state.with_topic(decision.topic)
        if decision.intent == CLARIFY:
            return state.clarifying(answer.text[:300])
        cited = list(dict.fromkeys(c.record_id for c in answer.citations))
        shown = {pk for pk in state.presented if pk is not None}
        if cited and not set(cited) <= shown:
            state = state.presenting(cited)
        return state

    def _ms(self, started) -> int:
        return max(0, int((self.clock() - started) * 1000))


def _waves(calls, width):
    wave = []
    for call in calls:
        if call.name in READS and sum(c.name in READS for c in wave) >= width:
            yield wave
            wave = []
        wave.append(call)
    if wave:
        yield wave


def _known(run, gathered) -> tuple:
    held = {i.handle for i in (*run.ledger.records(), *run.ledger.passages())}
    return frozenset(held), frozenset(gathered.facts)


def _fact_key(fact) -> str:
    return json.dumps(fact, sort_keys=True, default=str)


def _informative(envelope) -> bool:
    return envelope.status in (Status.OK, Status.PARTIAL, Status.AMBIGUOUS) and bool(
        envelope.items or envelope.evidence or envelope.facts)


def _current(run, envelopes) -> list:
    """Envelopes whose every source is still readable and disclosable, and
    whose metadata facts still describe the same visible population."""
    owners = {item.handle: item.record_id
              for item in (*run.ledger.records(), *run.ledger.passages())}
    named = [{owners[h] for h in _handles(e) if h in owners} for e in envelopes]
    allowed = disclosable(run.ctx, set().union(*named)) if named else {}
    snapshot = None
    if any(_snapshots(e) for e in envelopes):
        snapshot = population_snapshot(visible_record_ids(run.ctx))
    return [e for e, ids in zip(envelopes, named)
            if ids <= allowed.keys() and _snapshots(e) <= {snapshot}]


def _snapshots(envelope) -> set:
    return {f["provenance"]["snapshot"] for f in envelope.facts
            if f.get("provenance", {}).get("snapshot") is not None}


def _handles(envelope):
    for entry in (*envelope.items, *envelope.evidence):
        for key in ("record", "ref"):
            if isinstance(entry.get(key), str):
                yield entry[key]


def _still_current(run):
    """Chunk ids still readable, disclosable and in an active chunk set."""
    def current(sources) -> set:
        allowed = disclosable(run.ctx, {s.record_id for s in sources})
        active = set(DocumentChunk.objects.filter(
            pk__in=[s.chunk_id for s in sources], chunk_set__is_active=True,
            deleted_at__isnull=True,
        ).values_list("pk", flat=True))
        return {s.chunk_id for s in sources if s.record_id in allowed and s.chunk_id in active}
    return current


def _cancelled() -> bool:
    current = admission_scope.current_run()
    return current is not None and current.halted()


def _unavailable() -> GroundedAnswer:
    return GroundedAnswer(UNAVAILABLE_TEXT, (), state=UNAVAILABLE, degraded=True)
