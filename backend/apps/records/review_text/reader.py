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
RULES_VERSION = 2

#: pdfplumber's default word gap (3 pt) is a 12 pt Times space, so a line that
#: isn't justified came back as one word. Below a space's width (prototype finding 1).
X_TOLERANCE = 1.5
#: The top and bottom bands a column split leaves whole.
MARGIN_FRACTION = 0.08
#: The top and bottom bands searched for running heads, footers and page
#: numbers. Wider than the margin: a journal footer sat at 91.6% of the page.
RUNNING_BAND = 0.12
#: A section longer than this many pages may be two sections whose heading was missed.
LONG_SECTION_PAGES = 15
#: The most lines one heading wraps onto. A list of capitals lines (a form,
#: a table without rules) is many headings, which `_unreliable` then refuses.
HEADING_LINES = 3
#: How near the column's right edge, as a share of its width, a line ends to
#: have run on to the next. Generous on purpose: ragged-right lines end tens
#: of points apart, and gluing two paragraphs costs little, since each
#: sentence is still its own passage, while cutting a sentence breaks it.
RAN_ON = 0.10
#: The fewest lines a two-column band can be.
MIN_COLUMN_LINES = 5
#: How far right of its column's left edge a line starts to be a first-line
#: indent. A journal's 17 pt indent was missed at the prototype's 20.
INDENT = 10
FRONT_MATTER_KEY = "front-matter"
#: The one section a paper is stored as when its sections can't be trusted.
DOCUMENT_KEY = "document"
#: Above this share of words with no character behind them (U+FFFD, or
#: pdfminer's "(cid:N)"), the text is unreadable and none is stored.
UNREADABLE_SHARE = 0.2
#: A font size this many points off the paragraph's starts a new one: a
#: footnote, caption or block quote is never glued into a body sentence.
SIZE_BREAK = 1.0
#: A short line this many points larger than the body is a heading (sample21:
#: 12 pt headings over a 10 pt body, in fonts not named bold).
HEADING_SIZE = 1.5

SENTENCE_END = re.compile(r'(?<=[.!?])["”)]?\s+(?=[A-Z(“"])')
ABBREVIATIONS = (
    "et al.", "e.g.", "i.e.", "Fig.", "Figs.", "No.", "Nos.", "vs.", "Dr.", "Mr.", "Ms.",
    "Mrs.", "Prof.", "Engr.", "St.", "Jr.", "Sr.", "pp.", "p.", "Vol.", "cf.", "Eq.",
)
#: A heading's numbering, dropped from its key so a renumbered section is the
#: same section: "CHAPTER 2", "2.1", and roman "II." or lettered "A." too.
NUMBERING = re.compile(
    r"^(chapter\s+([0-9]+|[ivxlc]+)\b[\s.:-]*|\d+(\.\d+)*\.?\s+|[ivxlc]+\.\s+|[a-z]\.\s+)", re.I)
CHAPTER = re.compile(r"chapter\s+([0-9]+|[IVXLC]+)\.?", re.I)
# Section numbers run to two digits; a year or a DOI ("10.2190/...") is no numbering.
MULTI_LEVEL = re.compile(r"^\d{1,2}(\.\d{1,2})+\.?\s+\S")
SINGLE_LEVEL = re.compile(r"^\d{1,2}\.?\s+(\S.*)$")
CAPTION = re.compile(r"^(table|figure|fig\.|plate|appendix)\s*[0-9A-Z]", re.I)
DOT_LEADER = re.compile(r"(\.\s?){4,}|…{2,}")
TRAILING_PAGE = re.compile(r"\s\d{1,3}$")
PAGE_NUMBER = re.compile(r"[-–—\s]*\d{1,4}[-–—\s]*")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


