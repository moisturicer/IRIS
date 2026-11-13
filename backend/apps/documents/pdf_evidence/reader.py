"""PDF evidence reader (IR-1053, ADR-067 decision 4).

Reads the PDF's own layout once at extraction: lines with word boxes (page
points, top-left origin), font size and bold, bookmarks, page labels and
contents entries. pdfplumber, pypdf and the standard library only.

Runs as the sandbox child: ``python -I reader.py <pdf> <out> <MiB> <pages>``,
exit 0 read, 2 unreadable, 3 encrypted, 5 over limits. Raise ``READER`` on
any rule change.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict

READER = "pdf-evidence-1"

#: Same as the review text reader: pdfplumber's 3 pt default joins words.
X_TOLERANCE = 1.5
#: Words this far apart (in multiples of the font size) are separate lines,
#: so two columns sharing a baseline are not read as one line.
LINE_GAP = 1.5
#: Font name parts that mean bold.
BOLD_NAMES = ("bold", "black", "heavy", "semibold", "demi")
#: Box precision in points: 0.1 pt is far finer than a highlight needs.
ROUND = 1


class OverBudget(Exception):
    pass


class Encrypted(Exception):
    pass


def _bold(fontname: str) -> bool:
    name = (fontname or "").split("+")[-1].lower()
    return any(part in name for part in BOLD_NAMES)


def _same_row(top: float, other_top: float, size: float) -> bool:
    return abs(top - other_top) <= max(2.0, size * 0.3)


def _lines(words: list[dict]) -> list[dict]:
    """Words in pdfplumber's order (by line, then left to right) grouped into lines."""
    lines, current = [], []
    for word in words:
        if current:
            last = current[-1]
            same_row = _same_row(word["top"], last["top"], last["size"])
            near = word["x0"] - last["x1"] <= last["size"] * LINE_GAP
            if not (same_row and near):
                lines.append(current)
                current = []
        current.append(word)
    if current:
        lines.append(current)
    return [_line(line) for line in lines]


def _line(words: list[dict]) -> dict:
    sizes = defaultdict(int)
    bold_chars = 0
    for word in words:
        sizes[round(word["size"], 1)] += len(word["text"])
        bold_chars += len(word["text"]) if _bold(word["fontname"]) else 0
    total = sum(len(word["text"]) for word in words)
    return {
        "box": [round(min(w["x0"] for w in words), ROUND), round(min(w["top"] for w in words), ROUND),
                round(max(w["x1"] for w in words), ROUND), round(max(w["bottom"] for w in words), ROUND)],
        "size": max(sizes, key=sizes.get),
        "bold": bold_chars * 2 > total,
        "words": [[w["text"], round(w["x0"], ROUND), round(w["top"], ROUND),
                   round(w["x1"], ROUND), round(w["bottom"], ROUND)] for w in words],
    }


def _page(page, number: int) -> dict:
    entry = {"page": number, "width": round(float(page.width), ROUND),
             "height": round(float(page.height), ROUND), "has_text_layer": bool(page.chars)}
    if not entry["has_text_layer"]:
        return entry
    words = page.extract_words(x_tolerance=X_TOLERANCE, keep_blank_chars=False,
                               extra_attrs=["fontname", "size"])
    entry["lines"] = _lines(words)
    return entry


#: How many lines from a page's top a "Contents" heading may sit.
CONTENTS_HEADING_LINES = 5
#: The most pages one table of contents runs to.
MAX_CONTENTS_PAGES = 10
#: Caps on what a crafted PDF can make the reader store.
MAX_BOOKMARKS = 5000
CONTENTS_HEADING = re.compile(r"^(table of )?contents$", re.IGNORECASE)
OTHER_LIST = re.compile(r"^list of ", re.IGNORECASE)
LABEL = r"(?P<label>\d+|[ivxlcdm]+)"
#: Title, dot leaders, printed page; or title, a wide gap, printed page.
LEADERED = re.compile(r"^(?P<body>.*?\S)\s*(?:[.·…_]\s*){2,}\s*" + LABEL + r"$", re.IGNORECASE)
SPACED = re.compile(r"^(?P<body>.*?\S)\s{2,}" + LABEL + r"$", re.IGNORECASE)
NUMBER = re.compile(r"^(?P<number>(?:chapter|appendix)\s+[\w.]+|\d+(?:\.\d+)*\.?)\s+(?P<title>.+)$",
                    re.IGNORECASE)


def _text(line: dict) -> str:
    return " ".join(word[0] for word in line["words"])


def _rows(lines: list[dict]) -> list[dict]:
    """Lines on one baseline joined left to right, keeping a wide gap as two
    spaces: a right-aligned page number is its own line until then."""
    rows = []
    for line in sorted(lines, key=lambda l: (l["box"][1], l["box"][0])):
        if rows and _same_row(line["box"][1], rows[-1]["box"][1], line["size"]):
            rows[-1] = {"box": rows[-1]["box"], "text": rows[-1]["text"] + "  " + _text(line)}
        else:
            rows.append({"box": line["box"], "text": _text(line)})
    return rows


