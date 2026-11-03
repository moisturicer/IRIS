"""Shape a stored LlamaParse result without I/O (ADR-056, IR-840).

The adapter stores its downloaded grounding pages under ``grounded_items``.
Use those items when present: their line boxes are more precise than the
coarse boxes in the expanded result. Never infer labels from page position,
repetition or the file name. Two heading repairs are kept (IR-859): section
numbering sets heading depth, and a caption labelled a heading becomes text.
"""

import re
from collections import Counter
from dataclasses import replace
from pathlib import PurePosixPath
from typing import Any, Mapping
from urllib.parse import urlparse

from apps.ai.chunking.document import BoundingBox, DocumentElement, NormalizedDocument
from apps.ai.chunking.formulas import DISPLAY_FORMULA
from apps.ai.chunking.numbering import outline_depths
from apps.ai.chunking.regions import dedupe_regions


_KINDS = {"heading", "text", "list", "table", "image", "code", "link", "header", "footer"}
# "Table 1:", "TABLE I:", "Fig. 3", but not "Table of Contents" or "TABLES".
_CAPTION = re.compile(r"^(?:(?i:table|figure)(?![A-Za-z])|(?i:tab|fig)\.)\s*(?:\d+|[IVXLC]+|[A-Z]\d*)\b")
_FRONT_MATTER = re.compile(r"^(abstract|keywords|contents|table of contents|summary|a preprint)\b", re.IGNORECASE)


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
        start = len(elements)
        for item in evidence_page.get("items", []) or []:
            if item.get("type") == "table" and item.get("merged_into_page"):
                continue
            elements.extend(_split_formulas(_element(item, number, metadata)))
        if evidence_page is not page:
            elements[start:] = _named_images(elements[start:], page)
    elements = _repair_headings(elements)
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
    boxes = _boxes(item, page)
    child_boxes = tuple(box for child in children for box in child.bboxes)
    if child_boxes and not (item.get("grounding") or {}).get("lines"):
        boxes = dedupe_regions(child_boxes)
    element = DocumentElement(
        kind=label if label in _KINDS else "paragraph", text=text,
        level=item.get("level") if label == "heading" else None,
        page=page, bboxes=boxes,
        printed_page_number=metadata.get(page, {}).get("printed_page_number"),
        source_label=label, children=children, ordered=ordered, rows=rows,
        html=str(item.get("html") or ""),
        figure=_image_name(item) if label == "image" else "",
    )
    if nested and label == "text" and DISPLAY_FORMULA.search(text):
        element = replace(element, children=tuple(_split_formulas(element)))
    return element


def _named_images(elements, page):
    """Grounded items may omit an image's url; take it from the page's image
    items, in order, so a stored Figure still joins its element (IR-852)."""
    names = iter([_image_name(item) for item in page.get("items", []) or [] if item.get("type") == "image"])
    named = []
    for element in elements:
        if element.kind == "image":
            name = next(names, "")
            element = element if element.figure else replace(element, figure=name)
        named.append(element)
    return named


def _image_name(item):
    """The image's filename, as the adapter stores its Figure under (IR-852)."""
    return PurePosixPath(urlparse(str(item.get("url") or "")).path).name


def _repair_headings(elements):
    """Captions become text, the title heads the paper, and section numbering
    sets heading depth (IR-859)."""
    elements = [
        replace(e, kind="text", level=None) if e.kind == "heading" and _CAPTION.match(e.text.strip()) else e
        for e in elements
    ]
    headings = [i for i, e in enumerate(elements) if e.kind == "heading"]
    depths = dict(zip(headings, outline_depths([elements[i].text for i in headings])))
    top_levels = [elements[i].level for i in headings if depths[i] == 1 and elements[i].level is not None]
    if not top_levels:
        return elements
    counts = Counter(top_levels)
    section_level = max(counts, key=lambda level: (counts[level], -level))
    title = _title(elements, headings, depths)
    if title is not None:
        elements[title] = replace(elements[title], level=1)
        section_level = max(section_level, 2)
    open_level = None
    for i in headings:
        element = elements[i]
        if i == title:
            continue
        if depths[i] is not None:
            level = open_level = section_level + depths[i] - 1
        elif element.level is None:
            continue
        elif open_level is None or element.level <= section_level:
            # Front matter, or an unnumbered peer of the sections.
            level = open_level = section_level
        else:
            level = open_level + 1
        elements[i] = replace(element, level=level)
    return elements


def _title(elements, headings, depths):
    """The heading that names the paper: a level-one heading early on, else an
    unnumbered first heading on page 1 that is not front matter."""
    first_numbered = next((i for i in headings if depths[i] is not None), len(elements))
    front = [i for i in headings if i < first_numbered]
    named = next((i for i in front if elements[i].level == 1 and elements[i].page in (1, 2)), None)
    if named is not None:
        return named
    if front and front[0] == headings[0] and elements[front[0]].page == 1 \
            and not _FRONT_MATTER.match(elements[front[0]].text.strip()):
        return front[0]
    return None


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
