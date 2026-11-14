"""Formula crop renderer (IR-1102, ADR-067 §Amendment).

Renders each box from the PDF at ``DPI``, as PNG. Boxes are fractions of
their page, so the Extractor's render size never has to match the PDF's.
pypdfium2, Pillow and the standard library only.

Runs as the sandbox child: ``python -I crops.py <pdf> <boxes> <out> <MiB> <pages>``,
exit 0 rendered, 2 unreadable, 3 encrypted, 5 over limits. A box that cannot
be rendered is ``null`` in the output, never a failure of the rest.
"""
from __future__ import annotations

import base64
import io
import json
import sys

DPI = 300
#: Points added around each box, so a glyph on its edge is not clipped.
PAD = 4.0
#: Pixels one crop may hold; a display formula is far smaller.
MAX_PIXELS = 12_000_000


class OverBudget(Exception):
    pass


class Encrypted(Exception):
    pass


def render(data: bytes, boxes: list, *, max_pages: int) -> list:
    """One PNG (or ``None``) per ``{"page", "box": [l, t, r, b]}`` fraction box."""
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as error:
        if "password" in str(error).lower():
            raise Encrypted from error
        raise
    if len(pdf) > max_pages:
        raise OverBudget
    return [_crop(pdf, item) for item in boxes]


def _crop(pdf, item):
    page_number, box = item.get("page"), item.get("box")
    if not (isinstance(page_number, int) and 1 <= page_number <= len(pdf)
            and isinstance(box, list) and len(box) == 4):
        return None
    page = pdf[page_number - 1]
    width, height = page.get_size()
    left, top = max(box[0] * width - PAD, 0.0), max(box[1] * height - PAD, 0.0)
    right, bottom = min(box[2] * width + PAD, width), min(box[3] * height + PAD, height)
    scale = DPI / 72
    if right <= left or bottom <= top or (right - left) * (bottom - top) * scale * scale > MAX_PIXELS:
        return None
    # pdfium crops by the amount taken off each side: left, bottom, right, top.
    image = page.render(scale=scale, crop=(left, height - bottom, width - right, top)).to_pil()
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


# ---------------------------------------------------------------- sandbox child
def _preload():
    """Import, before `confine()`, everything a render loads lazily."""
    import PIL.Image
    import PIL.PngImagePlugin  # noqa: F401
    import pypdfium2  # noqa: F401

    PIL.Image.init()


def confine():
    """Open no file from here on (as ``reader.confine``)."""
    import os
    import resource

    lowest_free = os.dup(0)
    os.close(lowest_free)
    resource.setrlimit(resource.RLIMIT_NOFILE, (lowest_free, lowest_free))


def main(argv) -> int:
    try:
        import os
        import resource

        path, boxes_path, out, memory_mib, max_pages = argv[1], argv[2], argv[3], int(argv[4]), int(argv[5])
        memory = memory_mib * 1024 * 1024
        with open("/proc/self/statm", encoding="ascii") as usage:
            runtime_bytes = int(usage.read(128).split()[0]) * os.sysconf("SC_PAGE_SIZE")
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        if runtime_bytes > memory:
            return 5
        with open(path, "rb") as source:
            data = source.read()
        with open(boxes_path, encoding="utf-8") as listed:
            boxes = json.load(listed)
        target = open(out, "w", encoding="utf-8")
        _preload()
        confine()
        crops = render(data, boxes, max_pages=max_pages)
        json.dump({"crops": [base64.b64encode(c).decode("ascii") if c else None for c in crops]}, target)
        target.close()
        return 0
    except (MemoryError, OverBudget, RecursionError):
        return 5
    except Encrypted:
        return 3
    except Exception:
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
