"""Chunk authoritative structure without Docling's label repairs (IR-840)."""

from dataclasses import replace
from html import escape
import hashlib
import json

from ..context_path import _truncate_middle
from ..document import FORMULA, HEADING, DocumentElement, NormalizedDocument
from ..formulas import without_formulas
from ..hashing import chunkset_hash
from ..regions import dedupe_regions
from ..text_splitting import grapheme_safe_split, split_into_sentences
from ..table_html import TableHTML
from ..tokens import count_tokens
from ..values import Chunk, ChunkingOptions, ChunkSet


STRATEGY_ID = "labeled-structure-v1"


class LabeledStructureChunker:
    """Headings open sections at their declared depth. Math is display only."""

    def chunk(self, document: NormalizedDocument, options: ChunkingOptions) -> ChunkSet:
        chunks = []
        stack: list[tuple[int, str]] = []
        section: list[DocumentElement] = []
        path: tuple[str, ...] = (document.title,) if document.title else ()
        for element in document.elements:
            if element.kind == HEADING:
                if section:
                    chunks.extend(_pack_section(section, path, options))
                section = []
                level = element.level or 1
                stack = [(depth, text) for depth, text in stack if depth < level]
                stack.append((level, element.text))
                headings = tuple(text for _, text in stack)
                path = headings if headings[0] == document.title else ((document.title,) if document.title else ()) + headings
                path = _bounded_path(path, options)
            section.append(element)
        if section:
            chunks.extend(_pack_section(section, path, options))
        chunks = [replace(chunk, sequence=index) for index, chunk in enumerate(chunks)]
        return ChunkSet(
            chunks=tuple(chunks), strategy_id=STRATEGY_ID, options=options,
            content_hash=_content_hash(chunks, document.page_sizes), page_sizes=document.page_sizes,
        )


def _bounded_path(path, options):
    # Leave most of the total budget for the author's text, including the
    # separator. The legacy helper alone can retain an oversized first word.
    budget = min(options.context_path_max_tokens, options.max_tokens // 3)
    if budget < 1:
        return ()
    path = _truncate_middle(path, budget)
    if count_tokens(" > ".join(path)) <= budget:
        return path
    label = ""
    for cluster in grapheme_safe_split(path[0], 1):
        if count_tokens(label + cluster) > budget:
            break
        label += cluster
    return (label,) if label else ()


def _embedded(elements, path):
    body = "\n".join(
        without_formulas(e.text + ("\n" + e.description if e.kind == "image" and e.description else ""))
        for e in elements if e.kind != FORMULA
    ).strip()
    prefix = without_formulas(" > ".join(path)).strip()
    return f"{prefix}\n\n{body}" if prefix and body else prefix or body


def _fits(elements, path, options):
    return count_tokens(_embedded(elements, path)) <= options.max_tokens


def _pack_section(elements, path, options):
    chunks = []
    window: list[DocumentElement] = []
    for element in elements:
        if element.kind in {"table", "image"}:
            if window:
                chunks.append(_chunk(window, path))
                window = []
            parts = _table_parts(element, path, options) if element.kind == "table" else [element]
            chunks.extend(_chunk([part], path) for part in parts)
        else:
            for part in _prose_parts(element, path, options):
                if window and not _fits(window + [part], path, options):
                    chunks.append(_chunk(window, path))
                    window = []
                window.append(part)
    if window:
        chunks.append(_chunk(window, path))
    return chunks


def _prose_parts(element, path, options):
    if element.kind not in {HEADING, "text", "paragraph", "code", "link"} or _fits([element], path, options):
        return [element]
    atoms = []
    for sentence in split_into_sentences(element.text):
        if _fits([replace(element, text=sentence)], path, options):
            atoms.append(sentence)
        else:
            for word in sentence.split():
                atoms.extend(_word_parts(word, element, path, options))
    parts = []
    current = ""
    for atom in atoms:
        candidate = (current + " " + atom).strip()
        if current and not _fits([replace(element, text=candidate)], path, options):
            parts.append(replace(element, text=current))
            current = ""
        current = (current + " " + atom).strip()
    if current:
        parts.append(replace(element, text=current))
    return parts


def _word_parts(word, element, path, options):
    if _fits([replace(element, text=word)], path, options) or len(word) <= 1:
        return [word]
    pieces = grapheme_safe_split(word, max(1, len(word) // 2))
    if len(pieces) == 1:  # A single grapheme is indivisible too.
        return [word]
    return [part for piece in pieces for part in _word_parts(piece, element, path, options)]


def _table_parts(table, path, options):
    if _fits([table], path, options) or len(table.rows) < 2:
        return [table]
    layout = TableHTML.parse(table.html, table.rows)
    parts = []
    start = 1
    for stop in range(2, len(table.rows) + 1):
        candidate = _table_fragment(table, start, stop, layout)
        if stop > start + 1 and not _fits([candidate], path, options):
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


def _chunk(elements, path):
    text = _embedded(elements, path)
    content = "\n\n".join(
        f"$$\n{e.text.strip()}\n$$" if e.kind == FORMULA else (e.html or e.text) if e.kind == "table" else e.text
        for e in elements
    ).strip()
    return Chunk(
        text=text, content=content, context_path=path, sequence=0,
        token_count=count_tokens(text), source_page=elements[0].page,
        element_kinds=frozenset(e.kind for e in elements),
        bboxes=dedupe_regions(tuple(box for e in elements for box in e.bboxes)),
    )


def _content_hash(chunks, page_sizes):
    """Refresh display/evidence edits while reusing unchanged text vectors.

    Legacy strategies retain their pinned semantic-only set hash. This new
    strategy must also notice formulas, HTML and evidence, which deliberately
    do not enter embedding text. Per-chunk text hashes remain unchanged.
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