UNMAPPED = re.compile(r"\ufffd|\(cid:\d+\)")


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
            _drop_running(pages)
            for p in pages:
                p["columns"] = _columns(p.pop("words"), p["width"], p["height"], p["margin"])
    except (PDFPasswordIncorrect, PDFEncryptionError) as exc:
        raise Encrypted from exc
    except (OverBudget, MemoryError, RecursionError):
        raise
    except Exception as exc:  # pdfminer raises many kinds for a broken file
        raise Unreadable from exc
    if not pages:
        raise Unreadable

    sections, warnings = _structure(pages)
    share = _unmapped_share(sections)
    if share > UNREADABLE_SHARE:
        raise Unreadable   # stored as "No text for vN", never as nonsense
    if share:
        warnings.append({"code": "unmapped_characters", "share": round(share, 3)})
    return {
        "reader": reader_version(),
        "page_count": len(pages),
        "sections": sections,
        "warnings": warnings,
    }


def _join_touching(words, spaces=()):
    """Rejoin a word split where its font changes: pdfplumber starts a new word
    at every font change, and some publishers set ligatures, apostrophes and
    dashes in a second font ("arti fi cial", "Nursing ' s"). Pieces in
    different fonts, closer than a space, on the same line and in the same
    size, with no space character between them (a tightly justified line can
    set a space narrower than that), are one word, in the font of most of its
    letters, so a bold heading is still found. ``spaces`` are the page's
    space characters."""
    def spaced(left, right):
        # A narrow space can overlap the next letter, so it need only start in the gap.
        return any(abs(s["top"] - right["top"]) < 2 and left["x1"] - 0.5 <= s["x0"] <= right["x0"] + 0.5
                   for s in spaces)

    out, last_font = [], None
    for w in (w for line in _lines(words) for w in line):
        prev = out[-1] if out else None
        if (prev and w.get("fontname") != last_font and abs(prev["top"] - w["top"]) < 1
                and -1 <= w["x0"] - prev["x1"] < X_TOLERANCE
                and abs(float(prev.get("size") or 0) - float(w.get("size") or 0)) < 0.1
                and not spaced(prev, w)):
            font = prev["fontname"] if len(prev["text"]) >= len(w["text"]) else w["fontname"]
            out[-1] = dict(prev, text=prev["text"] + w["text"], x1=w["x1"], fontname=font,
                           bottom=max(prev["bottom"], w["bottom"]))
        else:
            out.append(w)
        last_font = w.get("fontname")
    return out


def _join_small_caps(words):
    """Rejoin a small-capitals word split after its larger first letter, as
    "I NTRODUCTION": a single capital, then capitals in a smaller size, less
    than 3 pt apart or touching (pdfplumber splits a word where its size
    changes), on the same line."""
    out = []
    for w in (w for line in _lines(words) for w in line):   # a smaller size sits lower
        prev = out[-1] if out else None
        if (prev and len(prev["text"]) == 1 and prev["text"].isupper()
                and abs(prev["top"] - w["top"]) < 3 and -1 <= w["x0"] - prev["x1"] < 3
                and w["text"][:1].isupper() and w["text"].replace("-", "").isalpha()
                and w["text"].isupper() and float(prev.get("size") or 0) > float(w.get("size") or 0) + 0.5):
            prev = dict(prev, text=prev["text"] + w["text"], x1=w["x1"], bottom=max(prev["bottom"], w["bottom"]))
            out[-1] = prev
            continue
        out.append(w)
    return out


def _unmapped_share(sections) -> float:
    """The share of words the PDF gives no character for, as a font with no
    Unicode map does. pypdf reads the same marks: nothing can be recovered."""
    words = [w for s in sections for p in s["passages"] for w in p["text"].split()]
    return sum(1 for w in words if UNMAPPED.search(w)) / len(words) if words else 0.0


WHITE = ((1,), (1, 1, 1), (0, 0, 0, 0))   # grey, RGB and CMYK


