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
    if element.bbox is not None:
        # {page, rect} rather than four keys: it is the shape the chunk's
        # own stored regions use, so one reader understands both.
        out["bbox"] = {
            "page": element.bbox.page,
            "rect": [
                element.bbox.left,
                element.bbox.top,
                element.bbox.right,
                element.bbox.bottom,
            ],
        }
    return out


def _element_from_json(data: Mapping[str, Any]) -> DocumentElement:
    bbox = data.get("bbox")
    return DocumentElement(
        kind=data["kind"],
        text=data["text"],
        level=data.get("level"),
        page=data.get("page"),
        bbox=_bbox_from_json(bbox) if bbox else None,
    )


def _bbox_from_json(data: Mapping[str, Any]) -> BoundingBox:
    left, top, right, bottom = data["rect"]
    return BoundingBox(
        page=data["page"], left=left, top=top, right=right, bottom=bottom
    )
