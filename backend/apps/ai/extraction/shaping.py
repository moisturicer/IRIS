"""Shape a stored LlamaParse result without I/O (ADR-056, IR-840).

The adapter stores its downloaded grounding pages under ``grounded_items``.
Use those items when present: their line boxes are more precise than the
coarse boxes in the expanded result. Never infer labels from page position,
repetition, numbering or the file name.
"""

from dataclasses import replace
from typing import Any, Mapping

from apps.ai.chunking.document import BoundingBox, DocumentElement, NormalizedDocument
from apps.ai.chunking.formulas import DISPLAY_FORMULA


_KINDS = {"heading", "text", "list", "table", "image", "code", "link", "header", "footer"}


def shape_llamaparse(raw: Mapping[str, Any]) -> NormalizedDocument:
    """Turn one raw result, including downloaded grounding, into IRIS values."""
    metadata = {p["page_number"]: p for p in (raw.get("metadata") or {}).get("pages", []) or []}
    grounded = {p["page_number"]: p for p in raw.get("grounded_items", []) or []}
    elements = []
    sizes = {}
    for page in (raw.get("items") or {}).get("pages", []) or []:
        number = page["page_number"]
        sizes[number] = (float(page["page_width"]), float(page["page_height"]))
        evidence_page = grounded.get(number, page)
        if evidence_page.get("success") is False or evidence_page.get("items") is None:
            evidence_page = page
        for item in evidence_page.get("items", []) or []:
            if item.get("type") == "table" and item.get("merged_into_page"):
                continue
            elements.extend(_split_formulas(_element(item, number, metadata)))
    title = next((e.text for e in elements if e.kind == "heading" and e.level == 1 and e.page in (1, 2)), "")
    return NormalizedDocument(
        title=title, elements=tuple(elements), page_sizes=sizes,
        structure_is_authoritative=True, page_metadata=metadata,
        confidence=((raw.get("metadata") or {}).get("document") or {}).get("confidence"),
    )


def _element(item, page, metadata, *, nested=False):
    label = item.get("type", "")
    children = tuple(_element(child, page, metadata, nested=True) for child in item.get("items", []) or [])
    rows = tuple(tuple("" if cell is None else str(cell) for cell in row) for row in item.get("rows", []) or [])
    text = str(item.get("value", item.get("text", item.get("md", ""))) or "")
    ordered = item.get("ordered", False)
    if label == "table":
        text = "\n".join(" | ".join(row) for row in rows)
    elif label == "image":
        text = str(item.get("caption") or "")
    elif label == "list" and not text:
        text = _list_text(children, ordered)
    elif label in {"header", "footer"} and not text:
        text = "\n".join(child.text for child in children)
    element = DocumentElement(
        kind=label if label in _KINDS else "paragraph", text=text,
        level=item.get("level") if label == "heading" else None,
        page=page, bboxes=_boxes(item, page),
        printed_page_number=metadata.get(page, {}).get("printed_page_number"),
        source_label=label, children=children, ordered=ordered, rows=rows,
        html=str(item.get("html") or ""),
    )
    if nested and label == "text" and DISPLAY_FORMULA.search(text):
        element = replace(element, children=tuple(_split_formulas(element)))
    return element


def _list_text(children, ordered):
    lines: list[str] = []
    index = 0
    for child in children:
        if child.kind == "list":
            lines.extend("  " + line for line in child.text.splitlines())
        else:
            index += 1
            lines.append((f"{index}. " if ordered else "- ") + child.text)
    return "\n".join(lines)


def _split_formulas(element):
    if element.kind != "text":
        return [element]
    parts = []
    start = 0
    for match in DISPLAY_FORMULA.finditer(element.text):
        if match.start() > start:
            parts.append(replace(element, text=element.text[start:match.start()]))
        parts.append(replace(element, kind="formula", text=match.group("dollar") or match.group("bracket") or ""))
        start = match.end()
    if start < len(element.text) or not parts:
        parts.append(replace(element, text=element.text[start:]))
    return parts


def _boxes(item, page):
    lines = (item.get("grounding") or {}).get("lines", [])
    boxes = [line["bbox"] for line in lines if line.get("bbox")]
    if not boxes:
        boxes = item.get("bbox") or []
    if isinstance(boxes, dict):
        boxes = [boxes]
    pages = item.get("merged_from_pages") or []
    # The merged run keeps one original table box per source page. Explicit
    # page numbers always win; do not guess row coordinates from the grid.
    if len(pages) != len(boxes):
        pages = [page] * len(boxes)
    return tuple(BoundingBox(
        page=int(box.get("page_number", source_page)), left=float(box["x"]), top=float(box["y"]),
        right=float(box["x"]) + float(box["w"]), bottom=float(box["y"]) + float(box["h"]),
    ) for box, source_page in zip(boxes, pages))
