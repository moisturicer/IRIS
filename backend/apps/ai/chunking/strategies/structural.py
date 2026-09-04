"""Structure-aware splitting cascade — the strategy the fixed-window baseline
(IR-110) is measured against on the eval set.

Five stages, each handling only what the one before it could not:

1. emit a section as-is if it fits the token ceiling
2. split on heading boundaries (sectioning)
3. split structurally: table rows/headers, list items, paragraphs
4. split on sentence boundaries
5. hard split on grapheme clusters, backtracking to the nearest breakpoint

Two rules hold throughout: a table split across chunks repeats its header
row in every fragment, and a list never splits mid-item. Short chunks merge
with their next sibling within a heading section, and never across one.

Sectioning (stage 2) runs before the fits-check (stage 1) is applied, not
after: "fits" is evaluated per section rather than for the document as a
whole, because checking the whole document first and only falling back to
sectioning on overflow would let two sections share one chunk whenever the
document happens to be short — exactly the merge-across-a-heading case the
short-chunk rule above exists to prevent.
"""

from dataclasses import dataclass

from ..document import (
    HEADING,
    LIST_ITEM,
    TABLE_HEADER,
    TABLE_ROW,
    DocumentElement,
    NormalizedDocument,
)
from ..hashing import chunkset_hash
from ..packing import Piece, pack_pieces
from ..regions import dedupe_regions, regions_for
from ..registry import register_chunker
from ..text_splitting import (
    grapheme_safe_split,
    split_into_clauses,
    split_into_sentences,
    split_into_word_groups,
)
from ..tokens import count_tokens
from ..values import Chunk, ChunkingOptions, ChunkSet

STRATEGY_ID = "structural-markdown-v1"

# Above this raw character length, a single whitespace-free "word" is
# pathological rather than a genuine token — a run-on with no natural
# boundary — and is hard-split at the grapheme level regardless of what the
# word-count ceiling would otherwise allow. Generous on purpose: this is a
# safety net for degenerate input, not a realistic word.
_HARD_SPLIT_CHAR_THRESHOLD = 64


@register_chunker(STRATEGY_ID)
class StructuralCascadeChunker:
    """Splits a document along its structure before ever falling back to a
    generic split. See the module docstring for the five-stage cascade."""

    def chunk(
        self, document: NormalizedDocument, options: ChunkingOptions
    ) -> ChunkSet:
        chunks: list[Chunk] = []
        for section in _sectionize(document.elements):
            chunks.extend(_chunk_section(section, options))

        chunks = [
            Chunk(
                text=c.text,
                content=c.content,
                context_path=c.context_path,
                sequence=sequence,
                token_count=c.token_count,
                source_page=c.source_page,
                element_kinds=c.element_kinds,
                bboxes=c.bboxes,
            )
            for sequence, c in enumerate(chunks)
        ]

        return ChunkSet(
            chunks=tuple(chunks),
            strategy_id=STRATEGY_ID,
            options=options,
            content_hash=chunkset_hash(chunks),
            page_sizes=document.page_sizes,
        )


# --------------------------------------------------------------------------
# Fit — the predicate every stage routes on
# --------------------------------------------------------------------------


def _longest_word_length(text: str) -> int:
    return max((len(w) for w in text.split()), default=0)


def _fits(text: str, max_tokens: int) -> bool:
    """Whether ``text`` can be emitted as one piece.

    Two conditions, not one: the word-count ceiling, and a character-length
    guard on the single longest word. Without the second, a pathological
    run-on with no whitespace always counts as "one token" and the grapheme
    stage would never be reachable no matter how long it actually is.
    """
    return (
        count_tokens(text) <= max_tokens
        and _longest_word_length(text) <= _HARD_SPLIT_CHAR_THRESHOLD
    )


# --------------------------------------------------------------------------
# Sectioning — stage 2, heading boundaries
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Section:
    heading: DocumentElement | None
    elements: tuple[DocumentElement, ...]


