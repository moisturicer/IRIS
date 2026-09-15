"""The retrieval seam (IR-129).

One interface: a question and a user in, ranked chunks the user is permitted
to read out. The whole query path is testable through it, which is the point --
the security property this package exists to guarantee is a property of *what
comes back*, not of how the SQL was shaped.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class RetrievedChunk:
    """A passage the asking user is entitled to read.

    Carries the record and page alongside the text because a citation needs
    them, and fetching them later would be a second query per result -- and,
    worse, a second place where visibility could be forgotten.
    """

    chunk_id: int
    record_id: int
    record_title: str
    content: str
    context_path: Sequence[str]
    source_page: Optional[int]
    score: float


class Retriever(ABC):
    @abstractmethod
    def retrieve(self, question: str, user, limit: int = 20) -> list[RetrievedChunk]:
        """Ranked, permitted passages for ``question``.

        Implementations must never return a chunk ``user`` cannot read -- not
        ranked lower, not filtered by the caller afterwards, never returned.
        """