def _visible(obj) -> bool:
    """Whether a page object can be seen, for finding tables. A box filled
    white with no border, or with neither fill nor border, is drawn behind
    text by some exporters, one per line; its edges are no table's rules."""
    if obj.get("object_type") != "rect" or obj.get("stroke"):
        return True
    if not obj.get("fill"):
        return False
    colour = obj.get("non_stroking_color")
    if colour is None:
        return True   # no colour given fills black
    colour = tuple(colour) if isinstance(colour, (list, tuple)) else (colour,)
    try:
        return tuple(round(float(v), 3) for v in colour) not in WHITE
    except (TypeError, ValueError):
        return True   # a pattern or a named colour: assume it shows


def _read_page(page) -> dict:
    number, width, height = page.page_number, float(page.width), float(page.height)
    words = page.extract_words(extra_attrs=["fontname", "size"], keep_blank_chars=False,
                               x_tolerance=X_TOLERANCE)
    for w in words:
        w["text"] = _clean(w["text"])
        w["page"] = number
    spaces = [c for c in page.chars if c["text"].isspace()]
    words = _join_small_caps(_join_touching([w for w in words if w["text"].strip()], spaces))
    # Only a grid of two columns or more is a table. A stack of one-cell boxes
    # is a bordered or shaded paragraph (Word draws one box per line), whose
    # text reads as ordinary lines, not as one "row" per line.
    tables = [t for t in page.filter(_visible).find_tables()
              if max((len(r) for r in t.extract()), default=0) >= 2]
    boxes = [t.bbox for t in tables]

    def inside(w):
        # 2 pt of slack: a line's last word can overhang a cell's border, and
        # was then read twice, once in the row and once as ordinary text.
        return any(b[0] - 2 <= w["x0"] and w["x1"] <= b[2] + 2 and b[1] - 2 <= w["top"]
                   and w["bottom"] <= b[3] + 2 for b in boxes)

    rows = []
    for table in tables:
        for cells, row in zip(table.extract(), table.rows):
            text = _clean(" | ".join((c or "").replace("\n", " ") for c in cells)).strip(" |")
            if text:
                rows.append({"text": text, "top": row.bbox[1], "bbox": row.bbox})
    return {"number": number, "width": width, "height": height,
            "margin": height * MARGIN_FRACTION, "words": [w for w in words if not inside(w)],
            "rows": rows, "has_words": bool(words)}


