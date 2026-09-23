"""Citation regions, as a reader's viewer can draw them (IR-334, ADR-031).

Chunks store rectangles in PDF points against a page size the client does not
have. This converts them to fractions of the page, so a viewer positions a
highlight from the numbers alone at any zoom.

Pure: no I/O, no Django.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class Region:
    """One highlightable rectangle, as a fraction of its page (0–1)."""

    page: int
    left: float
    top: float
    right: float
    bottom: float


def _clamp(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def _page_size(page_sizes: Mapping[Any, Any], page: int) -> tuple[float, float] | None:
    """The page's ``(width, height)``, whichever way its key is typed.

    Stored JSON keys are strings; a value built in memory keys by int.
    """
    size = page_sizes.get(str(page), page_sizes.get(page))
    if not isinstance(size, (list, tuple)) or len(size) < 2:
        return None
    try:
        width, height = float(size[0]), float(size[1])
    except (TypeError, ValueError):
        return None
    return (width, height) if width > 0 and height > 0 else None


def normalized_regions(
    bboxes: Sequence[Mapping[str, Any]] | None,
    page_sizes: Mapping[Any, Any] | None,
) -> tuple[Region, ...]:
    """The drawable regions among ``bboxes``, in reading order.

    Three kinds of rectangle are dropped rather than sent. A degenerate one
    has no area to draw; one on a page with no recorded size cannot be
    normalized without inventing that size; a malformed one is not a
    rectangle. Each would otherwise become a box in the wrong place, which is
    worse than no box — the page still travels separately as ``page``.
    """
    if not bboxes or not page_sizes:
        return ()

    regions: list[Region] = []
    for box in bboxes:
        if not isinstance(box, Mapping) or box.get("degenerate"):
            continue
        try:
            page = int(box["page"])
            left, top = float(box["left"]), float(box["top"])
            right, bottom = float(box["right"]), float(box["bottom"])
        except (KeyError, TypeError, ValueError):
            continue
        if right <= left or bottom <= top:
            continue

        size = _page_size(page_sizes, page)
        if size is None:
            continue
        width, height = size

        regions.append(
            Region(
                page=page,
                left=_clamp(left / width),
                top=_clamp(top / height),
                right=_clamp(right / width),
                bottom=_clamp(bottom / height),
            )
        )
    return tuple(regions)


def regions_wire(regions: Sequence[Region]) -> list[dict]:
    """Regions in the shape the API sends. Rounded: six decimals is finer
    than a pixel on any page, and keeps a response from carrying float noise."""
    return [
        {
            "page": r.page,
            "left": round(r.left, 6),
            "top": round(r.top, 6),
            "right": round(r.right, 6),
            "bottom": round(r.bottom, 6),
        }
        for r in regions
    ]
