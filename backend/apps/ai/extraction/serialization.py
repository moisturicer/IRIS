"""``NormalizedDocument`` to JSON and back.

The structured document is persisted as ``jsonb`` on ``PdfExtraction``
because it is read whole, by one consumer, and never queried field by field —
the same reasoning the design applies to a chunk's regions. A side table of
elements would add a join to every chunking run and buy nothing.

Round-tripping is the contract: ``document_from_json(document_to_json(d))``
must equal ``d``. Two things make that non-trivial and are handled here
rather than left to a caller to remember.

**JSON object keys are strings.** ``page_sizes`` is keyed by ``int``, so the
naive round trip returns ``{"1": ...}`` where ``{1: ...}`` went in, and every
page lookup afterwards silently misses.

**Optional fields are omitted, not written as null.** A thesis is thousands
of elements; writing four nulls each is a measurable fraction of the blob for
no information.

``version`` is written so a later format change is detectable rather than
merely wrong. Nothing reads it yet — that is deliberate, and it is a marker,
not a feature: the alternative is discovering the need for it on the day the
format changes, with a table full of unversioned rows.

Pure: no Django, no I/O, no clock.
"""

from typing import Any, Mapping

from apps.ai.chunking.document import BoundingBox, DocumentElement, NormalizedDocument

FORMAT_VERSION = 1


def document_to_json(document: NormalizedDocument) -> dict[str, Any]:
    """Return ``document`` as a JSON-serializable dict."""
    return {
        "version": FORMAT_VERSION,
        "title": document.title,
        "page_sizes": {
            str(page): [width, height] for page, (width, height) in document.page_sizes.items()
        },
        "elements": [_element_to_json(element) for element in document.elements],
    }


def document_from_json(data: Mapping[str, Any]) -> NormalizedDocument:
    """Rebuild a ``NormalizedDocument`` from ``document_to_json`` output."""
    return NormalizedDocument(
        title=data.get("title") or "",
        elements=tuple(_element_from_json(e) for e in data.get("elements") or []),
        page_sizes={
            int(page): (float(size[0]), float(size[1]))
            for page, size in (data.get("page_sizes") or {}).items()
        },
    )


def _element_to_json(element: DocumentElement) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": element.kind, "text": element.text}
    if element.level is not None:
        out["level"] = element.level
    if element.page is not None:
        out["page"] = element.page
    # An extractor emits at most one region per element, so the single-box
    # `bbox` key stays the wire format and every document written so far
    # still reads back unchanged. `bboxes` appears only for an element that
    # genuinely occupies several rectangles — which normalization can
    # produce by rejoining a word hyphenated across a page break.
    if len(element.bboxes) == 1:
        out["bbox"] = _bbox_to_json(element.bboxes[0])
    elif element.bboxes:
        out["bboxes"] = [_bbox_to_json(b) for b in element.bboxes]
    return out


def _bbox_to_json(bbox: BoundingBox) -> dict[str, Any]:
    # {page, rect} — the extraction's own wire format. Note this is NOT the
    # shape a chunk's stored regions use: ``repositories.serialize_regions``
    # writes four flat keys plus a ``degenerate`` flag. Two formats for one
    # value object is a wart, but they are written by different tickets into
    # different columns and unifying them would rewrite stored rows, so it
    # is recorded here rather than reconciled silently.
    return {
        "page": bbox.page,
        "rect": [bbox.left, bbox.top, bbox.right, bbox.bottom],
    }


def _element_from_json(data: Mapping[str, Any]) -> DocumentElement:
    bbox = data.get("bbox")
    bboxes = data.get("bboxes")
    if bboxes:
        regions = tuple(_bbox_from_json(b) for b in bboxes)
    else:
        regions = (_bbox_from_json(bbox),) if bbox else ()
    return DocumentElement(
        kind=data["kind"],
        text=data["text"],
        level=data.get("level"),
        page=data.get("page"),
        bboxes=regions,
    )


def _bbox_from_json(data: Mapping[str, Any]) -> BoundingBox:
    left, top, right, bottom = data["rect"]
    return BoundingBox(
        page=data["page"], left=left, top=top, right=right, bottom=bottom
    )
