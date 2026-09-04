"""Docling's document JSON, translated into the document IRIS owns.

This module is the whole reason ``apps.ai.chunking.document`` can promise
that swapping extractors changes an adapter rather than the domain. Every
Docling-specific name — ``self_ref``, ``prov``, ``coord_origin``,
``column_header`` — is spent here and appears nowhere downstream.

Pure: a dict in, a ``NormalizedDocument`` out. No Django, no network, no
clock. That is what lets the judgement calls below (reading order, table
shape, coordinate origin) be tested with a literal and an assertion.

Three of those calls are worth stating up front:

**Reading order comes from ``body.children``, not from array order.** The
``texts`` array is storage order, which is close to reading order and not the
same as it — a multi-column page or a floated caption is enough to separate
them. The chunker splits on adjacency, so order is not cosmetic here: two
elements that are neighbours in the wrong order produce a chunk that reads as
nonsense and embeds as one.

**A label outside the known set is carried through as its own kind**, per the
promise in ``document.py``. It also does real work: it keeps ``page_header``
and ``page_footer`` distinguishable, which is what the normalizer stage
(still to be written) needs in order to drop running headers without
guessing at them from the text.

**Regions are stored top-left**, converted here rather than at render time.
Docling emits either origin; PDF.js viewports are top-left. Normalizing at
the one place that knows the page height means no later consumer can forget.
"""

from typing import Any, Iterator, Mapping, Optional

from apps.ai.chunking.document import (
    CAPTION,
    HEADING,
    LIST_ITEM,
    PARAGRAPH,
    TABLE_HEADER,
    TABLE_ROW,
    BoundingBox,
    DocumentElement,
    NormalizedDocument,
)

# Docling label → the kind the chunker splits on. A label absent from this
# map is not an error: it is carried through unchanged (see module docstring).
_LABEL_KINDS: Mapping[str, str] = {
    "title": HEADING,
    "section_header": HEADING,
    "text": PARAGRAPH,
    "paragraph": PARAGRAPH,
    "list_item": LIST_ITEM,
    "caption": CAPTION,
}

# US Letter. Only ever used to convert a bottom-left region on a page Docling
# described a provenance for but not a size — rare, and a wrong page height
# costs a slightly misplaced highlight rather than a lost element.
_DEFAULT_PAGE_HEIGHT = 792.0

_TITLE_LABEL = "title"

# Docling's table-shaped labels. ``document_index`` is a table of contents,
# which Docling emits with the same cell structure as a table.
_TABLE_LABELS = frozenset({"table", "document_index"})


def normalized_document_from_docling(
    payload: Mapping[str, Any], *, fallback_title: str = ""
) -> NormalizedDocument:
    """Translate one serialized ``DoclingDocument`` into a
    ``NormalizedDocument``.

    ``fallback_title`` is used only when the payload names the document
    nothing at all — in practice, the uploaded filename.
    """
    page_sizes = _page_sizes(payload.get("pages"))
    items = _items_in_reading_order(payload)

    elements: list[DocumentElement] = []
    title = ""
    for item in items:
        if not title and item.get("label") == _TITLE_LABEL:
            title = (item.get("text") or "").strip()
        elements.extend(_elements_for(item, page_sizes))

    return NormalizedDocument(
        title=title or (payload.get("name") or "").strip() or fallback_title,
        elements=tuple(elements),
        page_sizes=page_sizes,
    )


# ---------------------------------------------------------------------------
# Reading order
# ---------------------------------------------------------------------------


