"""Chunk authoritative structure at its declared heading depth (IR-840).

Headings open sections at their declared level. Formulas are shown to readers
and never embedded. Tables split only between rows and repeat their header.
Prose packs to the target size with its trail counted in; a figure, a list or
a table row is kept whole up to the safety ceiling (ADR-067 decision 14).
"""

from dataclasses import replace
from html import escape
import hashlib
import json

from ..assembly import Draft, Joiners, body_budget, finalize, fold_heading_only, merge_short_siblings
from ..document import FORMULA, HEADING, DocumentElement, NormalizedDocument
from apps.ai.extraction.formulas import without_formulas
from ..hashing import chunkset_hash
from ..outline import HeadingStack, bounded_trail, embedded_text
from ..regions import dedupe_regions
from ..registry import register_chunker
from ..table_html import TableHTML
from ..text_splitting import split_to_fit
from ..tokens import count_tokens
from ..values import ChunkingOptions, ChunkSet


STRATEGY_ID = "labeled-structure-v1"

_PROSE = {HEADING, "text", "paragraph", "code", "link"}
_ATOMS = frozenset({"table", "image"})
_JOINERS = Joiners(body="\n", content="\n\n")


@register_chunker(STRATEGY_ID)
class LabeledStructureChunker:
    """Headings open sections at their declared depth. Math is display only."""

    def chunk(self, document: NormalizedDocument, options: ChunkingOptions) -> ChunkSet:
        stack = HeadingStack(document.title)
        drafts: list[Draft] = []
        section: list[DocumentElement] = []

        def flush() -> None:
            if section:
                key = stack.path
                trail = bounded_trail(tuple(without_formulas(t).strip() for t in key), options)
                drafts.extend(_pack_section(section, trail, key, options))

        for element in document.elements:
            if not _has_content(element):
                continue
            if element.kind == HEADING:
                flush()
                section = []
                stack.push(element)
            section.append(element)
        flush()

        def fits(draft: Draft) -> bool:
            return count_tokens(embedded_text(draft.trail, draft.body)) <= options.effective_target_tokens

        # A Figure or Table is its own retrievable unit (IR-852): never merged.
        drafts = merge_short_siblings(
            drafts, options, lambda d: fits(d) and not d.element_kinds & _ATOMS, _JOINERS
        )
        drafts = fold_heading_only(drafts, options, fits, _JOINERS)
        return finalize(
            drafts,
            strategy_id=STRATEGY_ID,
            options=options,
            page_sizes=document.page_sizes,
            content_hash=lambda chunks: _content_hash(chunks, document.page_sizes),
        )


def _has_content(element: DocumentElement) -> bool:
    return bool(element.text.split() or element.description.split() or element.rows)


def _body(elements) -> str:
    return "\n".join(
        without_formulas(e.text + ("\n" + e.description if e.kind == "image" and e.description else ""))
        for e in elements if e.kind != FORMULA
    ).strip()


def _fits(elements, trail, limit) -> bool:
    return count_tokens(embedded_text(trail, _body(elements))) <= limit


def _pack_section(elements, trail, key, options) -> list[Draft]:
    target = options.effective_target_tokens
    drafts: list[Draft] = []
    window: list[DocumentElement] = []
    for element in elements:
        if element.kind in {"table", "image"}:
            if window:
                drafts.append(_draft(window, trail, key))
                window = []
            parts = _table_parts(element, trail, target) if element.kind == "table" else [element]
            drafts.extend(_draft([part], trail, key) for part in parts)
        else:
            for part in _prose_parts(element, trail, options):
                if window and not _fits(window + [part], trail, target):
                    drafts.append(_draft(window, trail, key))
                    window = []
                window.append(part)
    if window:
        drafts.append(_draft(window, trail, key))
    return [split for d in drafts for split in _within_ceiling(d, options)]


def _prose_parts(element, trail, options):
    target = options.effective_target_tokens
    if element.kind not in _PROSE or _fits([element], trail, target):
        return [element]
    pieces = split_to_fit(element.text, body_budget(trail, options))
    parts: list[DocumentElement] = []
    current = ""
    for piece in pieces:
        candidate = f"{current} {piece}".strip()
        if current and not _fits([replace(element, text=candidate)], trail, target):
            parts.append(replace(element, text=current))
            candidate = piece
        current = candidate
    if current:
        parts.append(replace(element, text=current))
    return parts


def _within_ceiling(draft: Draft, options: ChunkingOptions) -> list[Draft]:
    """A kept-whole atom past the safety ceiling is split as plain text.
    Its display form (table HTML, formulas) is lost; only for pathological
    atoms."""
    if count_tokens(embedded_text(draft.trail, draft.body)) <= options.max_tokens:
        return [draft]
    budget = body_budget(draft.trail, options, options.max_tokens)
    return [
        replace(draft, body=piece, content=piece)
        for piece in split_to_fit(draft.body, budget)
    ]


def _table_parts(table, trail, target):
    if _fits([table], trail, target) or len(table.rows) < 2:
        return [table]
    layout = TableHTML.parse(table.html, table.rows)
    parts = []
    start = 1
    for stop in range(2, len(table.rows) + 1):
        candidate = _table_fragment(table, start, stop, layout)
        if stop > start + 1 and not _fits([candidate], trail, target):
            parts.append(_table_fragment(table, start, stop - 1, layout))
            start = stop - 1
    parts.append(_table_fragment(table, start, len(table.rows), layout))
    return parts


def _table_fragment(table, start, stop, layout):
    def cells(row, tag):
        return "<tr>" + "".join(f"<{tag}>{escape(cell)}</{tag}>" for cell in row) + "</tr>"

    header = table.rows[0]
    rows = table.rows[start:stop]
    if layout is not None:
        html = layout.fragment(start, stop)
    else:
        html = "<table><thead>" + cells(header, "th") + "</thead><tbody>"
        html += "".join(cells(row, "td") for row in rows) + "</tbody></table>"
    return replace(table, rows=(header, *rows), html=html,
                   text="\n".join(" | ".join(row) for row in (header, *rows)))


def _draft(elements, trail, key) -> Draft:
    content = "\n\n".join(
        f"$$\n{e.text.strip()}\n$$" if e.kind == FORMULA else (e.html or e.text) if e.kind == "table" else e.text
        for e in elements
    ).strip()
    return Draft(
        body=_body(elements),
        content=content,
        trail=trail,
        section_key=key,
        source_page=elements[0].page,
        element_kinds=frozenset(e.kind for e in elements),
        bboxes=dedupe_regions(tuple(box for e in elements for box in e.bboxes)),
    )


def _content_hash(chunks, page_sizes):
    """Refresh display/evidence edits while reusing unchanged text vectors.

    Formulas, HTML and evidence do not enter embedding text, so the set hash
    also covers them. Per-chunk text hashes are unchanged.
    """
    payload = {
        "semantic": chunkset_hash(chunks), "page_sizes": page_sizes,
        "display": [{
            "content": chunk.content, "source_page": chunk.source_page,
            "element_kinds": sorted(chunk.element_kinds),
            "boxes": [(b.page, b.left, b.top, b.right, b.bottom) for b in chunk.bboxes],
        } for chunk in chunks],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
