"""The chunk, the chunk set, and the options that produced them.

All three are frozen. A chunk is a *value*, not an entity with a lifecycle:
re-chunking produces a new ``ChunkSet`` rather than mutating chunks, which
removes "was this embedded before or after the edit?" as a possible bug.

Pure: no Django, no I/O, no clock, no randomness.
"""

from dataclasses import dataclass, field
from typing import Mapping

from .document import BoundingBox

# Kept as a plain string literal, not an import of
# strategies.structural.STRATEGY_ID: that module imports this one for its
# value objects, and importing back would be circular.
DEFAULT_STRATEGY = "structural-markdown-v1"

# ADR-067 decision 14: the packer aims for the target; nothing may exceed the
# safety ceiling.
DEFAULT_TARGET_TOKENS = 700
DEFAULT_MAX_TOKENS = 2000


@dataclass(frozen=True)
class Chunk:
    """One retrievable unit of a document.

    ``text`` and ``content`` are stored separately on purpose. ``text`` is the
    exact string handed to the embedding model and must never change, because
    the vector was computed from it. ``content`` is what a citation shows a
    reader. Deriving either from the other at read time is how text and
    vectors silently diverge the day someone changes a separator.
    """

    text: str
    content: str
    context_path: tuple[str, ...]
    sequence: int
    token_count: int
    source_page: int | None = None
    element_kinds: frozenset[str] = field(default_factory=frozenset)
    bboxes: tuple[BoundingBox, ...] = ()
    # Full heading path of the chunk's section. Not hashed (IR-1050).
    section_key: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChunkingOptions:
    """The strategy's parameters, as data.

    Two sizes (ADR-067 decision 14): ``target_tokens`` is what packing and
    splitting aim for; ``max_tokens`` is the safety ceiling no embedded chunk
    text, heading trail included, may exceed. Only content a strategy keeps
    whole can land between them. Unset, the target is 700 or the ceiling,
    whichever is smaller.

    Every ``*_tokens`` field is counted in real ``voyage-context-4`` tokens
    (IR-287).
    """

    strategy: str = DEFAULT_STRATEGY
    max_tokens: int = DEFAULT_MAX_TOKENS
    target_tokens: int | None = None
    min_tokens: int | None = None
    context_path_max_tokens: int = 64
    merge_short_siblings: bool = True
    exclude_sections: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.max_tokens < 1:
            raise ValueError("max_tokens must be at least 1")
        if self.target_tokens is not None:
            if self.target_tokens < 1:
                raise ValueError("target_tokens must be at least 1")
            if self.target_tokens > self.max_tokens:
                raise ValueError("target_tokens must not exceed max_tokens")
        if self.min_tokens is not None:
            if self.min_tokens < 0:
                raise ValueError("min_tokens must not be negative")
            if self.min_tokens > self.effective_target_tokens:
                raise ValueError("min_tokens must not exceed the target size")

    @property
    def effective_target_tokens(self) -> int:
        if self.target_tokens is not None:
            return self.target_tokens
        return min(DEFAULT_TARGET_TOKENS, self.max_tokens)

    @property
    def effective_min_tokens(self) -> int:
        """The floor below which a chunk is merged with its next sibling.

        Derived from the target when not set explicitly, rather than
        defaulting to a constant. A fixed default is a footgun: it silently
        exceeds any small window a caller chooses, and the resulting error is
        about a value the caller never supplied.
        """
        if self.min_tokens is not None:
            return self.min_tokens
        # 88 real tokens is the old 64-word cap (IR-287).
        return max(1, min(88, self.effective_target_tokens // 8))


@dataclass(frozen=True)
class ChunkSet:
    """One chunking of one document.

    It exists so that "the chunks of this document" is a single value you can
    hash, compare, and replace atomically. Without it, re-chunking is a
    partial-update problem: delete some rows, insert others, and hope nothing
    reads the table mid-flight.
    """

    chunks: tuple[Chunk, ...]
    strategy_id: str
    options: ChunkingOptions
    content_hash: str
    page_sizes: Mapping[int, tuple[float, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.chunks, tuple):
            object.__setattr__(self, "chunks", tuple(self.chunks))

    def __len__(self) -> int:
        return len(self.chunks)
