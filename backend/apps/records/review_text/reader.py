"""The review text reader (ADR-058 §1 as amended 2026-11-05, IR-871).

Reads one manuscript PDF into the sections and passages reviewers compare and
anchor threads to. A passage is one sentence, or one row of a ruled table, with
its page, its paragraph and one rectangle per line in ADR-031's shape
(fractions of the page). Nothing leaves the process: pdfplumber reads the
words and their positions, and everything after that is plain rules.

**Pure.** This file imports pdfplumber and the standard library only: no
Django, no network, no model. It runs as the child of the IR-830 sandbox
(``sandbox.py``), as ``python -I reader.py <pdf> <out.json> <memory MiB>
<max pages>``, and its exit code is the result protocol: 0 read (``out.json``
written), 2 unreadable, 3 encrypted, 5 over the limits. Tests import it and
call ``read()`` directly.

**Changing a rule is a new reader.** Stored text is never re-read in place
(ADR-058 §1 point 5), so a change that can move a sentence, a heading or a
region raises ``RULES_VERSION``. The reader's version is stored on every text.

The rules come from the prototype (``prototype/pdf-version-comparison``),
which passed 59 checks on a thesis-shaped paper, plus three added for IR-871:
headings found by numbering or capitals as well as bold, table-of-contents
lines never taken for headings, and warnings that say when sections may not
have been found.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter

#: Raise on any change that can alter what a stored text says.
RULES_VERSION = 1

#: pdfplumber's default word gap (3 pt) is a 12 pt Times space, so a line that
#: isn't justified came back as one word. Below a space's width (prototype finding 1).
X_TOLERANCE = 1.5
#: The top and bottom bands where running heads and page numbers live.
MARGIN_FRACTION = 0.08
#: A section longer than this many pages may be two sections whose heading was missed.
LONG_SECTION_PAGES = 15
FRONT_MATTER_KEY = "front-matter"

SENTENCE_END = re.compile(r'(?<=[.!?])["”)]?\s+(?=[A-Z(“"])')
ABBREVIATIONS = (
    "et al.", "e.g.", "i.e.", "Fig.", "Figs.", "No.", "Nos.", "vs.", "Dr.", "Mr.", "Ms.",
    "Mrs.", "Prof.", "Engr.", "St.", "Jr.", "Sr.", "pp.", "p.", "Vol.", "cf.", "Eq.",
)
NUMBERING = re.compile(r"^(chapter\s+([0-9]+|[ivxlc]+)\b[\s.:-]*|\d+(\.\d+)*\.?\s+)", re.I)
CHAPTER = re.compile(r"chapter\s+([0-9]+|[IVXLC]+)\.?", re.I)
MULTI_LEVEL = re.compile(r"^\d+(\.\d+)+\.?\s+\S")
SINGLE_LEVEL = re.compile(r"^\d+\.?\s+(\S.*)$")
CAPTION = re.compile(r"^(table|figure|fig\.|plate|appendix)\s*[0-9A-Z]", re.I)
DOT_LEADER = re.compile(r"(\.\s?){4,}|…{2,}")
TRAILING_PAGE = re.compile(r"\s\d{1,3}$")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class Unreadable(Exception):
    pass


class Encrypted(Exception):
    pass


class OverBudget(Exception):
    pass


def reader_version() -> str:
    import pdfplumber

    return f"review-reader-{RULES_VERSION}/pdfplumber-{pdfplumber.__version__}"


def norm(text: str) -> str:
    """Text as compared, never as stored: compatibility forms (ligatures),
    straight quotes and single spaces (ADR-058 §3)."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip()


def _clean(text: str) -> str:
    # PostgreSQL's JSON can't hold NUL, and no control character is text.
    return CONTROL.sub("", text)


# ---------------------------------------------------------------- reading
def read(path, max_pages: int | None = None) -> dict:
    """The review text of the PDF at ``path`` (a path, or a binary file
    already open), as the JSON-ready dict ``store`` writes.

    ``sections`` is empty when the PDF has no text layer (a scan).
    """
    import pdfplumber
    from pdfminer.pdfdocument import PDFEncryptionError, PDFPasswordIncorrect

    pages = []
    try:
        with pdfplumber.open(path) as pdf:
            if max_pages is not None and len(pdf.pages) > max_pages:
                raise OverBudget
            for page in pdf.pages:
                pages.append(_read_page(page))
    except (PDFPasswordIncorrect, PDFEncryptionError) as exc:
        raise Encrypted from exc
    except (OverBudget, MemoryError, RecursionError):
        raise
    except Exception as exc:  # pdfminer raises many kinds for a broken file
        raise Unreadable from exc
    if not pages:
        raise Unreadable

    sections, warnings = _structure(pages)
    return {
        "reader": reader_version(),
        "page_count": len(pages),
        "sections": sections,
        "warnings": warnings,
    }


