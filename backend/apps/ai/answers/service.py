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
from typing import TYPE_CHECKING, Callable, Iterator, Optional, Sequence

from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.providers.ports import LLMProvider
from apps.ai.retrieval.ports import RetrievalResult, RetrievedChunk, Retriever
from apps.records.models import Record

if TYPE_CHECKING:
    from apps.ai.memory import ConversationMemory
    from apps.ai.models import Conversation, Turn

from .citations import (
    NO_SOURCES,
    PARTIAL,
    SYSTEM_PROMPT,
    UNAVAILABLE,
    GroundedAnswer,
    build_prompt,
    parse_citations,
    unresolved_marker_candidates,
)
from .events import (
    AnswerEvent,
    CitationsResolved,
    Done,
    GenerationStarted,
    ReasoningDelta,
    RetrievalFinished,
    RetrievalStarted,
    TextDelta,
)
from .reasoning import ThinkTagFilter

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

    def _retrieve_and_gate(
        self, question: str, user
    ) -> tuple[RetrievalResult, list[RetrievedChunk]]:
        """Retrieval plus the disclosure gate -- the one step ``answer`` and
        ``answer_stream`` must never disagree about, since it is where
        IR-129's visibility guarantee lives. Shared rather than duplicated
        (IR-326 code review) so a fix here reaches both.
        """
        retrieved = self._retriever.retrieve(question, user, limit=self._max_sources)
        sources = self._disclosable(retrieved.passages)[: self._max_sources]
        return retrieved, sources

    def _recall(self, retrieved, conversation, history) -> Sequence["Turn"]:
        if self._memory is None or conversation is None:
            return ()
        return self._memory.recall(
            conversation,
            retrieved.query_vector,
            retrieved.embedding_space_id,
            exclude_ids=[turn.pk for turn in history],
        )

    @staticmethod
    def _no_sources_answer(retrieved) -> GroundedAnswer:
        # Nothing to ground an answer in. Saying so beats asking a model to
        # answer from nothing, which is how an invention gets written.
        return GroundedAnswer(
            text="No readable sources were found for this question.",
            citations=(),
            degraded=retrieved.degraded,
            state=NO_SOURCES,
            query_vector=retrieved.query_vector,
            embedding_space_id=retrieved.embedding_space_id,
        )

    @staticmethod
    def _unavailable_answer(
        retrieved, sources: Sequence[RetrievedChunk], had_reasoning: bool = False
    ) -> GroundedAnswer:
        # Degraded whatever retrieval did: the reader is getting sources
        # instead of an answer, which is exactly what the flag exists to
        # say. The sources travel with it -- retrieval worked (ADR-008).
        return GroundedAnswer(
            text=UNAVAILABLE_TEXT,
            citations=(),
            degraded=True,
            state=UNAVAILABLE,
            sources=tuple(sources),
            query_vector=retrieved.query_vector,
            embedding_space_id=retrieved.embedding_space_id,
            had_reasoning=had_reasoning,
        )

    def _grounded_answer(
        self,
        retrieved,
        sources: Sequence[RetrievedChunk],
        text: str,
        citations,
        had_reasoning: bool = False,
    ) -> GroundedAnswer:
        return GroundedAnswer(
            text=text,
            citations=citations,
            degraded=retrieved.degraded,
            sources=tuple(sources),
            query_vector=retrieved.query_vector,
            embedding_space_id=retrieved.embedding_space_id,
            model=self._model_that_answered(),
            had_reasoning=had_reasoning,
        )

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
        retrieved, sources = self._retrieve_and_gate(question, user)
        if not sources:
            return self._no_sources_answer(retrieved)

        recalled = self._recall(retrieved, conversation, history)

        try:
            raw = self._llm.generate(
                system=SYSTEM_PROMPT,
                user=build_prompt(question, sources, history=history, recalled=recalled),
            )
        except LLMUnavailable as exc:
            logger.warning("answer generation unavailable: %s", exc)
            return self._unavailable_answer(retrieved, sources)

        text, citations = parse_citations(raw, sources)
        _warn_if_citations_went_missing(raw, text, citations)
        return self._grounded_answer(retrieved, sources, text, citations)

    def answer_stream(
        self,
        question: str,
        user,
        conversation: Optional["Conversation"] = None,
        history: Sequence["Turn"] = (),
        on_interrupted: Optional[Callable[[GroundedAnswer], None]] = None,
    ) -> Iterator[AnswerEvent]:
        """`answer`, event by event, for a reader-facing progress line
        (IR-326).

        Retrieval, the disclosure gate, memory recall and the final
        ``Done.answer`` are identical to ``answer()`` -- this is the same
        service, ordering the same steps through the same private helpers,
        only narrating them as it goes rather than returning once at the
        end. Only synthesis actually streams: ``self._llm.stream(...)`` in
        place of ``.generate(...)``, yielding a ``TextDelta`` per chunk of
        raw text and accumulating it to parse citations once, after the
        model has finished, for the reasons ``TextDelta`` documents.

        **Reasoning is a separate channel throughout** (IR-327).
        ``delta.reasoning`` -- the vendor's own dedicated field -- becomes a
        ``ReasoningDelta``, never a ``TextDelta``. ``delta.text`` is passed
        through ``ThinkTagFilter`` first: the known gpt-oss-120b/Groq
        behaviour is that reasoning sometimes leaks into the text channel as
        ``<think>...</think>`` even when configured hidden, and a leaked span
        is reasoning by content, not by which field it arrived in. Only what
        the filter classifies as text ever reaches ``raw_parts`` -- the
        buffer citation parsing and the stored ``Turn.answer`` are built
        from -- so leaked reasoning can corrupt neither.

        **`on_interrupted` is the one seam a caller needs for IR-328.** A
        `finally` around the whole method calls it, exactly once, with
        whatever text and sources had been accumulated -- but only when the
        method is exiting *without* having reached its own `Done`, tracked
        by the plain `completed` flag rather than inferred from where the
        exit happened. That makes it fire identically whichever of the
        cause-agnostic ways this can end: a caller closing the generator
        early (disconnect), an exception this method does not otherwise
        catch (an unexpected vendor error), or anything else. Never called
        on a normal `Done` -- including the `NO_SOURCES` and `UNAVAILABLE`
        branches below, which are already complete, honestly-stated answers,
        not truncated ones.
        """
        completed = False
        retrieved = None
        sources: list[RetrievedChunk] = []
        raw_parts: list[str] = []
        had_reasoning = False
        try:
            yield RetrievalStarted()
            retrieved, sources = self._retrieve_and_gate(question, user)
            yield RetrievalFinished(
                passage_count=len(sources),
                record_count=len({s.record_id for s in sources}),
                degraded=retrieved.degraded,
            )
            if not sources:
                completed = True
                yield Done(self._no_sources_answer(retrieved))
                return

            recalled = self._recall(retrieved, conversation, history)

            yield GenerationStarted()

            def classified(text_part: str, reasoning_part: str) -> Iterator[AnswerEvent]:
                """One `(text, reasoning)` pair, as whichever events it implies --
                shared by every source of a pair: the vendor's own `reasoning`
                field, and `ThinkTagFilter`'s split of `.text`, mid-stream or on
                `flush()`. `had_reasoning` and `raw_parts` are this method's own
                state, so this closes over them rather than returning something
                the caller would just apply right back.
                """
                nonlocal had_reasoning
                if reasoning_part:
                    had_reasoning = True
                    yield ReasoningDelta(text=reasoning_part)
                if text_part:
                    raw_parts.append(text_part)
                    yield TextDelta(text=text_part)

            leak_filter = ThinkTagFilter()
            try:
                for delta in self._llm.stream(
                    system=SYSTEM_PROMPT,
                    user=build_prompt(
                        question, sources, history=history, recalled=recalled
                    ),
                ):
                    yield from classified("", delta.reasoning)
                    if delta.text:
                        yield from classified(*leak_filter.feed(delta.text))
            except LLMUnavailable as exc:
                logger.warning("answer generation unavailable: %s", exc)
                completed = True
                yield Done(self._unavailable_answer(retrieved, sources, had_reasoning))
                return

            yield from classified(*leak_filter.flush())

            raw = "".join(raw_parts)
            text, citations = parse_citations(raw, sources)
            _warn_if_citations_went_missing(raw, text, citations)
            yield CitationsResolved(citations=citations)
            completed = True
            yield Done(
                self._grounded_answer(retrieved, sources, text, citations, had_reasoning)
            )
        finally:
            if not completed and on_interrupted is not None:
                on_interrupted(
                    self._partial_answer(retrieved, sources, raw_parts, had_reasoning)
                )

    @staticmethod
    def _partial_answer(
        retrieved,
        sources: Sequence[RetrievedChunk],
        raw_parts: Sequence[str],
        had_reasoning: bool,
    ) -> GroundedAnswer:
        """Whatever text and sources had been accumulated when the stream cut
        off, in the same `GroundedAnswer` shape a completed answer takes
        (IR-328). Citation parsing runs exactly once here, over the
        truncated text, precisely as it does on a clean completion --
        never per delta, for the reasons `TextDelta` documents.

        Deliberately skips `_warn_if_citations_went_missing`: an answer cut
        off mid-sentence routinely ends mid-marker or before any marker at
        all, and that is expected here, not the drifted-format anomaly that
        check exists to surface.

        `degraded` is always `True` -- not `retrieved.degraded`, which
        answers a different question. Completeness is unknown, and that
        alone is reason enough to ask a reader to weigh it carefully.
        """
        raw = "".join(raw_parts)
        text, citations = parse_citations(raw, sources)
        return GroundedAnswer(
            text=text,
            citations=citations,
            degraded=True,
            state=PARTIAL,
            sources=tuple(sources),
            query_vector=None if retrieved is None else retrieved.query_vector,
            embedding_space_id=(
                None if retrieved is None else retrieved.embedding_space_id
            ),
            had_reasoning=had_reasoning,
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
