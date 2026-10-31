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

BACKGROUND_TEXT = "CIT-U"
BACKGROUND_FONT = "Helvetica-Bold"
BACKGROUND_ANGLE_DEGREES = 45
BACKGROUND_GREY = 0.88  # 0 is black and 1 is white
BACKGROUND_WIDTH_OF_SHORT_SIDE = 1.0

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


def _background(width: float, height: float):
    def draw(pdf):
        size = (
            BACKGROUND_WIDTH_OF_SHORT_SIDE * min(width, height)
            / stringWidth(BACKGROUND_TEXT, BACKGROUND_FONT, 1)
        )
        pdf.setFillGray(BACKGROUND_GREY)
        pdf.setFont(BACKGROUND_FONT, size)
        pdf.translate(width / 2, height / 2)
        pdf.rotate(BACKGROUND_ANGLE_DEGREES)
        pdf.drawCentredString(0, -size / 3, BACKGROUND_TEXT)

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
            overlays[size] = (_background(*size), _footer(identity.footer, *size))
        background, footer = overlays[size]
        to_visible_area = Transformation().translate(float(box.left), float(box.bottom))
        page.merge_transformed_page(background, to_visible_area, over=False)
        page.merge_transformed_page(footer, to_visible_area, over=True)
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