def _read_page(page) -> dict:
    number, width, height = page.page_number, float(page.width), float(page.height)
    words = page.extract_words(extra_attrs=["fontname", "size"], keep_blank_chars=False,
                               x_tolerance=X_TOLERANCE)
    for w in words:
        w["text"] = _clean(w["text"])
        w["page"] = number
    words = [w for w in words if w["text"].strip()]
    tables = page.find_tables()
    boxes = [t.bbox for t in tables]

    def inside(w):
        return any(b[0] <= w["x0"] and w["x1"] <= b[2] and b[1] <= w["top"] and w["bottom"] <= b[3]
                   for b in boxes)

    rows = []
    for table in tables:
        for cells, row in zip(table.extract(), table.rows):
            text = _clean(" | ".join((c or "").replace("\n", " ") for c in cells)).strip(" |")
            if text:
                rows.append({"text": text, "top": row.bbox[1], "bbox": row.bbox})
    margin = height * MARGIN_FRACTION
    columns = _columns([w for w in words if not inside(w)], width, height, margin)
    return {"number": number, "width": width, "height": height, "margin": margin,
            "columns": columns, "rows": rows, "has_words": bool(words)}


def _lines(words):
    lines = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if lines and abs(lines[-1][0]["top"] - w["top"]) < 2.5:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def _columns(words, width, height, margin):
    """Split a page into columns at a vertical gutter no body word crosses."""
    body = [w for w in words if margin < w["top"] < height - margin]
    if len(body) < 20:
        return [words]
    for x in range(int(width * 0.3), int(width * 0.7)):
        if all(not (w["x0"] - 2 < x < w["x1"] + 2) for w in body):
            left = [w for w in body if w["x1"] <= x]
            right = [w for w in body if w["x0"] >= x]
            if len(left) > 10 and len(right) > 10:
                in_body = lambda w: margin < w["top"] < height - margin  # noqa: E731
                return [[w for w in words if w["x1"] <= x or not in_body(w)],
                        [w for w in words if w["x0"] >= x and in_body(w)]]
    return [words]


def _line_text(line):
    return " ".join(w["text"] for w in line)


