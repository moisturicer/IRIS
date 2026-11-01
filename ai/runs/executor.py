"""What answers a run (IR-722). Called with no database transaction open.

Only a deterministic executor exists: it proves the run contract, never
paid capacity or answer quality.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Citation:
    record_id: int
    quote: str
    page: int | None = None


@dataclass(frozen=True)
class Result:
    answer: str
    citations: tuple[Citation, ...] = field(default_factory=tuple)
    #: Units this attempt used, as reported; 0 for the deterministic executor.
    reported_units: int = 0


class Executor(Protocol):
    name: str
    version: str
    #: Units reserved before the attempt starts.
    reserved_units: int

    async def answer(self, question: str) -> Result: ...


class DeterministicExecutor:
    name = "deterministic"
    version = "1"
    reserved_units = 0

    async def answer(self, question: str) -> Result:
        return Result(answer=f"Deterministic answer: {question.strip()}")
