"""Shape a stored Unstructured result without I/O (ADR-067 decision 8, IR-986).

Heading depth comes from section numbering alone until IR-1057 adds the
PDF-evidence cascade. ``Address`` and ``EmailAddress`` are never emitted;
they stay only in the stored raw result.
"""

from collections import Counter
from dataclasses import replace
from html.parser import HTMLParser
from typing import Any, Mapping, Optional

from apps.ai.chunking.document import BoundingBox, DocumentElement, NormalizedDocument
from apps.ai.extraction.formulas import DISPLAY_FORMULA
from apps.ai.extraction.numbering import outline_depths
from apps.ai.extraction.ports import ExtractionError
from apps.ai.extraction.shaping import CAPTION, FRONT_MATTER, split_formulas

# hi_res renders a US Letter page at 2125x2750 px (IR-984 spike), i.e. 250 dpi.
RENDER_DPI = 250
# A Title the layout model is less sure of than this is text. hi_res does not
# return the field (ADR-067, 2026-11-14 amendment), so it applies only when present.
TITLE_MIN_PROBABILITY = 0.5
_SCALE = 72 / RENDER_DPI
_SECTION_LEVEL = 2
_KINDS = {
    "Title": "heading", "NarrativeText": "text", "UncategorizedText": "text",
    "FigureCaption": "text", "ListItem": "text", "Table": "table", "Image": "image",
    "Formula": "image", "CodeSnippet": "code",
    "Header": "header", "Footer": "footer", "PageNumber": "footer",
}
_PERSONAL = {"Address", "EmailAddress"}
_KNOWN = {*_KINDS, *_PERSONAL, "PageBreak", "CompositeElement"}


def shape_unstructured(raw: Any, pdf_evidence: Optional[Mapping] = None) -> NormalizedDocument:
    """Turn one stored result into IRIS values. ``pdf_evidence`` waits for IR-1057."""
    elements: list[DocumentElement] = []
    sizes: dict[int, tuple[float, float]] = {}
    breaks = 0
    for item in _items(raw):
        label = str(item.get("type") or "")
        if label == "CompositeElement":
            raise ExtractionError("CompositeElement: IRIS does not use Unstructured's chunking")
        if label == "PageBreak":
            breaks += 1
            continue
        metadata = item.get("metadata") or {}
        page = metadata.get("page_number") or breaks + 1
        if breaks and page <= breaks:
            raise ExtractionError(f"element on page {page} follows {breaks} page breaks")
        if label in _PERSONAL:
            continue
        elements.extend(_element(item, label, metadata, page, sizes))
    elements = _headings(_captions(_lists(_continued_tables(elements))))
    title = next((e.text for e in elements if e.kind == "heading" and e.level == 1), "")
    return NormalizedDocument(
        title=title, elements=tuple(elements), page_sizes=sizes, structure_is_authoritative=True,
    )


def unmapped_types(raw: Any) -> dict[str, int]:
    """Element types shaping does not know, each kept as a paragraph."""
    return dict(Counter(
        str(item.get("type") or "") for item in _items(raw) if item.get("type") not in _KNOWN
    ))


def _items(raw):
    return raw if isinstance(raw, list) else (raw.get("elements") or [])


def _element(item, label, metadata, page, sizes):
    languages = metadata.get("languages") or []
    text = str(item.get("text") or "")
    element = DocumentElement(
        kind=_KINDS.get(label, "paragraph"), text=text, page=page,
        bboxes=_boxes(metadata, page, sizes), source_label=label,
        element_id=str(item.get("element_id") or ""), language=languages[0] if languages else "",
    )
    if label == "Title":
        probability = metadata.get("detection_class_prob")
        if CAPTION.match(text.strip()) or (probability is not None and probability < TITLE_MIN_PROBABILITY):
            element = replace(element, kind="text")
    elif label == "Table":
        element = _table(element, str(metadata.get("text_as_html") or ""))
    elif label in {"Image", "Formula"}:
        latex = DISPLAY_FORMULA.fullmatch(text.strip()) if label == "Formula" else None
        if latex:
            return [replace(element, kind="formula", text=latex.group("dollar") or latex.group("bracket") or "")]
        # Image OCR is not a caption; Formula OCR is never the formula (ADR-067),
        # so it stays an image crop until it is transcribed.
        element = replace(element, text="", figure=element.element_id)
    return split_formulas(element)


def _lists(elements):
    """Consecutive list items form one list."""
    grouped: list[DocumentElement] = []
    for element in elements:
        if element.source_label != "ListItem":
            grouped.append(element)
            continue
        previous = grouped[-1] if grouped else None
        items = (*previous.children, element) if previous and previous.kind == "list" else (element,)
        listing = replace(
            items[0], kind="list", children=items, text="\n".join(f"- {i.text}" for i in items),
            bboxes=tuple(box for i in items for box in i.bboxes),
        )
        if len(items) > 1:
            grouped[-1] = listing
        else:
            grouped.append(listing)
    return grouped


