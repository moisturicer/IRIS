"""The streaming event vocabulary for Ask IRIS (IR-326).

Yielded by `GroundedAnswerService.answer_stream` in the order a reader should
see them: retrieval, then generation, then the citations resolved once the
full answer is in hand. Pure domain shapes -- turning one into an SSE line is
the view's job (`apps/ai/views/chatbot.py`), the same split `presentation.py`
already draws between the domain's `GroundedAnswer` and the wire's JSON.

**Per ADR-028, this is honest progress reporting for one deterministic
retrieval call followed by one generation call -- never framed as parallel
agents or multi-step autonomous search.** The research lane (ADR-038) is the
one exception: its planner's steps arrive as `AgentStep` (IR-504).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional

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
class ReasoningDelta(AnswerEvent):
    """One increment of the model's reasoning (IR-327) -- structurally
    distinct from `TextDelta` at every layer downstream, per the vendor's own
    separate `reasoning` channel (IR-325's `StreamDelta.reasoning`) and per
    the defensive `<think>...</think>` split in `apps/ai/answers/reasoning.py`
    for the known leak into the text channel. Never concatenated into the
    answer, never scanned for citation markers, never persisted as
    `Turn.answer`. Its text *is* persisted, on `Turn.reasoning` (IR-381) --
    a different column with a different reader: a collapsed panel beside the
    answer, never the answer itself. `Turn.had_reasoning` survives alongside
    it for the Turns written before the text was stored.
    """

    text: str
    name: ClassVar[str] = "reasoning_delta"


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


#: A candidate's state in a listing. `pending` is only ever a preview: it
#: establishes no match and counts as none (IR-546).
PENDING, INCLUDED, EXCLUDED, UNCERTAIN, UNASSESSED = (
    "pending", "included", "excluded", "uncertain", "unassessed",
)
CANDIDATE_STATES = (PENDING, INCLUDED, EXCLUDED, UNCERTAIN, UNASSESSED)


@dataclass(frozen=True)
class CandidatesSelected(AnswerEvent):
    """The candidates a listing will screen, before any is judged (IR-546).

    Each row is `{record_id, title, state: "pending"}` and names a Record the
    reader may see. `more_available` is true only when retrieval found more
    than `limit`; false never means nothing else exists.
    """

    candidates: tuple[dict, ...]
    limit: int
    more_available: bool
    degraded: bool
    name: ClassVar[str] = "candidates_selected"

    def wire(self) -> dict:
        return {
            "candidates": list(self.candidates), "limit": self.limit,
            "more_available": self.more_available, "degraded": self.degraded,
        }


@dataclass(frozen=True)
class CandidatesUpdated(AnswerEvent):
    """New states for candidates already announced, by stable `record_id`.

    Rows carry a state and nothing else: no quote, no model text. The quoted
    support is in the final listing, after access is checked once more.
    """

    candidates: tuple[dict, ...]
    name: ClassVar[str] = "candidates_updated"

    def wire(self) -> dict:
        return {"candidates": list(self.candidates)}


@dataclass(frozen=True)
class AgentStep(AnswerEvent):
    """One research-planner step (IR-504): names, codes and counts, no content.

    A step is sent `running` before it starts and again with its outcome;
    `position` ties the two together.
    """

    position: int
    kind: str
    status: str
    tool: str = ""
    duplicate: bool = False
    latency_ms: int = 0
    coverage: Optional[str] = None
    found: Optional[int] = None
    name: ClassVar[str] = "agent_step"

    @classmethod
    def of(cls, position: int, step, *, coverage=None, found=None) -> "AgentStep":
        """From an audit `Step`, which carries no content either."""
        return cls(position, step.kind, step.status, tool=step.tool, duplicate=step.duplicate,
                   latency_ms=step.latency_ms, coverage=coverage, found=found)

    def wire(self) -> dict:
        return {
            "position": self.position, "kind": self.kind, "status": self.status,
            "tool": self.tool, "duplicate": self.duplicate, "latency_ms": self.latency_ms,
            "coverage": self.coverage, "found": self.found,
        }
