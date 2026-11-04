"""What answers a run (IR-722). Called with no database transaction open.

Only a deterministic executor exists: it proves the run contract, never
paid capacity or answer quality. `tools` is `ai.research.tools.ResearchTools`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Protocol

if TYPE_CHECKING:
    from ai.agent.budget import Bounds


@dataclass(frozen=True)
class Citation:
    record_id: int
    quote: str
    page: int | None = None
    #: The Manuscript revision the quote was read from (IR-719).
    revision: str | None = None


@dataclass(frozen=True)
class Result:
    answer: str
    citations: tuple[Citation, ...] = field(default_factory=tuple)
    #: Units this attempt used, as reported; 0 for the deterministic executor.
    reported_units: int = 0
    #: "clarification" when the run asked the reader one question instead (IR-728).
    kind: str = "answer"
    #: The Conversation state this Turn leaves; None keeps the previous one.
    state: dict | None = None
    #: Typed facts the answer stated: exact counts (with their counted Records, private)
    #: and keyword samples, which are never totals (IR-750).
    facts: tuple[dict, ...] = ()


@dataclass(frozen=True)
class PriorTurn:
    question: str
    answer: str
    kind: str = "answer"


@dataclass(frozen=True)
class RunContext:
    """What a claimed run carries into a conversational executor (IR-728)."""

    #: The persisted AskRun allowance, never renewed.
    allowance: dict
    remaining_seconds: float
    depth: str = "ordinary"
    #: Earlier Turns, oldest first.
    prior: tuple[PriorTurn, ...] = ()
    #: Shown order, selections and exclusions, as Record ids.
    state: dict = field(default_factory=dict)
    #: The research Bounds pinned at admission; the worker cannot widen them (IR-862).
    bounds: Optional["Bounds"] = None


class Unavailable(Exception):
    """No acceptable answer; the run ends `unavailable` and nothing is substituted."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class Executor(Protocol):
    name: str
    version: str
    #: Units reserved before the attempt starts.
    reserved_units: int

    async def answer(self, question: str, tools) -> Result: ...


class DeterministicExecutor:
    name = "deterministic"
    version = "1"
    reserved_units = 0

    async def answer(self, question: str, tools) -> Result:
        return Result(answer=f"Deterministic answer: {question.strip()}")