def _captions(elements):
    """A FigureCaption beside an Image on its page becomes that Image's text."""
    bound: list[DocumentElement] = []
    index = 0
    while index < len(elements):
        pair = elements[index:index + 2]
        if len(pair) == 2 and _binds(*pair):
            bound.append(_bound(*pair))
            index += 2
        elif len(pair) == 2 and _binds(*reversed(pair)):
            bound.append(_bound(*reversed(pair)))
            index += 2
        else:
            bound.append(elements[index])
            index += 1
    return bound


def _bound(image, caption):
    """The caption's box comes first, so a citation highlights the caption."""
    return replace(image, text=caption.text, bboxes=caption.bboxes + image.bboxes)


def _binds(image, caption):
    return (
        image is not None and caption is not None and image.source_label == "Image"
        and image.kind == "image" and not image.text
        and caption.source_label == "FigureCaption" and caption.page == image.page
    )


def _continued_tables(elements):
    """Join a table that opens a page onto the table that ended the page before
    when their column counts match: hi_res splits tables at page breaks (IR-1101)."""
    joined: list[DocumentElement] = []
    last = None  # index in ``joined`` of the last body element
    for element in elements:
        previous = joined[last] if last is not None else None
        if (element.kind == "table" and previous is not None and previous.kind == "table"
                and element.page == (previous.page or 0) + 1 and _columns(element) == _columns(previous) > 0):
            rows = previous.rows + element.rows
            joined[last] = replace(
                previous, rows=rows, bboxes=previous.bboxes + element.bboxes,
                html=(previous.html or "") + (element.html or ""),
                text="\n".join(" | ".join(row) for row in rows),
            )
            continue
        joined.append(element)
        if element.kind not in {"header", "footer"}:
            last = len(joined) - 1
    return joined


def _columns(table):
    return len(table.rows[0]) if table.rows and all(len(r) == len(table.rows[0]) for r in table.rows) else 0


def _table(element, html):
    """Rows from the table's HTML; split tables are joined by ``_continued_tables``."""
    if not html:
        return element
    parser = _TableRows()
    parser.feed(html)
    rows = tuple(tuple(row) for row in parser.rows if row)
    return replace(element, rows=rows, html=html, text="\n".join(" | ".join(row) for row in rows))


class _TableRows(HTMLParser):
    """Cell text per ``<tr>``; a colspan pads with empty cells to keep columns."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._cell: Optional[list[str]] = None
        self._span = 1

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.rows.append([])
        elif tag in {"td", "th"} and self.rows:
            self._cell = []
            try:
                self._span = max(1, int(dict(attrs).get("colspan") or 1))
            except ValueError:
                self._span = 1

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self._cell is not None:
            self.rows[-1].extend([" ".join("".join(self._cell).split())] + [""] * (self._span - 1))
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _headings(elements):
    """Numbered headings nest under the paper's title; others claim no depth."""
    headings = [i for i, e in enumerate(elements) if e.kind == "heading"]
    depths = outline_depths([elements[i].text for i in headings])
    for i, depth in zip(headings, depths):
        if depth is not None:
            elements[i] = replace(elements[i], level=_SECTION_LEVEL + depth - 1)
    first = headings[0] if headings else None
    if first is not None and depths[0] is None and elements[first].page == 1 \
            and not FRONT_MATTER.match(elements[first].text.strip()):
        elements[first] = replace(elements[first], level=1)
    return elements


def element_boxes(metadata: Mapping, page: int) -> tuple[BoundingBox, ...]:
    """One raw element's boxes in top-left page points."""
    return _boxes(metadata, page, {})


def _boxes(metadata, page, sizes):
    """Pixel corners to top-left page points, clamped to the page."""
    coordinates = metadata.get("coordinates")
    if not coordinates:
        return ()
    if isinstance(coordinates, Mapping):
        coordinates = [dict(coordinates, page_number=page)]
    boxes = []
    for region in coordinates:
        if region.get("system", "PixelSpace") != "PixelSpace":
            raise ExtractionError(f"unsupported coordinate system {region.get('system')}")
        number = int(region.get("page_number") or page)
        width = float(region["layout_width"]) * _SCALE
        height = float(region["layout_height"]) * _SCALE
        sizes.setdefault(number, (round(width, 3), round(height, 3)))
        xs = [float(x) * _SCALE for x, _ in region["points"]]
        ys = [float(y) * _SCALE for _, y in region["points"]]
        boxes.append(BoundingBox(
            page=number, left=max(0.0, min(xs)), top=max(0.0, min(ys)),
            right=min(width, max(xs)), bottom=min(height, max(ys)),
        ))
    return tuple(boxes)