def _sectionize(elements: tuple[DocumentElement, ...]) -> list[_Section]:
    sections: list[_Section] = []
    heading: DocumentElement | None = None
    buffer: list[DocumentElement] = []

    for element in elements:
        if element.kind == HEADING:
            if buffer:
                sections.append(_Section(heading, tuple(buffer)))
            heading = element
            buffer = [element]
        else:
            buffer.append(element)

    if buffer:
        sections.append(_Section(heading, tuple(buffer)))
    return sections


# --------------------------------------------------------------------------
# One section: stage 1, then stage 3 structural splitting, then merging
# --------------------------------------------------------------------------


def _chunk_section(section: _Section, options: ChunkingOptions) -> list[Chunk]:
    elements = [e for e in section.elements if e.text.split()]
    if not elements:
        return []

    full_text = " ".join(e.text for e in elements)
    if _fits(full_text, options.max_tokens):
        windows = [[(e.text, e) for e in elements]]
    else:
        windows = _split_structurally(elements, options.max_tokens)

    chunks = [_window_to_chunk(w) for w in windows if w]
    return _merge_short_siblings(chunks, options)


def _run_kind(element: DocumentElement) -> str:
    if element.kind in (TABLE_HEADER, TABLE_ROW):
        return "table"
    if element.kind == LIST_ITEM:
        return "list"
    return "prose"


def _iter_runs(elements: list[DocumentElement]):
    current_kind: str | None = None
    buffer: list[DocumentElement] = []
    for element in elements:
        kind = _run_kind(element)
        if kind != current_kind and buffer:
            yield current_kind, buffer
            buffer = []
        current_kind = kind
        buffer.append(element)
    if buffer:
        yield current_kind, buffer


def _split_structurally(
    elements: list[DocumentElement], max_tokens: int
) -> list[list[Piece]]:
    windows: list[list[Piece]] = []
    for kind, run in _iter_runs(elements):
        if kind == "table":
            windows.extend(_pack_table(run, max_tokens))
        else:
            # "prose" and "list" runs share the same atomicity rule: a unit
            # that fits is pooled and packed with its neighbours; a unit
            # that does not fit is hard-split, and every resulting fragment
            # is isolated in its own chunk so it is never merged with a
            # sibling's content — the same rule that keeps a table's row
            # fragments from mixing, applied to list items and paragraphs.
            windows.extend(_pack_atoms(run, max_tokens))
    return windows


def _window_to_chunk(window: list[Piece]) -> Chunk:
    content = " ".join(text for text, _ in window)
    elements = [element for _, element in window]
    pages = [e.page for e in elements if e.page is not None]
    bboxes = regions_for(elements)
    return Chunk(
        text=content,
        content=content,
        context_path=(),
        sequence=0,  # reassigned once the full chunk set is known
        token_count=count_tokens(content),
        source_page=pages[0] if pages else None,
        element_kinds=frozenset(e.kind for e in elements),
        bboxes=bboxes,
    )


# --------------------------------------------------------------------------
# Prose and list runs — pool what fits, isolate what doesn't
# --------------------------------------------------------------------------


def _pack_atoms(elements: list[DocumentElement], max_tokens: int) -> list[list[Piece]]:
    windows: list[list[Piece]] = []
    pool: list[Piece] = []

    def flush_pool() -> None:
        nonlocal pool
        if pool:
            windows.extend(pack_pieces(pool, max_tokens))
            pool = []

    for element in elements:
        if _fits(element.text, max_tokens):
            pool.append((element.text, element))
            continue

        flush_pool()
        for fragment in _hard_split_text(element.text, max_tokens):
            windows.append([(fragment, element)])

    flush_pool()
    return windows


# --------------------------------------------------------------------------
# Table runs — pack rows under the header, repeating it in every fragment
# --------------------------------------------------------------------------


