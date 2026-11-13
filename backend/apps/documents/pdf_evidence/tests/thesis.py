"""A thesis-shaped PDF with bookmarks, roman page labels, a contents page and
one page with no text layer, built in memory for the evidence tests."""

from io import BytesIO

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

HEIGHT = letter[1]


def _text(pdf, text, left, top, size=10, bold=False):
    pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    pdf.drawString(left, HEIGHT - top - size, text)


def _entry(title: str, page: str) -> str:
    return f"{title} {'.' * 30} {page}"


def thesis_pdf() -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    # i: title page
    _text(pdf, "A Thesis About Evidence", 72, 120, 18, bold=True)
    pdf.showPage()
    # ii: contents
    _text(pdf, "Table of Contents", 72, 72, 14, bold=True)
    _text(pdf, _entry("Abstract", "iii"), 72, 110)
    _text(pdf, _entry("1 Introduction", "1"), 72, 130)
    _text(pdf, _entry("1.1 Background", "1"), 90, 150)
    _text(pdf, _entry("2 Methods", "2"), 72, 170)
    pdf.showPage()
    # iii: a scanned page, a picture with no text layer
    pdf.rect(72, 200, 400, 400, fill=1)
    pdf.showPage()
    # 1 and 2: the chapters
    _text(pdf, "1 Introduction", 72, 72, 14, bold=True)
    _text(pdf, "The introduction opens the first chapter.", 72, 100)
    _text(pdf, "1.1 Background", 72, 130, 12, bold=True)
    pdf.showPage()
    _text(pdf, "2 Methods", 72, 72, 14, bold=True)
    pdf.showPage()
    pdf.save()

    writer = PdfWriter(clone_from=PdfReader(BytesIO(buffer.getvalue())))
    writer.set_page_label(0, 2, style="/r")
    writer.set_page_label(3, 4, style="/D", start=1)
    writer.add_outline_item("Contents", 1)
    chapter = writer.add_outline_item("1 Introduction", 3)
    writer.add_outline_item("1.1 Background", 3, parent=chapter)
    writer.add_outline_item("2 Methods", 4)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