def _items_in_reading_order(payload: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    """Walk ``body.children`` depth-first, resolving each ``$ref``.

    Falls back to array order when there is no body to walk — a payload from
    an older docling-serve, or a hand-written fixture. That order is usually
    right and always better than dropping the document.
    """
    by_ref = _index_by_ref(payload)
    body = payload.get("body")
    children = body.get("children") if isinstance(body, Mapping) else None

    if not children:
        yield from _in_array_order(payload)
        return

    seen: set[str] = set()
    yield from _walk(children, by_ref, seen)


def _index_by_ref(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    index: dict[str, Mapping[str, Any]] = {}
    for key in ("texts", "tables", "pictures", "groups"):
        for position, item in enumerate(payload.get(key) or []):
            if not isinstance(item, Mapping):
                continue
            index[item.get("self_ref") or f"#/{key}/{position}"] = item
    return index


def _walk(
    children: Any, by_ref: Mapping[str, Mapping[str, Any]], seen: set[str]
) -> Iterator[Mapping[str, Any]]:
    if not isinstance(children, list):
        return
    for child in children:
        ref = child.get("$ref") if isinstance(child, Mapping) else None
        if not ref or ref in seen:
            continue
        seen.add(ref)
        item = by_ref.get(ref)
        if item is None:
            # A dangling ref. Skipping it loses one element; raising would
            # lose the whole document.
            continue
        if ref.startswith("#/groups/"):
            # A group is a container — a list, a chapter — with no text of
            # its own. Its children are the content.
            yield from _walk(item.get("children"), by_ref, seen)
            continue
        yield item


def _in_array_order(payload: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    for key in ("texts", "tables"):
        for item in payload.get(key) or []:
            if isinstance(item, Mapping):
                yield item


# ---------------------------------------------------------------------------
# Elements
# ---------------------------------------------------------------------------


def _elements_for(
    item: Mapping[str, Any], page_sizes: Mapping[int, tuple[float, float]]
) -> list[DocumentElement]:
    if _is_table(item):
        return _table_elements(item, page_sizes)

    text = (item.get("text") or "").strip()
    if not text:
        return []

    label = item.get("label") or "text"
    page, bbox = _region(item.get("prov"), page_sizes)
    return [
        DocumentElement(
            kind=_LABEL_KINDS.get(label, label),
            text=text,
            level=_level(item, label),
            page=page,
            bbox=bbox,
        )
    ]


def _is_table(item: Mapping[str, Any]) -> bool:
    """Table by label, or by carrying table cells.

    The cell check is a safety net for a table whose label Docling changes or
    omits. It looks for ``table_cells`` specifically rather than for a ``data``
    key: routing on ``data`` alone would send any future text item that
    happens to carry one into table handling, which returns nothing — and the
    element would vanish with no error anywhere.
    """
    if item.get("label") in _TABLE_LABELS:
        return True
    data = item.get("data")
    return isinstance(data, Mapping) and "table_cells" in data


def _level(item: Mapping[str, Any], label: str) -> Optional[int]:
    if label == _TITLE_LABEL:
        # The document's own title is its top heading. Without a level the
        # context path has no root to hang the rest of the document from.
        return 1
    level = item.get("level")
    return level if isinstance(level, int) else None


def _table_elements(
    item: Mapping[str, Any], page_sizes: Mapping[int, tuple[float, float]]
) -> list[DocumentElement]:
    """One element per table row, header rows first.

    Emitted as contiguous ``TABLE_HEADER``/``TABLE_ROW`` elements because
    that is what the structural chunker's table handling reads: it treats a
    run of them as one table and repeats the header on every fragment.
    """
    data = item.get("data")
    cells = data.get("table_cells") if isinstance(data, Mapping) else None
    if not cells:
        return []

    table_page, table_bbox = _region(item.get("prov"), page_sizes)

    rows: dict[int, list[Mapping[str, Any]]] = {}
    header_rows: set[int] = set()
    for cell in cells:
        if not isinstance(cell, Mapping):
            continue
        row_index = cell.get("start_row_offset_idx")
        if not isinstance(row_index, int):
            continue
        rows.setdefault(row_index, []).append(cell)
        if cell.get("column_header"):
            header_rows.add(row_index)

    elements: list[DocumentElement] = []
    for row_index in sorted(rows):
        row_cells = sorted(rows[row_index], key=lambda c: c.get("start_col_offset_idx") or 0)
        texts = [(c.get("text") or "").strip() for c in row_cells]
        if not any(texts):
            continue

        bbox = _row_bbox(row_cells, table_page, page_sizes) or table_bbox
        elements.append(
            DocumentElement(
                kind=TABLE_HEADER if row_index in header_rows else TABLE_ROW,
                text="| " + " | ".join(t for t in texts if t) + " |",
                page=table_page if bbox is None else bbox.page,
                bbox=bbox,
            )
        )
    return elements


def _row_bbox(
    row_cells: list[Mapping[str, Any]],
    table_page: Optional[int],
    page_sizes: Mapping[int, tuple[float, float]],
) -> Optional[BoundingBox]:
    """The union of a row's own cell regions.

    Worth the arithmetic: falling back to the table's box highlights forty
    rows to cite one, which is the difference between a citation a reader can
    check and a gesture at the right page.
    """
    boxes = [
        box
        for cell in row_cells
        if (box := _bbox(cell.get("bbox"), table_page, page_sizes)) is not None
    ]
    if not boxes:
        return None
    return BoundingBox(
        page=boxes[0].page,
        left=min(b.left for b in boxes),
        top=min(b.top for b in boxes),
        right=max(b.right for b in boxes),
        bottom=max(b.bottom for b in boxes),
    )


# ---------------------------------------------------------------------------
# Pages and regions
# ---------------------------------------------------------------------------


def _page_sizes(pages: Any) -> dict[int, tuple[float, float]]:
    sizes: dict[int, tuple[float, float]] = {}
    if not isinstance(pages, Mapping):
        return sizes
    for key, page in pages.items():
        size = page.get("size") if isinstance(page, Mapping) else None
        if not isinstance(size, Mapping):
            continue
        try:
            sizes[int(key)] = (float(size["width"]), float(size["height"]))
        except (KeyError, TypeError, ValueError):
            continue
    return sizes


def _region(
    prov: Any, page_sizes: Mapping[int, tuple[float, float]]
) -> tuple[Optional[int], Optional[BoundingBox]]:
    """The first provenance entry's page and region.

    First rather than all: ``DocumentElement`` holds one region, and an
    element with several is one that straddles a page break — rare enough at
    element level that keeping the first is honest. Chunks accumulate the
    regions of every element they were built from, which is where a
    multi-region citation actually comes from.
    """
    if not isinstance(prov, list) or not prov:
        return None, None
    first = prov[0]
    if not isinstance(first, Mapping):
        return None, None

    page = first.get("page_no")
    page = page if isinstance(page, int) else None
    return page, _bbox(first.get("bbox"), page, page_sizes)


def _bbox(
    raw: Any, page: Optional[int], page_sizes: Mapping[int, tuple[float, float]]
) -> Optional[BoundingBox]:
    """Convert one Docling bbox to a top-left ``BoundingBox``.

    Returns ``None`` for a degenerate rect rather than a zero-area box: a
    stored zero-area region is a highlight that renders as nothing and reads
    as a bug every time someone finds it.
    """
    if not isinstance(raw, Mapping) or page is None:
        return None
    try:
        left = float(raw["l"])
        top = float(raw["t"])
        right = float(raw["r"])
        bottom = float(raw["b"])
    except (KeyError, TypeError, ValueError):
        return None

    if raw.get("coord_origin") == "BOTTOMLEFT":
        height = page_sizes.get(page, (0.0, _DEFAULT_PAGE_HEIGHT))[1]
        top, bottom = height - top, height - bottom

    if right <= left or bottom <= top:
        return None
    return BoundingBox(page=page, left=left, top=top, right=right, bottom=bottom)
