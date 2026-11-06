"""PROTOTYPE, throwaway. A three-column page, read by both readers, in order or not.

    python three_columns.py

Draws a newsletter-style page (a title across the top, then three columns of
numbered sentences), reads it with the rules and with the layout model, and
says whether the sentences come out in order.
"""
import re
import sys
import tempfile
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import layout_reader  # noqa: E402
import reader  # noqa: E402


def page(path):
    c = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    c.setFont("Times-Bold", 16)
    c.drawString(72, height - 80, "Campus Research Newsletter, November Issue")
    c.setFont("Times-Roman", 10)
    n = 0
    col_width = (width - 144 - 40) / 3
    for col in range(3):
        x = 72 + col * (col_width + 20)
        y = height - 120
        for _ in range(30):
            n += 1
            c.drawString(x, y, f"Sentence {n:02d} sits in column {col + 1} here.")
            y -= 14
    c.showPage()
    c.save()


def order(reading):
    text = " ".join(p["text"] for s in reading["sections"] for p in s["passages"])
    numbers = [int(m) for m in re.findall(r"Sentence (\d+)", text)]
    return numbers


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "three.pdf"
        page(pdf)
        for name, read in (("rules", reader.read), ("layout", layout_reader.read)):
            got = order(read(pdf))
            right = got == sorted(got) and len(got) == 90
            print(f"{name:6} read {len(got)} of 90 sentences, in order: {right}; first 12: {got[:12]}")
