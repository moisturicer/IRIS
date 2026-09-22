"""The streaming event vocabulary for Ask IRIS (IR-326).

Yielded by `GroundedAnswerService.answer_stream` in the order a reader should
see them: retrieval, then generation, then the citations resolved once the
full answer is in hand. Pure domain shapes -- turning one into an SSE line is
the view's job (`apps/ai/views/chatbot.py`), the same split `presentation.py`
already draws between the domain's `GroundedAnswer` and the wire's JSON.

**Per ADR-028, this is honest progress reporting for one deterministic
retrieval call followed by one generation call -- never framed as parallel
agents or multi-step autonomous search.**
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from .citations import Citation, GroundedAnswer


class AnswerEvent:
    """Common base so a caller can type-check what `answer_stream` yields
    without importing every concrete event."""

    name: ClassVar[str]


@dataclass(frozen=True)
class RetrievalStarted(AnswerEvent):
    name: ClassVar[str] = "retrieval_started"


@dataclass(frozen=True)
class RetrievalFinished(AnswerEvent):
    """What retrieval found, before the gate or the model see it -- enough
    for a reader-facing "Found N passages from M papers"."""

    passage_count: int
    record_count: int
    degraded: bool
    name: ClassVar[str] = "retrieval_finished"


@dataclass(frozen=True)
class GenerationStarted(AnswerEvent):
    name: ClassVar[str] = "generation_started"


@dataclass(frozen=True)
class TextDelta(AnswerEvent):
    """One increment of the model's answer, exactly as written.

    Carries a citation marker -- `[1]`, or the lenticular form a model
    actually emits -- as raw, unparsed text. `parse_citations` runs once,
    against the fully accumulated answer, never per delta: it rewrites
    matched markers in place and reasons about a marker's *complete*
    bracketed span (`apps/ai/answers/citations.py`), neither of which is a
    sound operation on a partial buffer that might end mid-marker.
    """

    text: str
    name: ClassVar[str] = "text_delta"


@dataclass(frozen=True)
class CitationsResolved(AnswerEvent):
    citations: tuple[Citation, ...]
    name: ClassVar[str] = "citations_resolved"


@dataclass(frozen=True)
class Done(AnswerEvent):
    """The stream is over. Carries the same `GroundedAnswer` the synchronous
    `answer()` would have returned, so a caller can persist a Turn or shape a
    final response identically to the non-streaming path."""

    answer: GroundedAnswer
    name: ClassVar[str] = "done"
