"""Draft chunks, short-chunk merging and final assembly (IR-1050).

Every strategy builds ``Draft``s (a body without its trail), and this module
merges, numbers, decorates and checks them the same way for all of them.
"""

from dataclasses import dataclass, field
from typing import Callable

from .document import HEADING, BoundingBox
from .hashing import chunkset_hash
from .outline import embedded_text, trail_cost
from .ports import ChunkingError
from .regions import dedupe_regions
from .tokens import count_tokens
from .values import Chunk, ChunkingOptions, ChunkSet


@dataclass(frozen=True)
class Draft:
    """A chunk before its trail is attached and its sequence assigned."""

    body: str
    content: str
    trail: tuple[str, ...]
    section_key: tuple[str, ...]
    source_page: int | None = None
    element_kinds: frozenset[str] = field(default_factory=frozenset)
    bboxes: tuple[BoundingBox, ...] = ()


@dataclass(frozen=True)
class Joiners:
    """How a strategy joins two drafts' bodies and contents."""

    body: str = " "
    content: str = " "


def body_budget(trail: tuple[str, ...], options: ChunkingOptions, limit: int | None = None) -> int:
    """Tokens left for the body under ``limit`` (default: the target) once
    ``trail`` is in."""
    limit = options.effective_target_tokens if limit is None else limit
    return max(1, limit - trail_cost(trail))


def combine(drafts: list[Draft], joiners: Joiners) -> Draft:
    """Join adjacent drafts. The last one's trail and section win, so a heading
    folded forward takes the section it labels."""
    pages = [d.source_page for d in drafts if d.source_page is not None]
    kinds: frozenset[str] = frozenset()
    for d in drafts:
        kinds |= d.element_kinds
    return Draft(
        body=joiners.body.join(d.body for d in drafts if d.body),
        content=joiners.content.join(d.content for d in drafts if d.content),
        trail=drafts[-1].trail,
        section_key=drafts[-1].section_key,
        source_page=pages[0] if pages else None,
        element_kinds=kinds,
        bboxes=dedupe_regions([box for d in drafts for box in d.bboxes]),
    )


Fits = Callable[[Draft], bool]


def merge_short_siblings(
    drafts: list[Draft], options: ChunkingOptions, fits: Fits, joiners: Joiners
) -> list[Draft]:
    """Fold a draft below the floor into its next sibling in the same section.

    The target wins over the floor: a merge that would not fit is skipped.
    """
    if not options.merge_short_siblings or len(drafts) <= 1:
        return list(drafts)
    floor = options.effective_min_tokens
    result: list[Draft] = []
    pending = drafts[0]
    for nxt in drafts[1:]:
        if pending.section_key == nxt.section_key and count_tokens(pending.body) < floor:
            candidate = combine([pending, nxt], joiners)
            if fits(candidate):
                pending = candidate
                continue
        result.append(pending)
        pending = nxt
    result.append(pending)
    return result


def fold_heading_only(
    drafts: list[Draft], options: ChunkingOptions, fits: Fits, joiners: Joiners
) -> list[Draft]:
    """Fold heading-only drafts forward into the draft they label (IR-241).

    Greedy from the nearest heading; if none fits, all stay as they are. A
    trailing heading with nothing after it is kept.
    """
    if not options.merge_short_siblings or len(drafts) <= 1:
        return list(drafts)
    result: list[Draft] = []
    pending: list[Draft] = []
    for draft in drafts:
        if draft.element_kinds == frozenset({HEADING}):
            pending.append(draft)
            continue
        result.extend(_fold_into(pending, draft, fits, joiners) if pending else [draft])
        pending = []
    result.extend(pending)
    return result


def _fold_into(pending: list[Draft], draft: Draft, fits: Fits, joiners: Joiners) -> list[Draft]:
    for first in range(len(pending)):
        candidate = combine([*pending[first:], draft], joiners)
        if fits(candidate):
            return [*pending[:first], candidate]
    return [*pending, draft]


def finalize(
    drafts: list[Draft],
    *,
    strategy_id: str,
    options: ChunkingOptions,
    page_sizes,
    content_hash: Callable[[tuple[Chunk, ...]], str] = chunkset_hash,
) -> ChunkSet:
    """Attach trails, number the chunks, hash, and enforce the safety ceiling."""
    chunks = tuple(
        Chunk(
            text=(text := embedded_text(d.trail, d.body)),
            content=d.content,
            context_path=d.trail,
            sequence=sequence,
            token_count=count_tokens(text),
            source_page=d.source_page,
            element_kinds=d.element_kinds,
            bboxes=d.bboxes,
            section_key=d.section_key,
        )
        for sequence, d in enumerate(drafts)
    )
    for chunk in chunks:
        if chunk.token_count > options.max_tokens:
            raise ChunkingError(
                f"chunk {chunk.sequence} is {chunk.token_count} tokens, over the "
                f"safety ceiling of {options.max_tokens}"
            )
    return ChunkSet(
        chunks=chunks,
        strategy_id=strategy_id,
        options=options,
        content_hash=content_hash(chunks) if chunks else chunkset_hash(()),
        page_sizes=page_sizes,
    )


__all__ = [
    "Draft",
    "Joiners",
    "body_budget",
    "combine",
    "finalize",
    "fold_heading_only",
    "merge_short_siblings",
]
