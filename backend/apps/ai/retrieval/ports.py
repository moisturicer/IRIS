"""The retrieval seam (IR-129).

One interface: a question and a user in, ranked chunks the user is permitted
to read out. The whole query path is testable through it, which is the point --
the security property this package exists to guarantee is a property of *what
comes back*, not of how the SQL was shaped.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import Optional, Sequence

#: The two ways a result can have been produced. Strings rather than an enum
#: because this crosses into an API response and a log line, where a name is
#: what is wanted; the set is small and closed enough that a constant each is
#: the whole of the abstraction it needs.
VECTOR = "vector"
FULL_TEXT = "full-text"


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


@dataclass(frozen=True)
class RetrievalResult:
    """What a retrieval produced, and how it was produced (IR-279).

    **Why this is a value and not a list.** The degraded flag used to ride on
    a ``list`` subclass, chosen so that "every existing caller iterates,
    indexes and slices it unchanged". That ergonomic is exactly what lost the
    flag: ``RerankingRetriever`` built an ordinary list from the results, and
    the subclass went with it, silently, so ADR-008's promise that a reader is
    told when the answer came from the fallback was false whenever a decorator
    sat in the stack — which is always.

    A frozen value has no such failure mode. A decorator cannot accidentally
    return "the passages" and think it returned the result, because the
    passages are not a result, and neither mistake can now pass silently: a
    decorator that returns a bare list gives the next reader an
    ``AttributeError`` on ``.degraded``, and a caller that treats a result as
    a list gets a ``TypeError``. Either way it is a failure at the seam
    rather than a ``False`` in the UI.

    ``mode`` and ``embedding_space_id`` are the room IR-133's evaluation work
    needs to tell the two retrieval paths apart, and to know which index a
    measurement was taken against. Neither is required — a retriever that
    does not know leaves them ``None``.
    """

    passages: tuple[RetrievedChunk, ...] = ()
    degraded: bool = False
    mode: Optional[str] = None
    embedding_space_id: Optional[int] = None

    def with_passages(self, passages: Sequence[RetrievedChunk]) -> "RetrievalResult":
        """The same result, re-ranked or trimmed.

        The method a decorator should reach for, and the reason the default
        is to carry everything forward: changing the passages is what a
        decorator does, and every other field surviving is what it must not
        have to remember.
        """
        return replace(self, passages=tuple(passages))


class Retriever(ABC):
    @abstractmethod
    def retrieve(self, question: str, user, limit: int = 20) -> RetrievalResult:
        """Ranked, permitted passages for ``question``.

        Implementations must never return a chunk ``user`` cannot read -- not
        ranked lower, not filtered by the caller afterwards, never returned.

        A **decorator** must return the result it was handed, with its
        passages replaced -- ``inner_result.with_passages(...)`` -- never a
        freshly constructed one. Constructing a new result silently resets
        ``degraded`` to ``False``, which is the defect IR-279 fixed.
        """
