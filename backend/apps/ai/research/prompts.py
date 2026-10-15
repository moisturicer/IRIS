"""Fresh planner context, never a replay of stale evidence (IR-513)."""

import json
from dataclasses import replace

from apps.ai.history import recent_window
from apps.ai.models import Turn
from .results import ToolResult, ToolStatus, NO_COVERAGE
from .tools.common import disclosable, visible_record_ids


def planner_history(ctx):
    if ctx.conversation_id is None:
        return []
    candidates = Turn.objects.filter(
        conversation_id=ctx.conversation_id, conversation__user=ctx.user,
    )
    if ctx.history_before_turn_id is not None:
        candidates = candidates.filter(pk__lt=ctx.history_before_turn_id)
    # Filtered before the budget, so a revoked Turn leaves no hole (IR-592).
    return recent_window(candidates, allowed=lambda ids: disclosable(ctx, ids).keys())


def conversation_state(run):
    """The state's papers as this run's handles, positions kept (IR-592)."""
    from apps.ai.conversation_state import reissue_handles, snapshot
    from apps.ai.models import Conversation

    ctx = run.ctx
    if ctx.conversation_id is None:
        return None
    conversation = Conversation.objects.filter(pk=ctx.conversation_id, user=ctx.user).first()
    if conversation is None:
        return None
    snap = snapshot(conversation, ctx.user)
    if not snap.state.record_ids() and not snap.state.topic:
        return None
    return {"topic": snap.state.topic, "filters": snap.state.filters,
            **reissue_handles(run, snap)}


def current_results(results, allowed, visible):
    """A content-bearing result is withheld in full if any source lost access.

    In particular screening quotes and section headings cannot outlive their
    record's gate. Metadata aggregates must still describe the same visible set.
    """
    return [result for result in results
            if all(item.record_id in allowed for item in result.evidence)
            and (result.visible_record_ids is None or result.visible_record_ids == visible)]


class PlannerContext:
    def __init__(self, run, question):
        self.run = run
        self.question = question
        self.notes = []
        self.exposed_records = set()
        self.exposed_history = set()
        self.exposed_visible_records = set()
        self.revoked = False

    def body(self, results):
        run = self.run
        # First, so its reissued records are tracked for revocation below.
        state = conversation_state(run)
        items = (*run.ledger.records(), *run.ledger.passages())
        allowed = disclosable(run.ctx, (item.record_id for item in items))
        evidence = [item for item in items if item.record_id in allowed]
        history = planner_history(run.ctx)
        visible = visible_record_ids(run.ctx)
        current_records = {item.record_id for item in evidence}
        current_history = {turn.pk for turn in history}
        self.revoked = bool(self.exposed_records - current_records
                            or self.exposed_history - current_history
                            or self.exposed_visible_records - visible)
        if self.revoked:
            self.notes.clear()
        self.exposed_records = current_records
        self.exposed_history = current_history
        self.exposed_visible_records = visible
        payload = {
            "question": self.question,
            "recent_history": [{"question": turn.question, "answer": turn.answer}
                               for turn in history],
            "aggregate_context": json.loads(ToolResult(
                ToolStatus.OK, NO_COVERAGE, evidence=tuple(evidence),
            ).planner_message()),
            "computed_results": [json.loads(replace(result, evidence=()).planner_message())
                                 for result in current_results(results, allowed, visible)],
            "planner_notes_not_evidence": list(self.notes),
        }
        if state is not None:
            payload["conversation_state"] = state
        return json.dumps(payload, ensure_ascii=False)
