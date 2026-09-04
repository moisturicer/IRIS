"""The document the chunker consumes.

This type is **owned by IRIS**. The chunker must never import a vendor model:
Docling is the extractor today, but swapping extractors has to change an
adapter, not this type, the port, or its contract suite.

It is also what lets the chunker be built and tested before any extractor
exists, against documents assembled by hand.

Pure: no Django, no I/O, no clock, no randomness.
"""

from dataclasses import dataclass, field
from typing import Mapping, Optional

# Element kinds the chunker understands. A kind outside this set is carried
# through untouched rather than rejected, so an extractor emitting something
# new degrades to plain text instead of failing the whole document.
HEADING = "heading"
PARAGRAPH = "paragraph"
TABLE_ROW = "table_row"
TABLE_HEADER = "table_header"
LIST_ITEM = "list_item"
CAPTION = "caption"

# Not mapped by the Docling adapter (see docling_mapping.py's module
# docstring) — these arrive as Docling's own labels, carried through
# unchanged specifically so the normalizer can drop them without guessing
# at running headers/footers from their text.
PAGE_HEADER = "page_header"
PAGE_FOOTER = "page_footer"


@dataclass(frozen=True)
class BoundingBox:
    """One highlightable region, top-left origin, in PDF points.

    Top-left because that is the origin the PDF viewer uses, so the stored
    form matches its consumer and no conversion can be forgotten.
    """

    page: int
    left: float
    top: float
    right: float
    bottom: float

    @property
    def is_degenerate(self) -> bool:
        """A zero-area rect. Stored as a sentinel rather than drawn."""
        return self.right <= self.left or self.bottom <= self.top


@dataclass(frozen=True)
class DocumentElement:
    """One structural element of a document, with where it came from.

    ``page`` and ``bboxes`` are populated by the extraction adapter (CURRENT
    — ``apps.ai.extraction.docling_mapping``, IR-107) and carried through to
    chunks so a citation can be highlighted. They stay optional because the
    chunker core does not need them: a document assembled by hand in a test
    chunks identically without them.

    ``bboxes`` is a tuple rather than one rectangle because normalization can
    assemble one element from several — a word hyphenated across a page break
    becomes a single element occupying a rectangle on each page. Storing one
    box there would truncate the highlight at the page boundary, which is the
    evidence a reviewer most needs to see.
    """

    kind: str
    text: str
    level: Optional[int] = None
    page: Optional[int] = None
    bboxes: tuple[BoundingBox, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.bboxes, tuple):
            object.__setattr__(self, "bboxes", tuple(self.bboxes))

    @property
    def bbox(self) -> Optional[BoundingBox]:
        """The first region — the one ``page`` refers to.

        Read only by tests today. It stays because ``page`` names a single
        page and this is the rectangle that goes with it; without it, a
        reader has to know that ``bboxes[0]`` is the one that matches.
        """
        return self.bboxes[0] if self.bboxes else None

    @property
    def is_heading(self) -> bool:
        return self.kind == HEADING


@dataclass(frozen=True)
class NormalizedDocument:
    """A document ready to be chunked: cleaned, structured, in reading order."""

    title: str
    elements: tuple[DocumentElement, ...] = ()
    page_sizes: Mapping[int, tuple[float, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.elements, tuple):
            object.__setattr__(self, "elements", tuple(self.elements))