def _stream(pages):
    """Every body line and table row in reading order, running heads dropped."""
    # Running heads and page numbers: margin lines that repeat on most pages
    # once digits are ignored, or a bare number in a margin.
    margin_text = Counter()
    for p in pages:
        for col in p["columns"]:
            for line in _lines(col):
                if line[0]["top"] < p["margin"] or line[0]["top"] > p["height"] - p["margin"]:
                    margin_text[re.sub(r"\d+", "#", _line_text(line))] += 1
    repeated = {t for t, n in margin_text.items() if n >= max(2, len(pages) // 2)}

    stream = []
    for p in pages:
        for ci, col in enumerate(p["columns"]):
            items = []
            for line in _lines(col):
                text = _line_text(line)
                top = line[0]["top"]
                in_margin = top < p["margin"] or top > p["height"] - p["margin"]
                if in_margin and (re.sub(r"\d+", "#", text) in repeated
                                  or re.fullmatch(r"[-–—\s]*\d{1,4}[-–—\s]*", text)):
                    continue
                items.append(("line", p["number"], line, top))
            if ci == 0:
                items += [("row", p["number"], r, r["top"]) for r in p["rows"]]
            stream += sorted(items, key=lambda it: it[3])
    return stream


def _is_heading(line):
    """Bold, or numbered, or in capitals, and shaped like a heading."""
    text = _line_text(line).strip()
    if not text or len(text) > 100 or text.endswith((".", ",", ";", ":", "?", "!")):
        return False
    if DOT_LEADER.search(text) or CAPTION.match(text):
        return False   # a table-of-contents line, or a caption
    if all("bold" in (w.get("fontname") or "").lower() for w in line):
        return True
    words = text.split()
    if len(words) > 12 or (TRAILING_PAGE.search(text) and not CHAPTER.fullmatch(text)):
        return False
    if CHAPTER.fullmatch(text) or MULTI_LEVEL.match(text):
        return True
    single = SINGLE_LEVEL.match(text)
    if single and all(w[:1].isupper() for w in single.group(1).split() if len(w) >= 4):
        return True
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 4 and all(c.isupper() for c in letters)


def _caps(text):
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def _continues(heading, line):
    """Is ``line`` the second line of ``heading``, not a subheading under it?
    A numbered line starts its own heading, and so does a change of case, as
    "INTRODUCTION" followed by "Background of the Study"."""
    return not NUMBERING.match(line.strip()) and _caps(heading) == _caps(line)


def _structure(pages):
    stream = _stream(pages)
    lines = [it for it in stream if it[0] == "line"]
    tops = [it[3] for it in lines]
    gaps = Counter(round(b - a) for a, b in zip(tops, tops[1:]) if 0 < b - a < 40)
    line_gap = gaps.most_common(1)[0][0] if gaps else 14
    body_x = Counter(round(it[2][0]["x0"]) for it in lines)
    left_margins = sorted(x for x, n in body_x.items() if n >= 3)
    # Every whole word on any page, to decide whether a line-end hyphen is a
    # compound's own (prototype finding 3).
    known = {re.sub(r"[^\w-]", "", w["text"]).lower() for it in lines for w in it[2]}

    sections = [{"heading": "", "page": 1, "passages": []}]
    para, paragraph = [], [0]
    last_top, pending_chapter, prev_heading = None, None, None

    def margin_of(x):
        return max([m for m in left_margins if m <= x + 1] or [x])

    def flush():
        if para:
            paragraph[0] += 1
            sections[-1]["passages"].extend(_sentences(para, known, paragraph[0], pages))
            para.clear()

    for it in stream:
        if it[0] == "row":
            flush()
            paragraph[0] += 1
            row = it[2]
            sections[-1]["passages"].append({
                "text": row["text"], "page": it[1], "paragraph": paragraph[0], "kind": "row",
                "regions": _normalize([(it[1], *row["bbox"])], pages),
            })
            continue
        _, page, line, top = it
        text = _line_text(line)
        if _is_heading(line):
            flush()
            if CHAPTER.fullmatch(text.strip()):
                pending_chapter = (text.strip(), page)
                continue
            if pending_chapter:
                text, page = f"{pending_chapter[0]} {text}", pending_chapter[1]
                pending_chapter = None
            elif (prev_heading and prev_heading[0] == page and top - prev_heading[1] < 30
                  and not sections[-1]["passages"] and _continues(sections[-1]["heading"], text)):
                sections[-1]["heading"] += " " + text   # a heading that wraps onto a second line
                prev_heading = (page, top)
                continue
            sections.append({"heading": text, "page": page, "passages": []})
            prev_heading = (page, top)
            last_top = top
            continue
        if pending_chapter:
            # "CHAPTER 2" with no title line after it is a heading on its own.
            sections.append({"heading": pending_chapter[0], "page": pending_chapter[1], "passages": []})
            pending_chapter = None
        indented = line[0]["x0"] > margin_of(line[0]["x0"]) + 20 or (
            line[0]["x0"] - min(left_margins or [line[0]["x0"]]) > 20)
        gap = bool(para) and last_top is not None and page == para[-1][1] and top - last_top > line_gap * 1.6
        if para and (indented or gap):
            flush()
        para.extend((w["text"], page, w) for w in line)
        para.append(("\n", page, None))
        last_top = top
    flush()
    if pending_chapter:
        sections.append({"heading": pending_chapter[0], "page": pending_chapter[1], "passages": []})

    if not sections[0]["passages"]:
        sections.pop(0)
    if not any(s["passages"] for s in sections):
        return [], []
    return _finish(sections, pages)


def _finish(sections, pages):
    """Give each section its key and hash, and say what may be wrong."""
    seen = Counter()
    out = []
    for s in sections:
        base = ((NUMBERING.sub("", norm(s["heading"]).lower()).strip() if s["heading"] else "")
                or FRONT_MATTER_KEY)[:240]   # cut before the suffix, so `#2` always survives
        seen[base] += 1
        key = base if seen[base] == 1 else f"{base}#{seen[base]}"
        digest = hashlib.sha256("\n".join(norm(p["text"]) for p in s["passages"]).encode()).hexdigest()
        out.append({"key": key, "heading": s["heading"], "page": s["page"],
                    "text_hash": digest, "passages": s["passages"]})

    warnings = []
    if all(s["key"] == FRONT_MATTER_KEY for s in out):
        warnings.append({"code": "no_headings"})
    for s in out:
        last = max((p["page"] for p in s["passages"]), default=s["page"])
        if last - s["page"] + 1 > LONG_SECTION_PAGES:
            warnings.append({"code": "long_section", "section": s["key"], "pages": last - s["page"] + 1})
    blank = [p["number"] for p in pages if not p["has_words"]]
    if blank:
        warnings.append({"code": "pages_without_text", "pages": blank[:50]})
    return out, warnings


def _sentences(para, known, paragraph, pages):
    # Join lines; repair a word hyphenated across a line break.
    tokens = []   # (text, [words])
    i = 0
    while i < len(para):
        t, _page, w = para[i]
        if t == "\n":
            i += 1
            continue
        nxt = para[i + 2] if i + 2 < len(para) and para[i + 1][0] == "\n" else None
        if t.endswith("-") and len(t) > 1 and nxt and nxt[0][:1].isalpha():
            head, tail = t[:-1], nxt[0]
            compound = re.sub(r"[^\w-]", "", head + "-" + tail).lower()
            if "-" in head or tail[:1].isupper() or compound in known:
                joined = head + "-" + tail       # a compound broken at its own hyphen
            else:
                joined = head + tail             # a word hyphenated to fit the line
            tokens.append((joined, [w, nxt[2]]))
            i += 3
            continue
        tokens.append((t, [w]))
        i += 1

    text, spans = "", []
    for t, ws in tokens:
        if text:
            text += " "
        spans.append((len(text), len(text) + len(t), ws))
        text += t

    def splits_here(m):
        before = text[:m.start()].rstrip('"”)')
        if any(before.endswith(a) for a in ABBREVIATIONS):
            return False
        # An initial, as in "J. Cruz", ends no sentence.
        return not re.search(r"(^|\s)[A-Z]\.$", before)

    out, start = [], 0
    for end in [m.end() for m in SENTENCE_END.finditer(text) if splits_here(m)] + [len(text)]:
        chunk = text[start:end].strip()
        if chunk:
            ws = [w for s, e, wl in spans if s < end and e > start for w in wl if w]
            boxes = _line_boxes(ws)
            out.append({"text": chunk, "page": boxes[0][0] if boxes else ws[0]["page"],
                        "paragraph": paragraph, "kind": "sentence",
                        "regions": _normalize(boxes, pages)})
        start = end
    return out


def _line_boxes(words):
    """One rectangle per line, in points: (page, x0, top, x1, bottom)."""
    lines = {}
    for w in words:
        key = (w["page"], round(w["top"]))
        box = lines.setdefault(key, [w["page"], w["x0"], w["top"], w["x1"], w["bottom"]])
        box[1], box[2] = min(box[1], w["x0"]), min(box[2], w["top"])
        box[3], box[4] = max(box[3], w["x1"]), max(box[4], w["bottom"])
    return [tuple(b) for b in lines.values()]


def _normalize(boxes, pages):
    """ADR-031's shape: fractions of the page, clamped, degenerate ones withheld."""
    sizes = {p["number"]: (p["width"], p["height"]) for p in pages}
    out = []
    for page, x0, top, x1, bottom in boxes:
        width, height = sizes[page]
        clamp = lambda v: min(1.0, max(0.0, v))  # noqa: E731
        left, right = clamp(x0 / width), clamp(x1 / width)
        top_f, bottom_f = clamp(top / height), clamp(bottom / height)
        if right > left and bottom_f > top_f:
            out.append({"page": page, "left": round(left, 4), "top": round(top_f, 4),
                        "right": round(right, 4), "bottom": round(bottom_f, 4)})
    return out


# ---------------------------------------------------------------- sandbox child
def _preload():
    """Import, before `confine()`, everything a read loads lazily, since after
    it no module file can be opened. A CMap file pdfminer would load from disk
    (rare, for some non-Latin fonts) then fails closed, as unreadable."""
    import pdfminer.cmapdb  # noqa: F401
    import pdfminer.converter  # noqa: F401
    import pdfminer.layout  # noqa: F401
    import pdfminer.pdfdocument  # noqa: F401
    import pdfminer.pdfinterp  # noqa: F401
    import pdfminer.pdfparser  # noqa: F401
    import pdfplumber  # noqa: F401
    import pdfplumber.table  # noqa: F401

    for codec in ("latin-1", "utf-16be", "utf-16le", "ascii", "cp1252"):
        b"".decode(codec)


def confine():
    """Open no file from here on (IR-871 review, PDF_INTAKE.md §Review text).

    The reader is the one sandbox child that sends data back, so a parser
    taken over by a crafted PDF must not be able to read anything to send:
    not the worker's environment under /proc, not another paper. The child
    has already opened its input and output, so it caps RLIMIT_NOFILE at the
    lowest free descriptor. A new descriptor always takes the lowest free
    number, so every later open, socket or pipe is refused with EMFILE.
    """
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