def _entry(text: str):
    match = LEADERED.match(text) or SPACED.match(text)
    if not match:
        return None
    body = match["body"].strip()
    numbered = NUMBER.match(body)
    number, title = (numbered["number"].rstrip("."), numbered["title"]) if numbered else ("", body)
    return number, title.strip(), match["label"]


def _contents_page(page: dict, first: bool):
    rows = _rows(page.get("lines", []))
    if not rows:
        return None
    if first and not any(CONTENTS_HEADING.match(row["text"].strip())
                         for row in rows[:CONTENTS_HEADING_LINES]):
        return None
    if not first and OTHER_LIST.match(rows[0]["text"].strip()):
        return None
    entries, pending = [], []
    for row in rows:
        text = row["text"].strip()
        if CONTENTS_HEADING.match(text):
            continue
        parsed = _entry(text)
        if parsed is None:
            # A title wrapped onto a second line joins the entry it ends in.
            pending = (pending + [row])[-2:]
            continue
        number, title, label = parsed
        start = pending[0] if pending else row
        if pending:
            joined = _entry(" ".join(p["text"].strip() for p in pending) + " " + text)
            number, title, label = joined or parsed
        entries.append({"x0": start["box"][0], "number": number, "title": title, "page_label": label})
        pending = []
    if not entries or (not first and len(entries) * 2 < len(rows)):
        return None
    left = min(entry["x0"] for entry in entries)
    return [{"page": page["page"], "number": e["number"], "title": e["title"],
             "indent": round(e["x0"] - left, ROUND), "page_label": e["page_label"]} for e in entries]


def _contents(pages: list[dict]) -> list[dict]:
    for start, page in enumerate(pages):
        found = _contents_page(page, first=True)
        if found is None:
            continue
        for following in pages[start + 1:start + MAX_CONTENTS_PAGES]:
            more = _contents_page(following, first=False)
            if more is None:
                break
            found += more
        return found
    return []


def _bookmarks(pdf) -> list[dict]:
    out = []

    def walk(items, level):
        for item in items:
            if len(out) >= MAX_BOOKMARKS:
                raise OverBudget
            if isinstance(item, list):
                walk(item, level + 1)
                continue
            try:
                page = pdf.get_destination_page_number(item)
            except Exception:
                page = None
            out.append({"title": str(item.title or "").strip(), "level": level,
                        "page": page + 1 if page is not None and page >= 0 else None})

    walk(pdf.outline, 1)
    return out


def _page_labels(pdf):
    """The PDF's own labels; pypdf invents "1", "2"... when it has none."""
    if "/PageLabels" not in pdf.trailer["/Root"]:
        return None
    return list(pdf.page_labels)


def read(source, *, max_pages: int) -> dict:
    """The evidence of ``source``, an open binary PDF."""
    import pdfplumber
    from pypdf import PdfReader

    outline = PdfReader(source, strict=False)
    if outline.is_encrypted:
        raise Encrypted
    if len(outline.pages) > max_pages:
        raise OverBudget
    bookmarks, labels = _bookmarks(outline), _page_labels(outline)
    source.seek(0)
    with pdfplumber.open(source) as pdf:
        pages = [_page(page, number) for number, page in enumerate(pdf.pages, start=1)]
    return {"reader": READER, "error": "", "page_count": len(pages), "pages": pages,
            "bookmarks": bookmarks, "page_labels": labels, "contents": _contents(pages)}


# ---------------------------------------------------------------- sandbox child
def _preload():
    """Import, before `confine()`, everything a read loads lazily (as the
    review text reader does, IR-1005): after it no module file can be opened."""
    import codecs

    import pdfminer.cmapdb  # noqa: F401
    import pdfminer.converter  # noqa: F401
    import pdfminer.layout  # noqa: F401
    import pdfminer.pdfdocument  # noqa: F401
    import pdfminer.pdfinterp  # noqa: F401
    import pdfminer.pdfparser  # noqa: F401
    import pdfplumber  # noqa: F401
    import pypdf  # noqa: F401
    import pypdf.generic  # noqa: F401

    for codec in ("latin-1", "utf-16", "utf-16be", "utf-16le", "ascii", "cp1252"):
        codecs.lookup(codec)


def confine():
    """Open no file from here on: cap RLIMIT_NOFILE at the lowest free descriptor
    (``apps/records/review_text/reader.py``; PDF_INTAKE.md §Review text)."""
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
        source = open(path, "rb")
        target = open(out, "w", encoding="utf-8")
        _preload()
        confine()
        result = read(source, max_pages=max_pages)
        json.dump(result, target, ensure_ascii=False)
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
