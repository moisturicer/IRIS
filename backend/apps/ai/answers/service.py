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
from typing import TYPE_CHECKING, Callable, Optional, Sequence

from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.providers.ports import LLMProvider
from apps.ai.retrieval.ports import RetrievedChunk, Retriever
from apps.records.models import Record

if TYPE_CHECKING:
    from apps.ai.memory import ConversationMemory
    from apps.ai.models import Conversation, Turn

from .citations import (
    NO_SOURCES,
    SYSTEM_PROMPT,
    UNAVAILABLE,
    GroundedAnswer,
    build_prompt,
    parse_citations,
    unresolved_marker_candidates,
)

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
    from apps.ai.policy import decision_for_record

    return decision_for_record(record).allowed


class GroundedAnswerService:
    def __init__(
        self,
        retriever: Retriever,
        llm: LLMProvider,
        permits: Callable[[Record], bool] = _default_permits,
        policy_enabled: bool = True,
        max_sources: int = 8,
        memory: Optional["ConversationMemory"] = None,
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        self._permits = permits
        self._policy_enabled = policy_enabled
        self._max_sources = max_sources
        self._memory = memory

    def _disclosable(self, chunks: Sequence[RetrievedChunk]) -> list[RetrievedChunk]:
        if not self._policy_enabled:
            return list(chunks)

        records = Record.objects.filter(
            pk__in={c.record_id for c in chunks}
        ).in_bulk()
        allowed = {rid for rid, rec in records.items() if self._permits(rec)}
        return [c for c in chunks if c.record_id in allowed]

    def answer(
        self,
        question: str,
        user,
        conversation: Optional["Conversation"] = None,
        history: Sequence["Turn"] = (),
    ) -> GroundedAnswer:
        """A grounded answer. ``history`` (a Conversation's recent Turns) goes
        into the prompt verbatim; memory recall adds older, relevant ones
        when ``conversation`` is given (IR-297).
        """
        retrieved = self._retriever.retrieve(question, user, limit=self._max_sources)
        # Read off the result, not off the object with `getattr(..., False)`:
        # that default is what turned a dropped flag into a confident "the
        # vendor was fine" instead of an error (IR-279).
        degraded = retrieved.degraded

        sources = self._disclosable(retrieved.passages)[: self._max_sources]
        if not sources:
            # Nothing to ground an answer in. Saying so beats asking a model to
            # answer from nothing, which is how an invention gets written.
            return GroundedAnswer(
                text="No readable sources were found for this question.",
                citations=(),
                degraded=degraded,
                state=NO_SOURCES,
                query_vector=retrieved.query_vector,
                embedding_space_id=retrieved.embedding_space_id,
            )

        recalled: Sequence["Turn"] = ()
        if self._memory is not None and conversation is not None:
            recalled = self._memory.recall(
                conversation,
                retrieved.query_vector,
                retrieved.embedding_space_id,
                exclude_ids=[turn.pk for turn in history],
            )

        try:
            raw = self._llm.generate(
                system=SYSTEM_PROMPT,
                user=build_prompt(question, sources, history=history, recalled=recalled),
            )
        except LLMUnavailable as exc:
            logger.warning("answer generation unavailable: %s", exc)
            # Degraded whatever retrieval did: the reader is getting sources
            # instead of an answer, which is exactly what the flag exists to
            # say. The sources travel with it -- retrieval worked.
            return GroundedAnswer(
                text=UNAVAILABLE_TEXT,
                citations=(),
                degraded=True,
                state=UNAVAILABLE,
                sources=tuple(sources),
                query_vector=retrieved.query_vector,
                embedding_space_id=retrieved.embedding_space_id,
            )

        text, citations = parse_citations(raw, sources)
        _warn_if_citations_went_missing(raw, text, citations)
        return GroundedAnswer(
            text=text,
            citations=citations,
            degraded=degraded,
            sources=tuple(sources),
            query_vector=retrieved.query_vector,
            embedding_space_id=retrieved.embedding_space_id,
            model=self._model_that_answered(),
        )

    def _model_that_answered(self) -> Optional[str]:
        """Which model actually produced the answer just generated (IR-321).

        `FallbackLLMProvider.last_model_used` is read first because it is the
        only source of truth when a fallback provider handled the call --
        `.model` alone would report whichever provider is configured first,
        which is wrong exactly when a fallback happened. Every other
        `LLMProvider` this composes with (a lone adapter, a retry/circuit
        decorator, a test fake) either has no `.model` or reports the one
        provider it can ever call, so falling back to `.model` is correct
        for all of them.
        """
        return getattr(self._llm, "last_model_used", None) or getattr(
            self._llm, "model", None
        )


def _warn_if_citations_went_missing(raw: str, text: str, citations: Sequence) -> None:
    """Say something when an answer that should have cited did not.

    **Why this exists.** Twice now the model has drifted to a marker format the
    parser did not recognise -- `【1】`, then `【1†L1-L5】` -- and both times the
    symptom was identical and silent: a fluent answer, zero citations, the raw
    marker sitting in the reader's text, and nothing anywhere saying so. Both
    were found by a person reading a transcript by hand. There will be a third
    format; this is so it costs a log line rather than another afternoon.

    **The trigger is the unambiguous half.** The model was handed numbered
    sources and told to cite them, it wrote a real answer, and not one citation
    resolved. The one honest reason for that is the answer saying the sources
    do not cover the question, which the prompt explicitly asks for and
    `NO_ANSWER_HINT` already names -- so that case is excluded rather than
    alerted on.

    **The candidates are only the diagnostic half**, consulted after the
    anomaly is already established. `unresolved_marker_candidates` is
    deliberately loose and will sometimes point at ordinary prose; that is
    affordable here precisely because it never decides anything on its own, and
    when it is right it hands over the exact new format to support.
    """
    if citations or NO_ANSWER_HINT in text.lower():
        return

    candidates = unresolved_marker_candidates(raw)
    if candidates:
        logger.warning(
            "answer cited nothing, but %d citation-shaped marker(s) did not "
            "parse -- the model may have drifted to an unsupported format: %s",
            len(candidates),
            list(candidates[:5]),
        )
    else:
        logger.warning(
            "answer cited nothing and no citation-shaped markers were found, "
            "though sources were supplied and the answer does not decline"
        )
