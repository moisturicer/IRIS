"""The ledger replaces retrieval; generation and citation parsing stay shared."""

import json

from apps.ai.answers.service import GroundedAnswerService, UNAVAILABLE_TEXT
from apps.ai.answers.citations import GroundedAnswer, UNAVAILABLE
from apps.ai.history import estimate_tokens
from apps.ai.providers.ports import LLMProvider
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.providers.dialects import DEFAULT_DIALECT
from apps.ai.retrieval.ports import Retriever, RetrievedChunk, RetrievalResult
from .budget import BudgetExhausted
from .tools.common import disclosable
from .validation import validate_answer


class LedgerRetriever(Retriever):
    def __init__(self, run):
        self.run = run
        self.source_handles = {}

    def retrieve(self, question, user, limit=30):
        if user.pk != self.run.ctx.user.pk:
            raise PermissionError("research run owner mismatch")
        items = self.run.ledger.passages()
        allowed = disclosable(self.run.ctx, (p.record_id for p in items))
        items = [p for p in items if p.record_id in allowed][:limit]
        self.source_handles = {i: p.handle for i, p in enumerate(items, 1)}
        return RetrievalResult(passages=tuple(
            RetrievedChunk(
                chunk_id=p.chunk_id, record_id=p.record_id, record_title=p.record_title,
                content=p.text, context_path=p.context_path, source_page=p.page, score=p.score,
            ) for p in items
        ))


class ResearchAnswerLLM(LLMProvider):
    """Add computed facts and check raw text before markers can be stripped."""

    def __init__(self, inner, run, retriever, results):
        self.inner = inner
        self.run = run
        self.retriever = retriever
        self.results = results
        self.validation_codes = ()

    @property
    def dialect(self):
        return getattr(self.inner, "dialect", DEFAULT_DIALECT)

    @property
    def model(self):
        return getattr(self.inner, "last_model_used", None) or getattr(self.inner, "model", None)

    def generate(self, system, user):
        if self.run.spend.remaining_seconds <= 0:
            raise LLMUnavailable("research run wall clock budget exhausted")
        facts = [
            {"coverage": r.coverage.label.value, "truncated": r.coverage.truncated,
             "rows": dict(r.detail)} for r in self.results if r.detail
        ]
        system += (
            "\nResearch answer rules: only numbered Sources are citable. "
            "Mark every paper title as «exact title from the ledger». "
            "Do not introduce any other title, number or exhaustive claim. "
            "A sample or matches_found result cannot establish all papers or a total. "
            "Computed rows are facts, never new passage citations."
        )
        user += "\nComputed rows and their coverage:\n" + json.dumps(facts, ensure_ascii=False)
        self.run.spend.charge_prompt_tokens(estimate_tokens(system + user))
        raw = self.inner.generate(system, user)
        sources = self.retriever.retrieve("", self.run.ctx.user).passages
        self.validation_codes = validate_answer(
            raw, sources=sources, ledger=self.run.ledger, results=self.results,
        )
        if self.validation_codes:
            raise LLMUnavailable("research answer failed evidence validation")
        return raw


def synthesize(question, run, llm, results):
    retriever = LedgerRetriever(run)
    checked_llm = ResearchAnswerLLM(llm, run, retriever, results)
    service = GroundedAnswerService(
        retriever, checked_llm, permits=run.ctx.permits,
        max_sources=run.ctx.budget.max_ledger_passages,
    )
    try:
        answer = service.answer(question, run.ctx.user)
    except BudgetExhausted:
        answer = GroundedAnswer(
            text=UNAVAILABLE_TEXT, citations=(), state=UNAVAILABLE, degraded=True,
            sources=retriever.retrieve(question, run.ctx.user).passages,
        )
    if checked_llm.validation_codes:
        from dataclasses import replace

        answer = replace(answer, text=(
            "The research answer was withheld because it failed evidence validation. "
            "The gathered sources are available to read directly."
        ), reasoning="", had_reasoning=False)
    return answer, retriever.source_handles, checked_llm.validation_codes


class AnswerTaskLLM(LLMProvider):
    """Resolve the answer model only if evidence actually needs generation."""

    def __init__(self, root):
        self.root = root
        self.provider = None

    @property
    def model(self):
        return getattr(self.provider, "last_model_used", None) or getattr(self.provider, "model", None)

    def generate(self, system, user):
        from apps.ai.inference import InferenceTask

        self.provider = self.root.llm_for(InferenceTask.ANSWER)
        return self.provider.generate(system, user)
