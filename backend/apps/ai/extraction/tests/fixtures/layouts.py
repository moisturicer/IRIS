"""The fixture layouts: one description draws the PDF and states its document.

Coordinates are top-left PDF points, the origin ``BoundingBox`` uses; the
drawing converts to reportlab's bottom-left. ``invariant`` mode makes the
bytes reproducible, so a test can tell a committed PDF from a stale one.
"""

from dataclasses import dataclass
from io import BytesIO
from typing import Optional

from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from apps.ai.chunking.document import (
    CAPTION,
    FORMULA,
    HEADING,
    PAGE_FOOTER,
    PAGE_HEADER,
    PARAGRAPH,
    TABLE_HEADER,
    TABLE_ROW,
    BoundingBox,
    DocumentElement,
    NormalizedDocument,
)

WIDTH, HEIGHT = letter  # 612 x 792
FONT, BOLD = "Helvetica", "Helvetica-Bold"


@dataclass(frozen=True)
class Item:
    kind: str
    text: str
    left: float
    top: float
    size: float = 10.0
    level: Optional[int] = None


@dataclass(frozen=True)
class Figure:
    """A drawn picture; it yields no element, only its caption does."""

    left: float
    top: float
    width: float
    height: float


@dataclass(frozen=True)
class Fixture:
    name: str
    title: str
    pages: tuple[tuple[object, ...], ...]
    # Text that must arrive in this order: the contract's reading-order check.
    reading_order: tuple[str, ...]
    has_table: bool = False

    @property
    def filename(self) -> str:
        return f"{self.name}.pdf"


def _furniture(page: int) -> tuple[Item, ...]:
    return (
        Item(PAGE_HEADER, "IRIS contract fixture", 72, 36, 8),
        Item(PAGE_FOOTER, f"Page {page}", 290, 750, 8),
    )


def _numbered_headings() -> Fixture:
    page1 = _furniture(1) + (
        Item(HEADING, "1 Introduction", 72, 80, 14, level=1),
        Item(PARAGRAPH, "The introduction states the question this fixture asks.", 72, 104),
        Item(HEADING, "1.1 Background", 72, 140, 12, level=2),
        Item(PARAGRAPH, "Background material follows its numbered heading.", 72, 162),
        Item(HEADING, "2 Methods", 72, 200, 14, level=1),
        Item(PARAGRAPH, "Methods are described before any result is reported.", 72, 224),
    )
    page2 = _furniture(2) + (
        Item(HEADING, "3 Results", 72, 80, 14, level=1),
        Item(PARAGRAPH, "Results close the document on its second page.", 72, 104),
    )
    return Fixture(
        name="numbered_headings",
        title="Numbered headings",
        pages=(page1, page2),
        reading_order=("1 Introduction", "1.1 Background", "2 Methods", "3 Results"),
    )


def _two_columns() -> Fixture:
    left, right = 72, 324
    items = _furniture(1) + (
        Item(HEADING, "Two column study", 72, 70, 14, level=1),
        Item(PARAGRAPH, "Left column one opens.", left, 110),
        Item(PARAGRAPH, "Left column two continues.", left, 140),
        Item(FORMULA, "E = m c^2", left + 40, 180, 12),
        Item(PARAGRAPH, "Left column three ends.", left, 220),
        Item(PARAGRAPH, "Right column one resumes.", right, 110),
        Item(PARAGRAPH, "Right column two continues.", right, 140),
        Item(PARAGRAPH, "Right column three ends.", right, 170),
    )
    return Fixture(
        name="two_columns",
        title="Two column study",
        pages=(items,),
        reading_order=(
            "Left column one", "Left column two", "E = m c^2", "Left column three",
            "Right column one", "Right column two", "Right column three",
        ),
    )


def _table_across_pages() -> Fixture:
    rows = [f"| Row {n:02d} | {400 + n} g |" for n in range(1, 31)]
    page1 = _furniture(1) + (
        Item(HEADING, "Measurements", 72, 70, 14, level=1),
        Item(PARAGRAPH, "The table below continues onto the next page.", 72, 94),
        Item(TABLE_HEADER, "| Sample | Mass |", 72, 120, 10),
    ) + tuple(Item(TABLE_ROW, row, 72, 140 + 20 * i) for i, row in enumerate(rows[:28]))
    page2 = _furniture(2) + tuple(
        Item(TABLE_ROW, row, 72, 80 + 20 * i) for i, row in enumerate(rows[28:])
    ) + (Item(PARAGRAPH, "The paragraph after the table.", 72, 140),)
    return Fixture(
        name="table_across_pages",
        title="Measurements",
        pages=(page1, page2),
        reading_order=("Measurements", "| Sample | Mass |", "| Row 01 |", "| Row 30 |",
                       "The paragraph after the table."),
        has_table=True,
    )


def _figures() -> Fixture:
    items = _furniture(1) + (
        Item(HEADING, "Figures and formulas", 72, 70, 14, level=1),
        Item(PARAGRAPH, "A captioned figure comes first.", 72, 94),
        Figure(72, 110, 200, 120),
        Item(CAPTION, "Figure 1: A captioned rectangle.", 72, 240, 9),
        Item(PARAGRAPH, "An uncaptioned figure follows.", 72, 270),
        Figure(72, 290, 200, 120),
        Item(FORMULA, "a^2 + b^2 = c^2", 120, 430, 12),
        Item(PARAGRAPH, "The formula above closes the page.", 72, 460),
    )
    return Fixture(
        name="figures",
        title="Figures and formulas",
        pages=(items,),
        reading_order=("Figure 1:", "An uncaptioned figure", "a^2 + b^2 = c^2", "The formula above"),
    )


FIXTURES: dict[str, Fixture] = {
    f.name: f for f in (_numbered_headings(), _two_columns(), _table_across_pages(), _figures())
}


def _font(item: Item) -> str:
    return BOLD if item.kind == HEADING else FONT


def _box(item: Item, page: int) -> BoundingBox:
    width = stringWidth(item.text, _font(item), item.size)
    return BoundingBox(page=page, left=item.left, top=item.top,
                       right=item.left + width, bottom=item.top + item.size * 1.2)


def render(fixture: Fixture) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.setTitle(fixture.title)
    for page in fixture.pages:
        for item in page:
            if isinstance(item, Figure):
                pdf.rect(item.left, HEIGHT - item.top - item.height, item.width, item.height)
                continue
            pdf.setFont(_font(item), item.size)
            pdf.drawString(item.left, HEIGHT - item.top - item.size, item.text)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def blank_pdf() -> bytes:
    """One empty page: what an Extractor must refuse as ``EmptyExtraction``."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _reading_key(item: Item):
    # Columns are read left before right; furniture is dropped from order but kept.
    return (item.left >= WIDTH / 2, item.top)


def expected_document(fixture: Fixture) -> NormalizedDocument:
    """The document a correct Extractor returns for ``fixture``."""
    elements = []
    for number, page in enumerate(fixture.pages, start=1):
        items = sorted((i for i in page if isinstance(i, Item)), key=_reading_key)
        elements += [
            DocumentElement(kind=i.kind, text=i.text, level=i.level, page=number,
                            bboxes=(_box(i, number),))
            for i in items
        ]
    return NormalizedDocument(
        title=fixture.title,
        elements=tuple(elements),
        page_sizes={n: (WIDTH, HEIGHT) for n in range(1, len(fixture.pages) + 1)},
    )
