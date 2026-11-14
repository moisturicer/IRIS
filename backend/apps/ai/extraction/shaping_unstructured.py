"""Shape a stored Unstructured result without I/O (ADR-067 decision 8, IR-986).

Heading depth, printed page numbers and line-level citation boxes read IRIS's
own PDF evidence when it is given (IR-1057, ``evidence_rules``).
``Address`` and ``EmailAddress`` are never emitted; they stay only in the
stored raw result.
"""

from collections import Counter
from dataclasses import replace
from html.parser import HTMLParser
from typing import Any, Mapping, Optional

from apps.ai.chunking.document import BoundingBox, DocumentElement, NormalizedDocument
from apps.ai.extraction.formulas import DISPLAY_FORMULA
from apps.ai.extraction import evidence_rules
from apps.ai.extraction.ports import ExtractionError
from apps.ai.extraction.shaping import CAPTION, split_formulas

# hi_res renders a US Letter page at 2125x2750 px (IR-984 spike), i.e. 250 dpi.
RENDER_DPI = 250
# A Title the layout model is less sure of than this is text. hi_res does not
# return the field (ADR-067, 2026-11-14 amendment), so it applies only when present.
TITLE_MIN_PROBABILITY = 0.5
_SCALE = 72 / RENDER_DPI
_KINDS = {
    "Title": "heading", "NarrativeText": "text", "UncategorizedText": "text",
    "FigureCaption": "text", "ListItem": "text", "Table": "table", "Image": "image",
    "Formula": "image", "CodeSnippet": "code",
    "Header": "header", "Footer": "footer", "PageNumber": "footer",
}
_PERSONAL = {"Address", "EmailAddress"}
_KNOWN = {*_KINDS, *_PERSONAL, "PageBreak", "CompositeElement"}


# Element types whose box narrows to its text lines (ADR-067 decision 5).
_LINED = {"Title", "NarrativeText", "UncategorizedText", "FigureCaption", "ListItem"}


def shape_unstructured(raw: Any, pdf_evidence: Optional[Mapping] = None) -> NormalizedDocument:
    """Turn one stored result, and the PDF evidence beside it, into IRIS values."""
    return _shape(raw, pdf_evidence)[0]


def shaping_report(raw: Any, pdf_evidence: Optional[Mapping] = None) -> dict:
    """Which signal decided each heading, and how often line boxes matched."""
    document, outcomes = _shape(raw, pdf_evidence)
    headings = [(e.text, e.level, e.level_source) for e in document.elements if e.kind == "heading"]
    return {
        "headings": headings,
        "signals": dict(Counter(source for _, _, source in headings)),
        "line_boxes": dict(Counter(outcomes)),
        "printed_pages": sorted({e.page for e in document.elements if e.printed_page_number}),
    }


def _shape(raw, pdf_evidence):
    elements: list[DocumentElement] = []
    sizes: dict[int, tuple[float, float]] = {}
    parents: dict[str, str] = {}
    outcomes: list[str] = []
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
        if metadata.get("parent_id"):
            parents[str(item.get("element_id") or "")] = str(metadata["parent_id"])
        elements.extend(_element(item, label, metadata, page, sizes, pdf_evidence, outcomes))
    elements = evidence_rules.place_headings(_captions(_lists(elements)), pdf_evidence, parents)
    elements = _printed(elements, pdf_evidence, sizes)
    title = next((e.text for e in elements if e.kind == "heading" and e.level == 1), "")
    document = NormalizedDocument(
        title=title, elements=tuple(elements), page_sizes=sizes, structure_is_authoritative=True,
    )
    return document, outcomes


def _printed(elements, pdf_evidence, sizes):
    pages = {*sizes, *(e.page for e in elements if e.page)}
    count = (evidence_rules.usable(pdf_evidence) or {}).get("page_count") or 0
    printed = evidence_rules.printed_pages(elements, pdf_evidence, pages | set(range(1, count + 1)))
    return [replace(e, printed_page_number=printed[e.page]) if e.page in printed else e for e in elements]


def unmapped_types(raw: Any) -> dict[str, int]:
    """Element types shaping does not know, each kept as a paragraph."""
    return dict(Counter(
        str(item.get("type") or "") for item in _items(raw) if item.get("type") not in _KNOWN
    ))


def _items(raw):
    return raw if isinstance(raw, list) else (raw.get("elements") or [])


def _element(item, label, metadata, page, sizes, pdf_evidence, outcomes):
    languages = metadata.get("languages") or []
    text = str(item.get("text") or "")
    boxes = _boxes(metadata, page, sizes)
    if label in _LINED:
        boxes, outcome = evidence_rules.line_boxes(text, boxes, pdf_evidence)
        if outcome:
            outcomes.append(outcome)
    element = DocumentElement(
        kind=_KINDS.get(label, "paragraph"), text=text, page=page,
        bboxes=boxes, source_label=label,
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


def _table(element, html):
    """Rows from the table's HTML. Unstructured already joins a table split
    across pages into one element (IR-984), so no merge is built here."""
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
