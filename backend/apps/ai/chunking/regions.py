"""Assembling a chunk's citation regions from its source elements (IR-113).

One place, shared by every strategy, because "which rectangles does this
chunk occupy?" has one answer and a strategy that computed it differently
would produce citations that highlight differently for no reason a reader
could see.

Pure: no I/O, no clock, no randomness.
"""

from typing import Iterable

from .document import BoundingBox, DocumentElement


def dedupe_regions(boxes: Iterable[BoundingBox]) -> tuple[BoundingBox, ...]:
    """Return ``boxes`` in order, with repeats removed.

    Deduplication is what makes "a chunk assembled from N elements carries N
    regions" true. Without it an element that was hard-split into several
    fragments, or a table header repeated across row fragments, would
    contribute the same rectangle once per fragment — and the citation
    overlay would stack identical boxes on top of each other, darkening that
    line once per repeat.

    Order is preserved rather than sorted: reading order is what the
    extractor established, and it is what a reader follows down the page.
    """
    seen: set[BoundingBox] = set()
    result: list[BoundingBox] = []
    for box in boxes:
        if box in seen:
            continue
        seen.add(box)
        result.append(box)
    return tuple(result)


def regions_for(elements: Iterable[DocumentElement]) -> tuple[BoundingBox, ...]:
    """Return the regions the given source elements occupy, in reading order."""
    return dedupe_regions(box for element in elements for box in element.bboxes)
