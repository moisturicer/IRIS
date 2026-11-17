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


#: The mark's words, one line each, centred on one another (IR-1198).
MARK_LINES = ("PROPERTY OF", "CIT-U", "DO NOT DISTRIBUTE")
MARK_WORD_GAP = 0.6  # A space between words, of a letter's height
MARK_LINE_GAP = 0.7  # Clear space between lines, of a letter's height

MARK_OVERSHOOT = 0.2  # How far an open stroke runs past its line's edge, to be cut flat there

#: Each letter as strokes, one unit tall, y up, from x = 0: (width, strokes).
#: The unit is between the centres of a letter's top and bottom strokes, so its
#: ink is one unit and a stroke tall. A stroke that ends open at the top or the
#: bottom runs MARK_OVERSHOOT past it (y = 1.2 or -0.2) and `_line_bands` cuts
#: it flat at the ink's edge, which makes every letter the same height.
#: A stroke is ("M", x, y) then ("L", x, y) lines and ("A", cx, cy, rx, ry,
#: start, extent) elliptical arcs in degrees, counterclockwise when positive,
#: each beginning where the one before it ended; ("Z",) closes it. Mirrored in
#: `ReaderWatermark.tsx`, so the reader's mark matches a downloaded copy's.
MARK_GLYPHS: dict[str, tuple[float, tuple[tuple, ...]]] = {
    "B": (0.7, (
        (("M", 0.38, 0.5), ("L", 0, 0.5), ("L", 0, 1), ("L", 0.38, 1), ("A", 0.38, 0.75, 0.28, 0.25, 90, -180)),
        (("M", 0, 0.5), ("L", 0.4, 0.5), ("A", 0.4, 0.25, 0.3, 0.25, 90, -180), ("L", 0, 0), ("L", 0, 0.5)),
    )),
    "C": (0.7, ((("M", 0.35 + 0.35 * 0.6427876, 0.5 + 0.5 * 0.7660444), ("A", 0.35, 0.5, 0.35, 0.5, 50, 260)),)),
    "D": (0.7, ((("M", 0, 0), ("L", 0, 1), ("L", 0.25, 1), ("A", 0.25, 0.5, 0.45, 0.5, 90, -180), ("Z",)),)),
    "E": (0.6, (
        (("M", 0.6, 1), ("L", 0, 1), ("L", 0, 0), ("L", 0.6, 0)),
        (("M", 0, 0.5), ("L", 0.5, 0.5)),
    )),
    "F": (0.6, (
        (("M", 0.6, 1), ("L", 0, 1), ("L", 0, -0.2)),
        (("M", 0, 0.5), ("L", 0.5, 0.5)),
    )),
    "I": (0.0, ((("M", 0, -0.2), ("L", 0, 1.2)),)),
    "N": (0.7, (
        (("M", 0, -0.2), ("L", 0, 1.2)),
        (("M", 0, 1), ("L", 0.7, 0)),
        (("M", 0.7, -0.2), ("L", 0.7, 1.2)),
    )),
    "O": (0.7, ((("M", 0.7, 0.5), ("A", 0.35, 0.5, 0.35, 0.5, 0, 360), ("Z",)),)),
    "P": (0.7, ((("M", 0, -0.2), ("L", 0, 1), ("L", 0.4, 1), ("A", 0.4, 0.725, 0.3, 0.275, 90, -180), ("L", 0, 0.45)),)),
    "R": (0.7, (
        (("M", 0, -0.2), ("L", 0, 1), ("L", 0.4, 1), ("A", 0.4, 0.725, 0.3, 0.275, 90, -180), ("L", 0, 0.45)),
        (("M", 0.36, 0.45), ("L", 0.724, -0.2)),
    )),
    "S": (0.7, ((
        ("M", 0.35 + 0.35 * 0.8660254, 0.75 + 0.25 * 0.5),
        ("A", 0.35, 0.75, 0.35, 0.25, 30, 240),
        ("A", 0.35, 0.25, 0.35, 0.25, 90, -240),
    ),)),
    "T": (0.7, (
        (("M", 0, 1), ("L", 0.7, 1)),
        (("M", 0.35, 1), ("L", 0.35, -0.2)),
    )),
    "U": (0.7, ((("M", 0, 1.2), ("L", 0, 0.35), ("A", 0.35, 0.35, 0.35, 0.35, 180, 180), ("L", 0.7, 1.2)),)),
    "Y": (0.7, (
        (("M", -0.025, 1.2), ("L", 0.35, 0.45), ("L", 0.725, 1.2)),
        (("M", 0.35, 0.45), ("L", 0.35, -0.2)),
    )),
    "-": (0.4, ((("M", 0, 0.45), ("L", 0.4, 0.45)),)),
}


