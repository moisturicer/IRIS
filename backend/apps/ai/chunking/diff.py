"""What a re-chunk actually costs, decided before any of it is spent.

Re-chunking is routine — a normalizer fix, a strategy change, a token-ceiling
adjustment, a re-extraction. The naive implementation re-embeds the whole
document every time, which on a metered token budget is the difference
between an experiment that can be run repeatedly and one that can be run
once.

This module answers the only question that makes it cheap: *which chunks are
genuinely new?* A chunk's ``text`` is exactly what its vector was computed
from, so two chunks with the same text hash are interchangeable as far as the
embedding provider is concerned, no matter where in the document they sit.
Sequence deliberately does not participate: a paragraph that shifts down
because something was inserted above it is the same string, and buying its
vector again would buy nothing.

Pure: no Django, no I/O, no clock, no randomness. The decision is made here,
where it is testable with two lists and an assertion; ``apps.ai.repositories``
is what acts on it.
"""

from dataclasses import dataclass
from typing import Optional

from .hashing import chunk_text_hash
from .values import Chunk, ChunkSet


@dataclass(frozen=True)
class ChunkSetDiff:
    """The plan for one re-chunk.

    ``unchanged`` is the case worth optimising for and is decided by the set
    hash alone, before any per-chunk work: an idempotent re-run of the
    pipeline on identical input must cost zero writes and zero embedding
    calls.
    """

    unchanged: bool
    reused: tuple[Chunk, ...]
    to_embed: tuple[Chunk, ...]
    removed_hashes: tuple[str, ...]


def diff_chunk_sets(
    *, previous: Optional[ChunkSet], incoming: ChunkSet
) -> ChunkSetDiff:
    """Classify ``incoming``'s chunks against ``previous``.

    ``previous`` is ``None`` for a first chunking, which is simply the case
    where nothing can be reused.
    """
    if previous is not None and previous.content_hash == incoming.content_hash:
        return ChunkSetDiff(
            unchanged=True, reused=(), to_embed=(), removed_hashes=()
        )

    previous_hashes = (
        tuple(chunk_text_hash(chunk) for chunk in previous.chunks)
        if previous is not None
        else ()
    )
    previous_hash_set = set(previous_hashes)

    reused: list[Chunk] = []
    to_embed: list[Chunk] = []
    surviving: set[str] = set()
    for chunk in incoming.chunks:
        text_hash = chunk_text_hash(chunk)
        if text_hash in previous_hash_set:
            surviving.add(text_hash)
            reused.append(chunk)
        else:
            to_embed.append(chunk)

    # Ordered and de-duplicated, so the value is comparable and reproducible;
    # the previous set's document order is the only order there is to keep.
    removed = tuple(
        text_hash
        for text_hash in dict.fromkeys(previous_hashes)
        if text_hash not in surviving
    )

    return ChunkSetDiff(
        unchanged=False,
        reused=tuple(reused),
        to_embed=tuple(to_embed),
        removed_hashes=removed,
    )
