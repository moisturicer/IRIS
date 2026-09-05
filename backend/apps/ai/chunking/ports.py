"""The chunker port.

Two arguments, one return value, over an implementation of several hundred
lines. That ratio is what makes it a deep module.

It is **synchronous and pure**: the document arrives already extracted, and
chunking is CPU work. Making it ``async`` would advertise an I/O seam that
does not exist. Callers that need it off the event loop move it themselves.
"""

from typing import Protocol, runtime_checkable

from .document import NormalizedDocument
from .values import ChunkSet, ChunkingOptions


class ChunkingError(Exception):
    """Base class for chunking failures."""


class UnknownChunkingStrategy(ChunkingError):
    """Raised when a strategy id is not registered.

    It raises rather than falling back to a default. The gateway's provider
    wiring silently resolves an unrecognised name to a mock adapter, which
    turns a typo into wrong output instead of an error; that failure mode is
    not repeated here.
    """

    def __init__(self, strategy: str, known: list[str]):
        self.strategy = strategy
        self.known = known
        super().__init__(
            f"Unknown chunking strategy {strategy!r}. "
            f"Known strategies: {', '.join(known) if known else '(none registered)'}"
        )


@runtime_checkable
class Chunker(Protocol):
    """Turns a normalized document into a ChunkSet.

    Pure with respect to I/O: no network, no database, no clock, no
    randomness. Deterministic: the same document and options always produce
    the same ChunkSet, including its content hash, across runs and across
    processes.
    """

    def chunk(
        self, document: NormalizedDocument, options: ChunkingOptions
    ) -> ChunkSet: ...
