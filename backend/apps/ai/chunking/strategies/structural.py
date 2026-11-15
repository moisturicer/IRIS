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

A transcribed formula (IR-1102) is shown as LaTeX and embedded, with its
description, only when ``index_formulas`` is on. With ``figure_passages``
(IR-1054) each Figure leaves the text flow for a passage of its own that
embeds its caption and description and shows only the caption.

With ``sibling_merge_floor`` (IR-1147) a passage under the floor merges
forward with the next section under the same parent heading (3.1 with 3.2,
never 3 with 4), up to the target, and carries the parent's path; a short
last section merges back. A Figure passage is never merged; a merge passes
over it.
"""

import hashlib
import json
from dataclasses import dataclass, replace

from ..assembly import (
    Draft,
    Joiners,
    body_budget,
    finalize,
    fold_heading_only,
    is_figure,
    merge_short_siblings,
    merge_sibling_sections,
)
from ..document import (
    FORMULA,
    LIST_ITEM,
    TABLE_HEADER,
    TABLE_ROW,
    DocumentElement,
    NormalizedDocument,
)
from ..hashing import chunkset_hash
from ..outline import HeadingStack, bounded_trail
from ..packing import JOIN, Piece, assembled_fits, pack_pieces, reader_form
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
            # A Figure passage is never folded into (IR-1054).
            return not is_figure(draft) and _fits(
                draft.body, body_budget(draft.trail, options))

        # Across sections, so it cannot live in _chunk_section (IR-241).
        drafts = fold_heading_only(drafts, options, fits, _JOINERS)
        drafts = merge_sibling_sections(
            drafts, options, _root(document.title, drafts), fits, _JOINERS,
            trail_for=lambda key: bounded_trail(key, options))
        return finalize(
            drafts, strategy_id=STRATEGY_ID, options=options, page_sizes=document.page_sizes,
            content_hash=lambda chunks: _set_hash(chunks, options),
        )


def _root(title: str, drafts: list[Draft]) -> tuple[str, ...]:
    """The path above every chapter: the title, or a heading every key starts with."""
    if title.strip():
        return (title.strip(),)
    firsts = {d.section_key[0] for d in drafts if d.section_key}
    return (firsts.pop(),) if len(firsts) == 1 else ()


def _set_hash(chunks, options: ChunkingOptions) -> str:
    """The set hash, covering shown text too once a set carries Figure passages
    or transcribed formulas, so a change only readers see is still saved.
    Every other set keeps the semantic hash, which ignores boxes and pages."""
    semantic = chunkset_hash(chunks)
    if not options.figure_passages and all(c.keyword_text is None for c in chunks):
        return semantic
    payload = {"semantic": semantic, "shown": [[c.content, c.keyword_text] for c in chunks]}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


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
    flow = section.elements
    figures: list[Draft] = []
    if options.figure_passages:
        flow = tuple(e for e in section.elements if e.kind != "image" or _formula_crop(e))
        figures = [d for e in section.elements if _citable_figure(e)
                   for d in _figure_drafts(e, section, options)]

    def text_of(element: DocumentElement) -> str:
        return _embedded(element, options)

    # An untranscribed formula stays in its paragraph as its crop: its box, never its text.
    elements = [e for e in flow if e.text.split() or _formula_crop(e)]
    if not elements:
        return figures

    budget = body_budget(section.trail, options)
    if _fits(" ".join(text_of(e) for e in elements), budget):
        windows = [[(text_of(e), e) for e in elements]]
    else:
        ceiling = body_budget(section.trail, options, options.max_tokens)
        windows = _split_structurally(elements, budget, ceiling, text_of)

    drafts = [_window_to_draft(w, section, options) for w in windows if w]
    merged = merge_short_siblings(drafts, options, lambda d: _fits(d.body, budget), _JOINERS)
    return merged + figures


def _transcribed(element: DocumentElement) -> bool:
    """A formula read from its crop (IR-1102), not one the Extractor typed."""
    return element.kind == FORMULA and element.source_label == "Formula"


def _formula_crop(element: DocumentElement) -> bool:
    return element.kind == "image" and element.source_label == "Formula"


def _embedded(element: DocumentElement, options: ChunkingOptions) -> str:
    if _formula_crop(element):
        return ""
    if not _transcribed(element):
        return element.text
    if not options.index_formulas:
        return ""
    return f"{element.text}\n{element.description}".strip()


def _shown(text: str, element: DocumentElement) -> str:
    if _formula_crop(element):
        return ""
    if _transcribed(element):
        return f"$$\n{element.text.strip()}\n$$"
    return reader_form(text, element)


def _citable_figure(element: DocumentElement) -> bool:
    # An untranscribed formula crop is an image too; it is never a Figure.
    return (element.kind == "image" and element.source_label != "Formula"
            and bool(element.text.strip() or element.description.strip()))


def _figure_drafts(element: DocumentElement, section: _Section, options: ChunkingOptions) -> list[Draft]:
    """A Figure kept whole up to the safety ceiling, split past it."""
    draft = _figure_draft(element, section)
    ceiling = body_budget(section.trail, options, options.max_tokens)
    if _fits(draft.body, ceiling):
        return [draft]
    return [replace(draft, body=piece) for piece in _hard_split_text(draft.body, ceiling)]


def _figure_draft(element: DocumentElement, section: _Section) -> Draft:
    caption = element.text.strip()
    return Draft(
        body="\n".join(p for p in (caption, element.description.strip()) if p),
        content=caption,
        trail=section.trail,
        section_key=section.key,
        source_page=element.page,
        element_kinds=frozenset({"image"}),
        bboxes=regions_for([element]),
    )


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
    elements: list[DocumentElement], max_tokens: int, ceiling: int, text_of=lambda e: e.text
) -> list[list[Piece]]:
    windows: list[list[Piece]] = []
    for kind, run in _iter_runs(elements):
        if kind == "table":
            windows.extend(_pack_table(run, max_tokens, ceiling))
        else:
            # Prose and list units pool when they fit; an oversized one is
            # hard-split and each fragment kept in its own chunk.
            windows.extend(_pack_atoms(run, max_tokens, text_of))
    return windows


def _window_to_draft(window: list[Piece], section: _Section, options: ChunkingOptions) -> Draft:
    elements = [element for _, element in window]
    pages = [e.page for e in elements if e.page is not None]
    return Draft(
        body=" ".join(text for text, _ in window if text),
        content=JOIN.join(s for s in (_shown(t, e) for t, e in window) if s).strip(),
        keyword=_keyword(window, options),
        trail=section.trail,
        section_key=section.key,
        source_page=pages[0] if pages else None,
        element_kinds=frozenset(e.kind for e in elements),
        bboxes=regions_for(elements),
    )


# --------------------------------------------------------------------------
# Prose and list runs — pool what fits, isolate what does not
# --------------------------------------------------------------------------


def _keyword(window: list[Piece], options: ChunkingOptions) -> str | None:
    """What the keyword index reads (IR-1102): a transcribed formula only when indexed."""
    if not any(_transcribed(e) for _, e in window):
        return None
    parts = []
    for text, element in window:
        if not _transcribed(element):
            parts.append(_shown(text, element))
        elif options.index_formulas:
            parts.append(f"{_shown(text, element)}\n{element.description}".strip())
    return JOIN.join(p for p in parts if p).strip()


def _pack_atoms(
    elements: list[DocumentElement], max_tokens: int, text_of=lambda e: e.text
) -> list[list[Piece]]:
    windows: list[list[Piece]] = []
    pool: list[Piece] = []

    def flush_pool() -> None:
        nonlocal pool
        if pool:
            windows.extend(pack_pieces(pool, max_tokens))
            pool = []

    for element in elements:
        text = text_of(element)
        if _fits(text, max_tokens):
            pool.append((text, element))
            continue

        flush_pool()
        for fragment in _hard_split_text(text, max_tokens):
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
