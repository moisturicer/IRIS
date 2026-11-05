"""Test PDFs for the review text reader (IR-871), drawn with reportlab so every
position is known. Not imported by any production module."""
from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

BODY, BOLD = "Times-Roman", "Times-Bold"
LEFT, LINE = 72, 16


def pdf(pages, *, running_head="Community Waste-to-Energy Feasibility", numbered=True,
        size=letter) -> bytes:
    """A PDF from ``pages``: each a list of ``(kind, text)`` with kind
    ``heading`` (bold), ``plain`` (body font, e.g. a numbered or capitals
    heading), ``para`` (an indented paragraph, one item per line), ``table``
    (rows of cells, ruled) or ``blank`` (a vertical gap)."""
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=size)
    width, height = size
    for number, items in enumerate(pages, start=1):
        if running_head:
            c.setFont(BODY, 10)
            c.drawString(LEFT, height - 40, running_head)
        y = height - 90
        for kind, value in items:
            if kind in ("heading", "plain"):
                c.setFont(BOLD if kind == "heading" else BODY, 12)
                c.drawString(LEFT, y, value)
                y -= LINE * 1.8
            elif kind == "para":
                c.setFont(BODY, 12)
                for i, line in enumerate(value):
                    c.drawString(LEFT + (36 if i == 0 else 0), y, line)
                    y -= LINE
                y -= LINE * 0.8
            elif kind == "table":
                y = _table(c, value, y)
            elif kind == "blank":
                y -= LINE * 2
        if numbered:
            c.setFont(BODY, 10)
            c.drawCentredString(width / 2, 36, str(number))
        c.showPage()
    c.save()
    return out.getvalue()


def _table(c, rows, y):
    col = 150
    c.setFont(BODY, 11)
    top = y + 12
    for r, cells in enumerate(rows):
        for i, cell in enumerate(cells):
            c.drawString(LEFT + 6 + i * col, y - r * 20, cell)
    bottom = y - len(rows) * 20 + 12
    right = LEFT + len(rows[0]) * col
    for r in range(len(rows) + 1):
        c.line(LEFT, top - r * 20, right, top - r * 20)
    for i in range(len(rows[0]) + 1):
        c.line(LEFT + i * col, top, LEFT + i * col, bottom)
    return bottom - LINE * 2


def two_columns(left_lines, right_lines, size=letter) -> bytes:
    """One page set in two columns with a gutter between them."""
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=size)
    width, height = size
    c.setFont(BODY, 11)
    for x, lines in ((LEFT, left_lines), (width / 2 + 18, right_lines)):
        y = height - 90
        for line in lines:
            c.drawString(x, y, line)
            y -= 14
    c.showPage()
    c.save()
    return out.getvalue()


def blank(pages=1, size=letter) -> bytes:
    """A PDF with pages and no text layer, as a scan is."""
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=size)
    for _ in range(pages):
        c.rect(100, 100, 200, 200, fill=1)
        c.showPage()
    c.save()
    return out.getvalue()


#: A short thesis-shaped paper: front matter, CHAPTER headings, numbered and
#: capitals headings in the body font, a hyphenated word, a compound broken at
#: its own hyphen, an abbreviation and an initial that end no sentence, and a
#: ruled table. Every page carries a running head and a page number.
THESIS = [
    [
        ("plain", "COMMUNITY WASTE-TO-ENERGY FEASIBILITY"),
        ("para", ["A thesis presented to the College of Engineering."]),
    ],
    [
        ("heading", "CHAPTER 1"),
        ("heading", "INTRODUCTION"),
        ("plain", "1.1 Background of the Study"),
        ("para", ["Metro Cebu generates about 2,000 tonnes of waste a day. Landfills",
                  "are near capacity, so the cities look at small-",
                  "scale plants. The municipal govern-",
                  "ment asked for a study, e.g. of costs. Engr. J. Cruz led it."]),
        ("plain", "1.2 Statement of the Problem"),
        ("para", ["This study asks whether a plant is feasible."]),
    ],
    [
        ("plain", "CHAPTER 2"),
        ("plain", "REVIEW OF RELATED LITERATURE"),
        ("para", ["Earlier studies used small-scale digesters in Davao."]),
        ("table", [["Technology", "Output"], ["Digestion", "40 kW"], ["Gasification", "90 kW"]]),
        ("para", ["The table shows each output."]),
    ],
]