def _pack_table(elements: list[DocumentElement], max_tokens: int) -> list[list[Piece]]:
    headers = [e for e in elements if e.kind == TABLE_HEADER]
    rows = [e for e in elements if e.kind == TABLE_ROW]
    header_pieces: list[Piece] = [(h.text, h) for h in headers if h.text.split()]
    header_text = " ".join(t for t, _ in header_pieces)
    header_tokens = count_tokens(header_text)

    if not rows:
        return [header_pieces] if header_pieces else []

    windows: list[list[Piece]] = []
    current_rows: list[Piece] = []
    current_tokens = header_tokens

    def flush() -> None:
        nonlocal current_rows, current_tokens
        if current_rows:
            windows.append(header_pieces + current_rows)
        current_rows, current_tokens = [], header_tokens

    for row in rows:
        row_tokens = count_tokens(row.text)
        fits_with_header = _fits(f"{header_text} {row.text}".strip(), max_tokens)

        if not fits_with_header:
            flush()
            budget = max(1, max_tokens - header_tokens)
            for fragment in _hard_split_text(row.text, budget):
                windows.append(header_pieces + [(fragment, row)])
            continue

        if current_rows and current_tokens + row_tokens > max_tokens:
            flush()
        current_rows.append((row.text, row))
        current_tokens += row_tokens

    flush()
    return windows


# --------------------------------------------------------------------------
# Stages 4 and 5 — sentence, clause, word, then grapheme-safe hard split
# --------------------------------------------------------------------------


def _hard_split_text(text: str, max_tokens: int) -> list[str]:
    """Split ``text`` until every piece fits, trying the coarsest boundary
    that works before ever cutting inside a word.

    Recursion always makes progress: each branch below only recurses on a
    strictly smaller piece than it received, and the final branch does not
    recurse at all — so this terminates for any input.
    """
    text = text.strip()
    if not text:
        return []
    if _fits(text, max_tokens):
        return [text]

    sentences = split_into_sentences(text)
    if len(sentences) > 1:
        return [p for s in sentences for p in _hard_split_text(s, max_tokens)]

    clauses = split_into_clauses(text)
    if len(clauses) > 1:
        return [p for c in clauses for p in _hard_split_text(c, max_tokens)]

    groups = split_into_word_groups(text, max_words=max(1, max_tokens))
    if len(groups) > 1:
        return [p for g in groups for p in _hard_split_text(g, max_tokens)]

    words = text.split()
    if len(words) > 1:
        return [p for w in words for p in _hard_split_text(w, max_tokens)]

    # A single word that still does not fit: the true last resort.
    return list(grapheme_safe_split(text, max_chars=_HARD_SPLIT_CHAR_THRESHOLD))


# --------------------------------------------------------------------------
# Merging short chunks within a section
# --------------------------------------------------------------------------


def _merge_short_siblings(chunks: list[Chunk], options: ChunkingOptions) -> list[Chunk]:
    """Fold a chunk below the floor into its next sibling, within a section.

    The ceiling always wins when the two constraints conflict: a merge that
    would exceed ``max_tokens`` is skipped, even if that leaves the chunk
    below the floor and it is not the section's last chunk. This is
    unavoidable, not a shortcut — IR-110 makes the ceiling a guarantee, and
    a short chunk whose only neighbour is already near-full has no grouping
    that satisfies both constraints (see the regression test for a worked
    example: 1 + 20 tokens under a 20-token ceiling cannot merge, whichever
    order they are considered in).
    """
    if not options.merge_short_siblings or len(chunks) <= 1:
        return list(chunks)

    floor = options.effective_min_tokens
    result: list[Chunk] = []
    pending = chunks[0]

    for nxt in chunks[1:]:
        combined_content = pending.content + " " + nxt.content
        if (
            pending.token_count < floor
            and count_tokens(combined_content) <= options.max_tokens
        ):
            pending = Chunk(
                text=combined_content,
                content=combined_content,
                context_path=pending.context_path,
                sequence=0,
                token_count=count_tokens(combined_content),
                source_page=(
                    pending.source_page
                    if pending.source_page is not None
                    else nxt.source_page
                ),
                element_kinds=pending.element_kinds | nxt.element_kinds,
                bboxes=dedupe_regions(pending.bboxes + nxt.bboxes),
            )
        else:
            result.append(pending)
            pending = nxt

    result.append(pending)
    return result