def _line_width(text: str) -> float:
    """
    A line's width between the outer edges of its first and last strokes.
    Letters are spaced by their stroke as well as MARK_GAP, so a thicker stroke
    widens the line instead of closing it up.
    """
    advance = MARK_STROKE + MARK_GAP
    x = 0.0
    for char in text:
        x += MARK_WORD_GAP if char == " " else MARK_GLYPHS[char][0] + advance
    return x - advance + MARK_STROKE


def _block_height() -> float:
    """The mark's lines, one unit tall each, and the space between them."""
    return len(MARK_LINES) + (len(MARK_LINES) - 1) * MARK_LINE_GAP


def _mark_width() -> float:
    return max(_line_width(line) for line in MARK_LINES)


def _draw_glyph(path, strokes, dx: float, dy: float) -> None:
    for stroke in strokes:
        for command, *args in stroke:
            if command == "M":
                path.moveTo(args[0] + dx, args[1] + dy)
            elif command == "L":
                path.lineTo(args[0] + dx, args[1] + dy)
            elif command == "A":
                cx, cy, rx, ry, start, extent = args
                path.arcTo(cx - rx + dx, cy - ry + dy, cx + rx + dx, cy + ry + dy, startAng=start, extent=extent)
            else:
                path.close()


def _row_bottom(row: int) -> float:
    """Where a line's bottom strokes are centred, with the block centred on y = 0."""
    return _block_height() / 2 - 1 - row * (1 + MARK_LINE_GAP)


def _line_bands() -> list[tuple[float, float, float, float]]:
    """
    Each line's ink as (x, y, width, height): from the outer edge of its bottom
    strokes to the outer edge of its top ones, wide enough for any line.
    """
    half = _mark_width() / 2 + 1
    return [(-half, _row_bottom(row) - MARK_STROKE / 2, 2 * half, 1 + MARK_STROKE) for row in range(len(MARK_LINES))]


def _mark_lines(pdf) -> None:
    """
    MARK_LINES as stroked lines and arcs, one unit per letter, each line centred
    on the origin and the block centred on it vertically. Every stroke ends flat,
    and nothing is drawn outside `_line_bands`, so every letter is one height.

    Shapes rather than a font, so the mark adds no text to the copy: copying or
    searching it finds only the paper and its footer. One path, stroked once, so
    where strokes cross the translucent grey is not laid down twice.
    """
    bands = pdf.beginPath()
    for band in _line_bands():
        bands.rect(*band)
    pdf.clipPath(bands, stroke=0, fill=0)

    advance = MARK_STROKE + MARK_GAP
    path = pdf.beginPath()
    for row, text in enumerate(MARK_LINES):
        y = _row_bottom(row)
        x = -_line_width(text) / 2 + MARK_STROKE / 2
        for char in text:
            if char == " ":
                x += MARK_WORD_GAP
                continue
            width, strokes = MARK_GLYPHS[char]
            _draw_glyph(path, strokes, x, y)
            x += width + advance
    pdf.drawPath(path, stroke=1, fill=0)


def _mark_overlay(width: float, height: float):
    """
    A faint diagonal "PROPERTY OF / CIT-U / DO NOT DISTRIBUTE" across the page,
    drawn over the content, its longest line as wide as the page's short side.

    Over, not beneath (ADR-048 decision 10, amended for IR-1127): many exported
    papers paint each page white edge to edge, and scanned pages are one opaque
    image, and either hides a mark beneath. Translucent, so the text stays readable.
    """
    def draw(pdf):
        letter = MARK_WIDTH_OF_SHORT_SIDE * min(width, height) / _mark_width()
        pdf.setStrokeGray(MARK_GREY)
        pdf.setStrokeAlpha(MARK_OPACITY)
        pdf.setLineWidth(MARK_STROKE)
        pdf.setLineCap(0)  # Flat ends: strokes stop square where they end
        pdf.setLineJoin(0)
        pdf.translate(width / 2, height / 2)
        pdf.rotate(MARK_ANGLE_DEGREES)
        pdf.scale(letter, letter)
        _mark_lines(pdf)

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