def _drop_running(pages):
    """Drop running heads, footers and page numbers from every page.

    A line in the top or bottom band, read across the page's whole width
    before any column split (a footer can span both columns), that repeats on
    most pages (at least three) once digits are ignored, or is a bare page
    number. A "CHAPTER N" line is never one, though each chapter opens at
    the top of a page.
    """
    def band_lines(p):
        band = p["height"] * RUNNING_BAND
        return [line for line in _lines(p["words"])
                if line[0]["top"] < band or line[0]["top"] > p["height"] - band]

    def signature(line):
        return re.sub(r"\d+", "#", _line_text(line))

    counts = Counter()
    for p in pages:
        counts.update({signature(line) for line in band_lines(p)})
    repeated = {t for t, n in counts.items() if n >= max(3, len(pages) // 2)}
    for p in pages:
        drop = {id(w) for line in band_lines(p)
                if not CHAPTER.fullmatch(_line_text(line).strip())
                and (signature(line) in repeated or PAGE_NUMBER.fullmatch(_line_text(line)))
                for w in line}
        p["words"] = [w for w in p["words"] if id(w) not in drop]


def _lines(words):
    lines = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if lines and abs(lines[-1][0]["top"] - w["top"]) < 2.5:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def _columns(words, width, height, margin):
    """Split a page into columns at a vertical gutter.

    A gutter is an x no body word crosses, except on lines that span the
    page: any number above or below the columns, such as a journal's title
    and authors over a two-column abstract, and at most 10% of the lines
    between them, which must be at least `MIN_COLUMN_LINES` lines tall, so
    two lines of prose that happen to share a gap are never columns. Spanning lines are read whole, with the left column; the
    rest split at the gutter. With none, the page is one column.
    """
    body = [w for w in words if margin < w["top"] < height - margin]
    if len(body) < 20:
        return [words]
    lines = _lines(body)
    best = None
    # 20-80%: a journal's narrow side column (article history, e-mail) sits
    # outside a 30-70% search and was read into the abstract.
    for x in range(int(width * 0.2), int(width * 0.8)):
        crossing = [line for line in lines if any(w["x0"] - 2 < x < w["x1"] + 2 for w in line)]
        span = {id(w) for line in crossing for w in line}
        right_tops = [w["top"] for w in body if id(w) not in span and w["x0"] >= x]
        if not right_tops:
            continue
        # Only spanning lines inside the columns' height interrupt them.
        band = [line for line in lines if min(right_tops) <= line[0]["top"] <= max(right_tops)]
        inside = sum(1 for line in crossing if min(right_tops) <= line[0]["top"] <= max(right_tops))
        if (len(band) < MIN_COLUMN_LINES or inside > 0.1 * len(band)
                or (best and inside >= best[0])):
            continue
        left_words = [w for w in body if id(w) not in span and w["x1"] <= x]
        if left_words and all(LIST_NUMBER.fullmatch(w["text"]) or w["text"].isdigit() for w in left_words):
            continue   # a strip of "[18]" labels, or section or line numbers, is no column
        left = len(left_words)
        if left > 10 and len(right_tops) > 10:
            best = (inside, x, span)
            if not inside:
                break
    if best is None:
        return [words]
    _, x, span = best
    in_body = lambda w: margin < w["top"] < height - margin  # noqa: E731
    return [[w for w in words if id(w) in span or not in_body(w) or w["x1"] <= x],
            [w for w in words if id(w) not in span and in_body(w) and w["x0"] >= x]]


def _column_left(lines) -> float:
    """A column's commonest line start, which a column's first line is
    measured against; every later line is measured against the line before
    it (`_structure`)."""
    return Counter(round(line[0]["x0"]) for line in lines).most_common(1)[0][0] if lines else 0


#: A list item's mark, alone or leading its first word.
BULLETS = "●•▪◦○■□➢➤✓✔◆◇►▸-–*"


#: A numbered or lettered list item's mark: "1.", "2)", "(3)", "a.", "b)",
#: or a numbered reference's "[18]".
LIST_NUMBER = re.compile(r"\(?(\d{1,2}|[a-z])[.)]|\[\d{1,3}\]")


#: Fonts whose every character is a symbol: a Word bullet set in one reads
#: as a letter ("l" in Wingdings is a round bullet).
SYMBOL_FONTS = ("wingdings", "webdings", "symbol", "zapfdingbats", "dingbats")


def _is_mark(word) -> bool:
    """A single list mark: a bullet character, a private-use character (Word's
    default Symbol bullet reads as U+F0B7), any one character in a symbol font,
    or one glyph with no character behind it ("(cid:127)")."""
    text = word["text"]
    if UNMAPPED.fullmatch(text):
        return True   # a lone glyph with no character, as a bullet's font often has
    if len(text) != 1:
        return False
    font = (word.get("fontname") or "").lower()
    return text in BULLETS or 0xE000 <= ord(text) <= 0xF8FF or any(f in font for f in SYMBOL_FONTS)


def _bullet_text_x(line):
    """Where a list item's text starts, if ``line`` opens one, else None."""
    first = line[0]["text"]
    if (LIST_NUMBER.fullmatch(first) or _is_mark(line[0])) and len(line) > 1:
        return line[1]["x0"]
    if first and first[0] in BULLETS and (len(first) == 1 or not first[1].isalnum() or first[0] not in "-–*"):
        if len(first) == 1:
            return line[1]["x0"] if len(line) > 1 else None
        return line[0]["x0"]
    return None


URL = re.compile(r"(https?://|www\.|doi\.org/|10\.\d{4,}/)", re.I)


def _ends_entry(word) -> bool:
    """Can a paragraph end on ``word``? A full stop, question or exclamation
    mark (before any closing quote or bracket), or a web address, as a
    reference entry ends on its DOI."""
    return bool(re.search(r"[.!?][\"”’')\]]*$", word) or URL.search(word))


def _continues_text(word) -> bool:
    """Does a line opening on ``word`` carry on what came before? Lower case,
    or a web address wrapped onto its own line."""
    return word[:1].islower() or bool(URL.match(word))


def _began_at(first, body, page, column) -> float:
    """Where the current paragraph began, in this column: its first line's
    position if that is here, else this column's body margin moved by the
    first line's distance from its body. Unknown means no limit."""
    if first is None:
        return float("inf")
    if first[:2] == (page, column):
        return first[2]
    if first[3] is not None and body is not None:
        return body[2] + first[3]
    return float("inf")


def _size(line) -> float:
    """The size most of a line is set in, so a larger bullet doesn't count."""
    return Counter(round(float(w.get("size") or 0), 1) for w in line).most_common(1)[0][0]


def _line_text(line):
    return " ".join(w["text"] for w in line)


def _stream(pages):
    """Every body line and table row in reading order (running heads are
    already gone, `_drop_running`)."""
    stream = []
    for p in pages:
        for ci, col in enumerate(p["columns"]):
            lines = _lines(col)
            # The column's own left edge, which a first-line indent is measured from.
            left = _column_left(lines)
            right = max((line[-1]["x1"] for line in lines), default=0)
            leftmost = min((line[0]["x0"] for line in lines), default=0)
            items = [("line", p["number"], line, line[0]["top"], left, ci, right, leftmost) for line in lines]
            if ci == 0:
                items += [("row", p["number"], r, r["top"], None, ci, None, None) for r in p["rows"]]
            stream += sorted(items, key=lambda it: it[3])
    return stream


def _wordy(text) -> bool:
    """Is ``text`` made of words, as a heading is? Not an identifier
    ("ICCOINS.2016.7783277", "QUADCOPTER_CONTROL"), a DOI, a year range or a
    bare number, which references and charts are full of: at least four
    letters, no underscore or slash, and at least half its tokens words."""
    tokens = NUMBERING.sub("", text).split()
    if not tokens or any("_" in t or "/" in t for t in tokens):
        return False
    words = [t for t in tokens if sum(c.isalpha() for c in t) >= 2 and not any(c.isdigit() for c in t)]
    return sum(c.isalpha() for c in text) >= 4 and len(words) * 2 >= len(tokens)


BOLD_NAME = re.compile(r"bold|black|heavy|semibold|demi|[.,+\-_](b|bd|bi)$", re.I)


def is_bold(fontname) -> bool:
    """Whether a font's name says bold: "Arial-BoldMT", "Calibri,Bold",
    "Helvetica-Black", or a short suffix as "…AdvOTab3e3698.B" or "-BI"."""
    return bool(BOLD_NAME.search(fontname or ""))


def _heading_words(text) -> bool:
    """Whether a larger line reads as a heading's words, not a formula (a math
    symbol or a Greek letter) or an author line (an asterisk, three commas, or
    a bare number marking an affiliation)."""
    if any(unicodedata.category(c) == "Sm" or "Ͱ" <= c <= "Ͽ" for c in text):
        return False
    if "*" in text or text.count(",") >= 3:
        return False
    return not any(t.isdigit() for t in text.split())


def _is_heading(line, body_size=None):
    """Bold, or numbered, or in capitals, or larger than the body (``body_size``),
    and shaped like a heading."""
    text = _line_text(line).strip()
    if not text or len(text) > 100 or text.endswith((".", ",", ";", ":", "?", "!")):
        return False
    if CHAPTER.fullmatch(text):
        return True   # all numbering, which `_wordy` would strip to nothing
    if not _wordy(text):
        return False
    first_letter = next((c for c in NUMBERING.sub("", text) if c.isalpha()), "")
    if first_letter.islower():
        return False   # a bold word in mid-sentence, alone on its line
    if DOT_LEADER.search(text) or CAPTION.match(text):
        return False   # a table-of-contents line, or a caption
    if all(is_bold(w.get("fontname")) for w in line):
        return True
    words = text.split()
    if len(words) > 12 or (TRAILING_PAGE.search(text) and not CHAPTER.fullmatch(text)):
        return False
    if body_size and _size(line) >= body_size + HEADING_SIZE and _heading_words(text):
        return True   # set larger than the body, as some journals mark headings
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


def _font(line):
    return (line[0].get("fontname") or "", round(float(line[0].get("size") or 0), 1))


def _continues(section, line):
    """Is ``line`` the second line of ``section``'s heading, not a subheading
    under it? Only in the same font and size: "Materials and Methods" (12 pt
    bold) over "Review Design" (11 pt bold italic) is two headings. A numbered
    line starts its own heading, and so does a change of case, as
    "INTRODUCTION" followed by "Background of the Study"."""
    text = _line_text(line)
    return (section.get("font") == _font(line) and not NUMBERING.match(text.strip())
            and _caps(section["heading"]) == _caps(text))


def _word(text):
    return re.sub(r"[^\w-]", "", text).lower()


def _keeps_hyphen(head, tail, known):
    """Is "head-" at a line end, followed by "tail", a compound's own hyphen?

    Decided by how the paper itself spells the word elsewhere (prototype
    finding 3), counting both spellings: "small-scale" seen whole, and
    "smallscale" never, keeps it; "adjustment" seen more often than
    "ad-justment" drops it. A handful of stray mid-line hyphens, as text pasted
    from a PDF leaves, no longer decides every other break of the word.
    """
    if "-" in head or tail[:1].isupper():
        return True
    return known[_word(head + "-" + tail)] > known[_word(head + tail)]


def _join_heading(heading, text, known):
    """A wrapped heading's two lines, a line-end hyphen decided as in body text."""
    if heading.endswith("-") and text[:1].islower():
        head = heading[:-1].split()[-1]
        return (heading if _keeps_hyphen(head, text.split()[0], known) else heading[:-1]) + text
    return f"{heading} {text}"


def _structure(pages):
    stream = _stream(pages)
    lines = [it for it in stream if it[0] == "line"]
    tops = [it[3] for it in lines]
    gaps = Counter(round(b - a) for a, b in zip(tops, tops[1:]) if 0 < b - a < 40)
    line_gap = gaps.most_common(1)[0][0] if gaps else 14
    # How often the paper spells each word, to decide whether a line-end
    # hyphen is a compound's own (`_keeps_hyphen`).
    known = Counter(_word(w["text"]) for it in lines for w in it[2])
    sizes = Counter(round(float(w.get("size") or 0), 1) for it in lines for w in it[2])
    body_size = sizes.most_common(1)[0][0] if sizes else None

    sections = [{"heading": "", "page": 1, "passages": []}]
    para, paragraph, para_size, hang, prev_line, body_x = [], [0], [None], [None], [None], [None]
    last_body = [None]   # the body margin of the latest paragraph, kept across columns
    first_x = [None]     # where the current paragraph's first line began
    last_top, pending_chapter, prev_heading = None, None, None

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
        _, page, line, top, column_left, column, column_right, column_min = it
        text = _line_text(line)
        # The second half of a heading broken at a hyphen, as "Accom-" over
        # "modation": no heading by itself, since it starts in lower case.
        hyphen_wrap = (prev_heading and prev_heading[0] == page and top - prev_heading[1] < 30
                       and not para and not sections[-1]["passages"]
                       and sections[-1]["heading"].endswith("-") and text[:1].islower()
                       and _continues(sections[-1], line))
        if hyphen_wrap or _is_heading(line, body_size):
            flush()
            if CHAPTER.fullmatch(text.strip()):
                pending_chapter = (text.strip(), page)
                continue
            if pending_chapter:
                text, page = f"{pending_chapter[0]} {text}", pending_chapter[1]
                pending_chapter = None
            elif (prev_heading and prev_heading[0] == page and top - prev_heading[1] < 30
                  and not sections[-1]["passages"] and sections[-1].get("lines", 1) < HEADING_LINES
                  and _continues(sections[-1], line)):
                # A heading that wraps onto a second line.
                sections[-1]["heading"] = _join_heading(sections[-1]["heading"], text, known)
                sections[-1]["lines"] = sections[-1].get("lines", 1) + 1
                prev_heading = (page, top)
                continue
            sections.append({"heading": text, "page": page, "passages": [], "font": _font(line)})
            prev_heading = (page, top)
            last_top = top
            continue
        if pending_chapter:
            # "CHAPTER 2" with no title line after it is a heading on its own.
            sections.append({"heading": pending_chapter[0], "page": pending_chapter[1], "passages": []})
            pending_chapter = None
        # A first-line indent, from this column's own left edge: measured from
        # the page's leftmost text, every line of a right-hand column read as
        # indented and became a paragraph of its own.
        bullet_x = _bullet_text_x(line)
        x = line[0]["x0"]
        if (bullet_x is not None and LIST_NUMBER.fullmatch(line[0]["text"]) and prev_line[0] is not None
                and prev_line[0][:2] == (page, column)
                and prev_line[0][3] >= column_right - RAN_ON * (column_right - column_left)
                and not re.search(r"[.:;!?]$", prev_line[0][4])):
            bullet_x = None   # "34." ending a page range the line before ran on into
        # A list item's later lines hang at its text, not at the indent.
        hanging = hang[0] is not None and abs(x - hang[0]) <= 3
        # A first-line indent is local: a line starting further right than
        # the line before it in the same column. A paper may set headings
        # and body at different margins, and a page of bullets has its own,
        # so no one left edge per column works. A column's first line is
        # measured from that column's commonest start instead, so a sentence
        # running on from the column or page before isn't cut.
        same_column = prev_line[0] is not None and prev_line[0][:2] == (page, column)
        if same_column:
            # ...unless the line before ran to the column's right edge: then
            # this one carries the same paragraph on, at a hanging indent, as
            # every line of a reference after its first does.
            ran_on = prev_line[0][3] >= column_right - RAN_ON * (column_right - column_left)
            indented = x > prev_line[0][2] + INDENT and not hanging and not ran_on
            # Back out past the paragraph's own body, to where it began or
            # beyond: a list, a block quote or a reference entry ended. A step
            # back that stops short of where the paragraph began is a second
            # indent inside it, as some reference entries have.
            outdented = (body_x[0] is not None and body_x[0][:2] == (page, column)
                         and x < body_x[0][2] - INDENT
                         and x <= _began_at(first_x[0], body_x[0], page, column) + 3)
            # A line that stopped short on a full stop or a web address ended
            # its paragraph, whatever the next line's position: two reference
            # entries set at the same margin, one line each. A sentence can't
            # be cut here, since it already ended.
            ended = (not ran_on and _ends_entry(prev_line[0][4])
                     and not _continues_text(line[0]["text"]))
            outdented = outdented or ended
        else:
            # Against the lower of the column's commonest start and the body
            # margin the text was just using: a page whose commonest start is
            # an indent would otherwise glue its first paragraph to the last.
            # That margin counts only if it lies in this column: a left
            # column's margin says nothing about the right column's lines.
            near = (last_body[0] is not None
                    and column_left - 4 * INDENT <= last_body[0][0] <= column_right)
            edge = min(column_left, last_body[0][0]) if near else column_left
            indented = x > edge + INDENT and not hanging
            # A hanging paragraph (a reference entry: first line out, the rest
            # in) carried into a new column: a line there at the column's
            # leftmost text, not at the indent, is the next entry.
            hang_by = first_x[0][3] if first_x[0] is not None and first_x[0][3] is not None else 0
            outdented = bool(para) and hang_by < -INDENT and x < column_min - hang_by - INDENT / 2
            # A paragraph that stopped short on a full stop at the foot of the
            # last column ended there, as a single-line entry does.
            if prev_line[0] is not None and para:
                prev_right = prev_line[0][5]
                prev_short = prev_line[0][3] < prev_right - RAN_ON * (prev_right - prev_line[0][6])
                outdented = outdented or (prev_short and _ends_entry(prev_line[0][4])
                                          and not _continues_text(line[0]["text"]))
        # A line opening on a lower-case word or a web address carries on
        # what came before, however far in it starts.
        if _continues_text(line[0]["text"]):
            indented = False
        indented = indented or outdented
        gap = bool(para) and last_top is not None and page == para[-1][1] and top - last_top > line_gap * 1.6
        size = _size(line)
        resized = bool(para) and para_size[0] is not None and abs(size - para_size[0]) > SIZE_BREAK
        if para and (bullet_x is not None or indented or gap or resized):
            flush()
        if not para:
            para_size[0] = size
            hang[0] = bullet_x   # each list item is its own passage
            first_x[0] = (page, column, x, None)   # where the paragraph began
            body_x[0] = None
        elif body_x[0] is None or body_x[0][:2] != (page, column):
            # The paragraph's second line, or its first in a new column or
            # page, sets its body margin there.
            if body_x[0] is None and first_x[0] is not None and first_x[0][:2] == (page, column):
                # How far its first line sat from its body: -24 pt for a
                # hanging indent. Carried to other columns, where the first
                # line's own position means nothing.
                first_x[0] = first_x[0][:3] + (first_x[0][2] - x,)
            body_x[0] = (page, column, x)
            last_body[0] = (x, x - column_left)   # the margin, and its offset in its column
        para.extend((w["text"], page, w) for w in line)
        para.append(("\n", page, None))
        prev_line[0] = (page, column, x, line[-1]["x1"], line[-1]["text"], column_right, column_left)
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
    reasons = _unreliable(out)
    if reasons:
        # Fail safe: a paper whose sections can't be trusted is stored as one
        # section, every sentence still carrying its page, so a comparison or
        # a Thread's quote never rests on a heading that was guessed wrong.
        passages = [p for s in out for p in s["passages"]]
        digest = hashlib.sha256("\n".join(norm(p["text"]) for p in passages).encode()).hexdigest()
        out = [{"key": DOCUMENT_KEY, "heading": "", "page": out[0]["page"],
                "text_hash": digest, "passages": passages}]
        warnings.append({"code": "sections_unreliable", "reasons": reasons})
    for s in out:
        last = max((p["page"] for p in s["passages"]), default=s["page"])
        if last - s["page"] + 1 > LONG_SECTION_PAGES:
            warnings.append({"code": "long_section", "section": s["key"], "pages": last - s["page"] + 1})
    blank = [p["number"] for p in pages if not p["has_words"]]
    if blank:
        warnings.append({"code": "pages_without_text", "pages": blank[:50]})
    return out, warnings


def _unreliable(sections) -> list:
    """Why these sections can't be trusted, or nothing. Each reason is a shape
    no paper's real headings take: none at all, about as many headings as
    sentences (capitals in a table read as headings), one heading over and
    over (a running head the reader missed), or headings over mostly nothing."""
    headed = [s for s in sections if s["key"] != FRONT_MATTER_KEY]
    passages = sum(len(s["passages"]) for s in sections)
    reasons = []
    if not headed:
        reasons.append("no_headings")
        return reasons
    if len(headed) > 10 and len(headed) * 3 > passages:
        reasons.append("too_many_headings")
    if sum(1 for s in headed if "#" in s["key"]) > max(3, len(headed) // 5):
        reasons.append("repeated_headings")
    if len(headed) > 4 and sum(1 for s in headed if not s["passages"]) * 2 > len(headed):
        reasons.append("mostly_empty_sections")
    return reasons


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
            if _keeps_hyphen(head, tail, known):
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
        if LIST_NUMBER.fullmatch(before.strip()):
            return False   # "1." opening a list item ends no sentence
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
