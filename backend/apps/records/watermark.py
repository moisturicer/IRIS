"""
Mark a copy of a manuscript with who downloaded it (ADR-048, decisions 10-12).

The copy is built per download, in memory, and never stored. Anything that goes
wrong raises `WatermarkFailed`, and the caller serves nothing.
"""
import logging
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)

MARK_ANGLE_DEGREES = 45
MARK_GREY = 0.45  # 0 is black and 1 is white
MARK_OPACITY = 0.18  # Over white paper this prints about as light as grey 0.9
MARK_WIDTH_OF_SHORT_SIDE = 1.0
MARK_STROKE = 0.24  # Of a letter's height
MARK_GAP = 0.2  # Clear space between letters, of a letter's height, so thick strokes never merge

FOOTER_FONT = "Helvetica"
FOOTER_GREY = 0.2
FOOTER_SIZE = 8
FOOTER_MIN_SIZE = 3
FOOTER_MARGIN = 12

#: What the built-in fonts can draw. Anything else would print as a blank.
_FOOTER_ENCODING = "cp1252"


class WatermarkFailed(Exception):
    """This copy could not be marked, so it must not be served."""


@dataclass(frozen=True)
class CopyIdentity:
    """Who a copy was made for, as the footer and the metadata both state it."""

    name: str
    email: str
    date: str  # YYYY-MM-DD
    basis: str  # "request #12", or the exemption reason

    @property
    def footer(self) -> str:
        return f"Downloaded by {self.holder} on {self.date} via CIT-U IRIS · {self.basis}"

    @property
    def holder(self) -> str:
        return f"{self.name} ({self.email})"

    @property
    def metadata(self) -> dict[str, str]:
        return {
            "/DownloadedBy": self.holder,
            "/DownloadedOn": self.date,
            "/DownloadBasis": self.basis,
        }


def _single_page(draw, width: float, height: float):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(width, height))
    draw(pdf)
    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return PdfReader(buffer).pages[0]


def _cit_u(pdf) -> float:
    """
    "CIT-U" as straight stroked lines, one unit tall, from the origin rightwards:
    square block letters, no curves.

    Shapes rather than a font, so the mark adds no "CIT-U" to the copy's text:
    copying or searching the copy finds only the paper and its footer. Letters
    are spaced by their stroke as well as MARK_GAP, so a thicker stroke widens
    the word instead of closing it up. Returns the width between the outer
    edges of the first and last strokes.
    """
    advance = MARK_STROKE + MARK_GAP  # Added to each letter's own width
    path = pdf.beginPath()
    x = 0.0
    # C: three sides of a square
    path.moveTo(x + 0.7, 1)
    path.lineTo(x, 1)
    path.lineTo(x, 0)
    path.lineTo(x + 0.7, 0)
    x += 0.7 + advance
    # I
    path.moveTo(x, 0)
    path.lineTo(x, 1)
    x += advance
    # T
    path.moveTo(x, 1)
    path.lineTo(x + 0.7, 1)
    path.moveTo(x + 0.35, 1)
    path.lineTo(x + 0.35, 0)
    x += 0.7 + advance
    # -
    path.moveTo(x, 0.45)
    path.lineTo(x + 0.4, 0.45)
    x += 0.4 + advance
    # U: three sides of a square
    path.moveTo(x, 1)
    path.lineTo(x, 0)
    path.lineTo(x + 0.7, 0)
    path.lineTo(x + 0.7, 1)
    pdf.drawPath(path, stroke=1, fill=0)
    return x + 0.7 + MARK_STROKE


def _cit_u_width() -> float:
    """What `_cit_u` returns, without drawing: four letters' widths and gaps."""
    return 0.7 + 0.7 + 0.4 + 0.7 + 4 * (MARK_STROKE + MARK_GAP) + MARK_STROKE


def _mark_overlay(width: float, height: float):
    """
    A faint diagonal "CIT-U" across the page, drawn over the content.

    Over, not beneath (ADR-048 decision 10, amended for IR-1127): many exported
    papers paint each page white edge to edge, and scanned pages are one opaque
    image, and either hides a mark beneath. Translucent, so the text stays readable.
    """
    def draw(pdf):
        word = _cit_u_width()
        letter = MARK_WIDTH_OF_SHORT_SIDE * min(width, height) / word
        pdf.setStrokeGray(MARK_GREY)
        pdf.setStrokeAlpha(MARK_OPACITY)
        pdf.setLineWidth(MARK_STROKE)
        pdf.setLineCap(2)  # Square ends and sharp corners, for block letters
        pdf.setLineJoin(0)
        pdf.translate(width / 2, height / 2)
        pdf.rotate(MARK_ANGLE_DEGREES)
        pdf.scale(letter, letter)
        pdf.translate(-word / 2 + MARK_STROKE / 2, -0.5)
        _cit_u(pdf)

    return _single_page(draw, width, height)


def _footer(text: str, width: float, height: float):
    available = width - 2 * FOOTER_MARGIN
    size = min(FOOTER_SIZE, FOOTER_SIZE * available / stringWidth(text, FOOTER_FONT, FOOTER_SIZE))
    if size < FOOTER_MIN_SIZE:
        raise WatermarkFailed(f"A {width}pt page is too narrow for a legible footer")

    def draw(pdf):
        pdf.setFillGray(FOOTER_GREY)
        pdf.setFont(FOOTER_FONT, size)
        pdf.drawCentredString(width / 2, FOOTER_MARGIN, text)

    return _single_page(draw, width, height)


def _mark(source: bytes, identity: CopyIdentity) -> BytesIO:
    identity.footer.encode(_FOOTER_ENCODING)  # A name the font can't spell identifies no one

    reader = PdfReader(BytesIO(source))
    if reader.is_encrypted:
        raise WatermarkFailed("The manuscript is encrypted")
    if not reader.pages:
        raise WatermarkFailed("The manuscript has no pages")

    writer = PdfWriter(clone_from=reader)
    overlays = {}  # Pages of one size share their overlays
    for page in writer.pages:
        page.transfer_rotation_to_content()
        box = page.cropbox
        size = (float(box.width), float(box.height))
        if size not in overlays:
            overlays[size] = (_mark_overlay(*size), _footer(identity.footer, *size))
        mark, footer = overlays[size]
        to_visible_area = Transformation().translate(float(box.left), float(box.bottom))
        page.merge_transformed_page(mark, to_visible_area, over=True)
        page.merge_transformed_page(footer, to_visible_area, over=True)  # Last, so nothing covers it
    writer.add_metadata(identity.metadata)

    marked = BytesIO()
    writer.write(marked)
    marked.seek(0)
    return marked


def watermark_pdf(source: bytes, identity: CopyIdentity) -> BytesIO:
    """A marked copy of `source`. The bytes given are left as they are."""
    try:
        return _mark(source, identity)
    except WatermarkFailed:
        raise
    except Exception as error:  # pypdf raises many types on a bad file, and fail closed covers all
        logger.warning("Could not watermark a manuscript: %s", error)
        raise WatermarkFailed(str(error)) from error
