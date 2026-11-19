"""First-page thumbnail renderer (IR-1241).

Draws page 1 of a manuscript as a small WebP for Discover's result rows, so a
row never downloads the whole paper. pypdfium2, Pillow and the standard
library only, as ``crops.py``.

Runs as the sandbox child: ``python -I first_page.py <pdf> <out> <MiB> <pages>``,
exit 0 rendered, 2 unreadable, 3 encrypted, 5 over limits. ``-I`` keeps this
file's own directory off ``sys.path``, so it imports nothing beside it; that is
why ``confine`` is repeated here rather than shared.
"""
from __future__ import annotations

import io
import sys

#: The Discover box is 96 px wide (`w-24`); twice that stays sharp on a
#: high-density screen.
WIDTH = 192
QUALITY = 70
#: Pixels the drawn page may hold. A normal page at WIDTH is ~50,000; this
#: refuses a page so tall and thin that its height alone would be a problem.
MAX_PIXELS = 4_000_000


class OverBudget(Exception):
    pass


class Encrypted(Exception):
    pass


def render(data: bytes, *, max_pages: int, width: int = WIDTH) -> bytes:
    """Page 1 of ``data`` as WebP bytes, ``width`` pixels wide."""
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as error:
        if "password" in str(error).lower():
            raise Encrypted from error
        raise
    try:
        if len(pdf) > max_pages:
            raise OverBudget
        if len(pdf) < 1:
            raise ValueError("no pages")
        page = pdf[0]
        page_width, page_height = page.get_size()
        if page_width <= 0 or page_height <= 0:
            raise ValueError("an empty page")
        scale = width / page_width
        if width * page_height * scale > MAX_PIXELS:
            raise OverBudget
        image = page.render(scale=scale).to_pil().convert("RGB")
        out = io.BytesIO()
        image.save(out, format="WEBP", quality=QUALITY)
        return out.getvalue()
    finally:
        pdf.close()


# ---------------------------------------------------------------- sandbox child
def _preload():
    """Import, before `confine()`, everything a render loads lazily."""
    import PIL.Image
    import PIL.WebPImagePlugin  # noqa: F401
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

        path, out, memory_mib, max_pages = argv[1], argv[2], int(argv[3]), int(argv[4])
        memory = memory_mib * 1024 * 1024
        with open("/proc/self/statm", encoding="ascii") as usage:
            runtime_bytes = int(usage.read(128).split()[0]) * os.sysconf("SC_PAGE_SIZE")
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        if runtime_bytes > memory:
            return 5
        with open(path, "rb") as source:
            data = source.read()
        target = open(out, "wb")
        _preload()
        confine()
        image = render(data, max_pages=max_pages)
        target.write(image)
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