def in_process_sandbox(source):
    """A stand-in for `sandbox.read_in_sandbox` that runs the same reader in
    this process, mapping its exceptions to the child's exit reasons. For
    tests on any platform; the real sandbox needs Linux (test_review_text_sandbox.py)."""
    import tempfile
    from pathlib import Path

    from . import reader, sandbox

    import hashlib

    data = source.read()
    sha256 = hashlib.sha256(data).hexdigest()
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "source.pdf"
        path.write_bytes(data)
        try:
            reading = reader.read(path, max_pages=1000)
        except reader.Encrypted:
            return sandbox.Outcome(sandbox.NO_TEXT, "encrypted", sha256=sha256)
        except reader.OverBudget:
            return sandbox.Outcome(sandbox.NO_TEXT, "over_limits", sha256=sha256)
        except reader.Unreadable:
            return sandbox.Outcome(sandbox.NO_TEXT, "unreadable", sha256=sha256)
    outcome = sandbox.outcome_of(reading)
    outcome.sha256 = sha256
    return outcome


def journal(pages=3, size=letter) -> bytes:
    """A journal-style article, as the first real paper read with IR-871 was
    laid out: a title across the page over two columns, 17 pt first-line
    indents, and a footer across both columns at 91.6% of the page height,
    inside the old 8% margin's reach but not its band."""
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=size)
    width, height = size
    gutter = width / 2 + 10
    for number in range(1, pages + 1):
        y = height - 90
        if number == 1:
            c.setFont(BOLD, 14)
            c.drawString(LEFT, y, "A Theory of Bounded Change Across Institutions and People")
            y -= 30
        c.setFont(BODY, 10)
        for column_x in (LEFT, gutter):
            line_y = y
            for paragraph in range(3):
                for i in range(5):
                    indent = 17 if i == 0 else 0
                    c.drawString(column_x + indent, line_y,
                                 f"P{number}{'LR'[column_x > LEFT]}{paragraph} line {i} reads on here.")
                    line_y -= 12
        c.setFont(BODY, 8)
        c.drawString(LEFT, height * (1 - 0.916), f"JOURNAL {4454 + number}")
        c.drawString(gutter, height * (1 - 0.916), "Volume 7 | Number 10 | October | 2026")
        c.showPage()
    c.save()
    return out.getvalue()


def headings(lines) -> bytes:
    """One page of ``(font, size, text)`` lines 13 pt apart, then a sentence."""
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=letter)
    y = letter[1] - 120
    for font, size, text in lines:
        c.setFont(font, size)
        c.drawString(LEFT, y, text)
        y -= 13
    c.setFont(BODY, 11)
    c.drawString(LEFT, y - 10, "The body starts here.")
    c.showPage()
    c.save()
    return out.getvalue()


def placed(pages, size=letter) -> bytes:
    """Pages of ``(x, font, size, text)`` lines, 16 pt apart, at exact
    positions, for paragraph and list rules. A fifth item, ``True``, draws
    the text on the line before, as a list item's text beside its number."""
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=size)
    for lines in pages:
        y = size[1] - 84
        for x, font, font_size, text, *same_line in lines:
            if not same_line:
                y -= 16
            c.setFont(font, font_size)
            c.drawString(x, y, text)
        c.showPage()
    c.save()
    return out.getvalue()


def boxed_paragraph(lines, size=letter) -> bytes:
    """A paragraph drawn as Word draws a bordered one: one box per line, the
    last word of a line overhanging the box's right border by a fraction."""
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=size)
    y = size[1] - 120
    c.setFont(BOLD, 12)
    c.drawString(LEFT, y + 30, "Consent Statement")
    c.setFont(BODY, 10)
    for text in lines:
        width = c.stringWidth(text, BODY, 10)
        c.rect(LEFT - 2, y - 3, width + 1.7, 12)   # 0.3 pt short of the text
        c.drawString(LEFT, y, text)
        y -= 12
    c.showPage()
    c.save()
    return out.getvalue()
