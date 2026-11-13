"""Structure-aware splitting cascade — the strategy the fixed-window baseline
(IR-110) is measured against on the eval set.

Five stages, each handling only what the one before it could not:

1. emit a section as-is if it fits the target size
2. split on heading boundaries (sectioning)
3. split structurally: table rows/headers, list items, paragraphs
4. split on sentence boundaries
5. hard split on grapheme clusters, backtracking to the nearest breakpoint

Two rules hold throughout: a table split across chunks repeats its header
row in every fragment, and a list never splits mid-item. Short chunks merge
with their next sibling within a heading section, and never across one.

One narrow exception to "never across one", added by IR-241: a chunk holding
*nothing but a heading* folds forward into the chunk that follows it. It is a
label rather than a topic, so folding it into the section it labels does not
put two topics in one vector. Two sections that both carry a body still never
merge.

Each section's heading trail is counted inside its budget (IR-1050), so the
embedded text, trail included, stays within the target.
"""

from dataclasses import dataclass

from ..assembly import (
    Draft,
    Joiners,
    body_budget,
    finalize,
    fold_heading_only,
    merge_short_siblings,
)
from ..document import (
    LIST_ITEM,
    TABLE_HEADER,
    TABLE_ROW,
    DocumentElement,
    NormalizedDocument,
)
from ..outline import HeadingStack, bounded_trail
from ..packing import Piece, assembled_fits, pack_pieces, reader_content
from ..regions import regions_for
from ..registry import register_chunker
from ..text_splitting import split_to_fit
from ..tokens import count_tokens
from ..values import ChunkingOptions, ChunkSet

STRATEGY_ID = "structural-markdown-v1"

# A whitespace-free run longer than this is hard-split whatever its token
# count: a safety net for degenerate input, not a realistic word.
_HARD_SPLIT_CHAR_THRESHOLD = 64

_JOINERS = Joiners(body=" ", content=" ")


@register_chunker(STRATEGY_ID)
class StructuralCascadeChunker:
    """Splits a document along its structure before ever falling back to a
    generic split. See the module docstring for the five-stage cascade."""

    def chunk(
        self, document: NormalizedDocument, options: ChunkingOptions
    ) -> ChunkSet:
        drafts: list[Draft] = []
        for section in _sectionize(document, options):
            drafts.extend(_chunk_section(section, options))

        def fits(draft: Draft) -> bool:
            return _fits(draft.body, body_budget(draft.trail, options))

        # Across sections, so it cannot live in _chunk_section (IR-241).
        drafts = fold_heading_only(drafts, options, fits, _JOINERS)
        return finalize(
            drafts, strategy_id=STRATEGY_ID, options=options, page_sizes=document.page_sizes
        )


def _fits(text: str, max_tokens: int) -> bool:
    """Under the budget, and no single run-on word past the char threshold."""
    return (
        count_tokens(text) <= max_tokens
        and max((len(w) for w in text.split()), default=0) <= _HARD_SPLIT_CHAR_THRESHOLD
    )


# --------------------------------------------------------------------------
# Sectioning — stage 2, heading boundaries
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Section:
    elements: tuple[DocumentElement, ...]
    trail: tuple[str, ...]
    key: tuple[str, ...]


def _sectionize(document: NormalizedDocument, options: ChunkingOptions) -> list[_Section]:
    stack = HeadingStack(document.title)
    sections: list[_Section] = []
    buffer: list[DocumentElement] = []

    def flush() -> None:
        if buffer:
            path = stack.path
            sections.append(_Section(tuple(buffer), bounded_trail(path, options), path))

    for element in document.elements:
        if element.is_heading:
            flush()
            buffer = []
            stack.push(element)
        buffer.append(element)
    flush()
    return sections


# --------------------------------------------------------------------------
# One section: stage 1, then stage 3 structural splitting, then merging
# --------------------------------------------------------------------------


def _chunk_section(section: _Section, options: ChunkingOptions) -> list[Draft]:
    elements = [e for e in section.elements if e.text.split()]
    if not elements:
        return []

    budget = body_budget(section.trail, options)
    if _fits(" ".join(e.text for e in elements), budget):
        windows = [[(e.text, e) for e in elements]]
    else:
        ceiling = body_budget(section.trail, options, options.max_tokens)
        windows = _split_structurally(elements, budget, ceiling)

    drafts = [_window_to_draft(w, section) for w in windows if w]
    return merge_short_siblings(drafts, options, lambda d: _fits(d.body, budget), _JOINERS)


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
    elements: list[DocumentElement], max_tokens: int, ceiling: int
) -> list[list[Piece]]:
    windows: list[list[Piece]] = []
    for kind, run in _iter_runs(elements):
        if kind == "table":
            windows.extend(_pack_table(run, max_tokens, ceiling))
        else:
            # Prose and list units pool when they fit; an oversized one is
            # hard-split and each fragment kept in its own chunk.
            windows.extend(_pack_atoms(run, max_tokens))
    return windows


def _window_to_draft(window: list[Piece], section: _Section) -> Draft:
    elements = [element for _, element in window]
    pages = [e.page for e in elements if e.page is not None]
    return Draft(
        body=" ".join(text for text, _ in window),
        content=reader_content(window),
        trail=section.trail,
        section_key=section.key,
        source_page=pages[0] if pages else None,
        element_kinds=frozenset(e.kind for e in elements),
        bboxes=regions_for(elements),
    )


# --------------------------------------------------------------------------
# Prose and list runs — pool what fits, isolate what does not
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


def _pack_table(
    elements: list[DocumentElement], max_tokens: int, ceiling: int
) -> list[list[Piece]]:
    """Rows packed to the target under a repeated header. A repeated header
    may carry a fragment past the target, never past the ceiling; a header
    with no room under the ceiling is chunked once, as prose."""
    headers = [e for e in elements if e.kind == TABLE_HEADER]
    rows = [e for e in elements if e.kind == TABLE_ROW]
    header_pieces: list[Piece] = [(h.text, h) for h in headers if h.text.split()]
    header_text = " ".join(t for t, _ in header_pieces)
    header_tokens = count_tokens(header_text)
    if header_pieces and rows and header_tokens + 1 >= ceiling:
        return _pack_atoms(headers, max_tokens) + _pack_atoms(rows, max_tokens)

    if not rows:
        return _pack_atoms(headers, max_tokens)

    windows: list[list[Piece]] = []
    current_rows: list[Piece] = []

    def flush() -> None:
        nonlocal current_rows
        if current_rows:
            windows.append(header_pieces + current_rows)
        current_rows = []

    for row in rows:
        if not _fits(f"{header_text} {row.text}".strip(), max_tokens):
            flush()
            budget = max_tokens - header_tokens
            if budget < 1:
                budget = max(1, min(max_tokens, ceiling - header_tokens - 1))
            for fragment in _hard_split_text(row.text, budget):
                windows.append(header_pieces + [(fragment, row)])
            continue

        # Counted as assembled, not summed (IR-287).
        window = [header_text, *(t for t, _ in current_rows), row.text]
        if current_rows and not assembled_fits(window, max_tokens):
            flush()
        current_rows.append((row.text, row))

    flush()
    return windows


def _hard_split_text(text: str, max_tokens: int) -> list[str]:
    """Stages 4 and 5: sentence, clause, word, then grapheme-safe split."""
    return split_to_fit(text, max_tokens, max_word_chars=_HARD_SPLIT_CHAR_THRESHOLD)
