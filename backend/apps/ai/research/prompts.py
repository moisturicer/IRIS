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
    turns = recent_window(Turn.objects.filter(
        conversation_id=ctx.conversation_id, conversation__user=ctx.user,
    ).prefetch_related("citations"))
    cited = {c.record_id for turn in turns for c in turn.citations.all()}
    allowed = disclosable(ctx, cited)
    return [turn for turn in turns
            if all(c.record_id in allowed for c in turn.citations.all())]


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
        return json.dumps(payload, ensure_ascii=False)
