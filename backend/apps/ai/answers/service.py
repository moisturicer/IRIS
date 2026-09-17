"""Turning retrieved passages into a grounded, cited answer (IR-131).

The composition point: retrieve, gate, assemble, generate, parse. Each of those
lives somewhere testable on its own; this is the thin thing that orders them.

**The disclosure gate runs before the prompt is built, never over the answer.**
An LLM call always leaves the deployment -- unlike a reranker, there is no
local variant -- so every passage in the prompt is content sent to a vendor.
Filtering afterwards would mean it had already gone (ADR-015, IR-127).

**A vendor failure is never a fabricated answer.** ADR-008: when the provider
is unavailable the answer is replaced by an explicit unavailable state. The
sources are still returned, because retrieval worked -- a reader gets passages
to read themselves instead of a sentence nobody wrote.
"""

from __future__ import annotations

import logging
from typing import Callable, Sequence

from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.providers.ports import LLMProvider
from apps.ai.retrieval.ports import RetrievedChunk, Retriever
from apps.records.models import Record

from .citations import SYSTEM_PROMPT, GroundedAnswer, build_prompt, parse_citations

logger = logging.getLogger(__name__)

#: What a reader is told when the provider is down. Deliberately plain, and
#: deliberately not phrased as an answer.
UNAVAILABLE_TEXT = (
    "The answering model is unavailable right now, so this has not been "
    "answered. The sources found for the question are listed below and can be "
    "read directly."
)

#: What the model is told to say when the sources do not cover the question --
#: asserted by a test, so the instruction and the expectation cannot drift.
NO_ANSWER_HINT = "the sources do not"


def _default_permits(record: Record) -> bool:
    from apps.ai.policy import inputs_for_record, may_disclose

    return may_disclose(inputs_for_record(record)).allowed


class GroundedAnswerService:
    def __init__(
        self,
        retriever: Retriever,
        llm: LLMProvider,
        permits: Callable[[Record], bool] = _default_permits,
        policy_enabled: bool = True,
        max_sources: int = 8,
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        self._permits = permits
        self._policy_enabled = policy_enabled
        self._max_sources = max_sources

    def _disclosable(self, chunks: Sequence[RetrievedChunk]) -> list[RetrievedChunk]:
        if not self._policy_enabled:
            return list(chunks)

        records = Record.objects.filter(
            pk__in={c.record_id for c in chunks}
        ).in_bulk()
        allowed = {rid for rid, rec in records.items() if self._permits(rec)}
        return [c for c in chunks if c.record_id in allowed]

    def answer(self, question: str, user) -> GroundedAnswer:
        retrieved = self._retriever.retrieve(question, user, limit=self._max_sources)
        degraded = bool(getattr(retrieved, "degraded", False))

        sources = self._disclosable(retrieved)[: self._max_sources]
        if not sources:
            # Nothing to ground an answer in. Saying so beats asking a model to
            # answer from nothing, which is how an invention gets written.
            return GroundedAnswer(
                text="No readable sources were found for this question.",
                citations=(),
                degraded=degraded,
            )

        try:
            raw = self._llm.generate(
                system=SYSTEM_PROMPT, user=build_prompt(question, sources)
            )
        except LLMUnavailable as exc:
            logger.warning("answer generation unavailable: %s", exc)
            return GroundedAnswer(text=UNAVAILABLE_TEXT, citations=(), degraded=True)

        text, citations = parse_citations(raw, sources)
        return GroundedAnswer(text=text, citations=citations, degraded=degraded)
