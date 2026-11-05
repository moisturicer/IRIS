"""PROTOTYPE, throwaway. Reads a PDF's text with pdfplumber and compares two Versions.

No AI and no network: pdfplumber reads the words and their positions, and
everything after that is rules. It follows ADR-058 §3: sections by heading, then
sentence by sentence, with each passage's page and regions in both Versions, and
text normalised only for matching.
"""
import difflib
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

import pdfplumber

SENTENCE_END = re.compile(r'(?<=[.!?])["”)]?\s+(?=[A-Z(“"])')
ABBREVIATIONS = ("et al.", "e.g.", "i.e.", "Fig.", "No.", "vs.", "Dr.", "Mr.", "Ms.")
NUMBERING = re.compile(r"^(chapter\s+\d+\s+|\d+(\.\d+)*\.?\s+)", re.I)


@dataclass
class Sentence:
    text: str                 # as read, after repairs
    regions: list             # [{page, x0, top, x1, bottom}] one per line, ADR-031 shape
    kind: str = "sentence"    # or "row" for a table row

    @property
    def page(self):
        return self.regions[0]["page"]

    @property
    def key(self):
        return norm(self.text)


@dataclass
class Section:
    heading: str
    page: int
    sentences: list = field(default_factory=list)

    @property
    def key(self):
        return NUMBERING.sub("", norm(self.heading).lower()).strip() or "front matter"


@dataclass
class Reading:
    sections: list
    dropped: list          # running heads and page numbers removed, as (page, text)
    repairs: list          # hyphen joins, as (page, before, after)
    columns: dict          # page -> number of columns found


def norm(text):
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------- reading
def _lines(words):
    lines = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if lines and abs(lines[-1][0]["top"] - w["top"]) < 2.5:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(l, key=lambda w: w["x0"]) for l in lines]


def _columns(words, page):
    """Split a page into columns at a vertical gutter no body word crosses."""
    body = [w for w in words if 60 < w["top"] < page.height - 60]
    if len(body) < 20:
        return [words]
    lo, hi = int(page.width * 0.3), int(page.width * 0.7)
    for x in range(lo, hi):
        if all(not (w["x0"] - 2 < x < w["x1"] + 2) for w in body):
            left = [w for w in body if w["x1"] <= x]
            right = [w for w in body if w["x0"] >= x]
            if len(left) > 10 and len(right) > 10:
                return [[w for w in words if w["x1"] <= x or not (60 < w["top"] < page.height - 60)],
                        [w for w in words if w["x0"] >= x and 60 < w["top"] < page.height - 60]]
    return [words]


def read(path):
    pages = []
    with pdfplumber.open(path) as pdf:
        for p in pdf.pages:
            # x_tolerance below a space's width: the default (3pt) equals a 12pt Times space
            # and joins the words of any line that isn't justified.
            words = p.extract_words(extra_attrs=["fontname", "size"], keep_blank_chars=False, x_tolerance=1.5)
            tables = p.find_tables()
            boxes = [t.bbox for t in tables]
            inside = lambda w: any(b[0] <= w["x0"] and w["x1"] <= b[2] and b[1] <= w["top"] and w["bottom"] <= b[3]
                                   for b in boxes)
            rows = [(t.bbox[1], [" | ".join(c or "" for c in r) for r in t.extract()]) for t in tables]
            cols = _columns([w for w in words if not inside(w)], p)
            pages.append((p.page_number, p.height, cols, rows))

    # Running heads and page numbers: lines in the top or bottom margin that repeat
    # on most pages once digits are ignored, or a bare number in the bottom margin.
    margin_text = Counter()
    for num, height, cols, _ in pages:
        for col in cols:
            for line in _lines(col):
                if line[0]["top"] < 60 or line[0]["top"] > height - 60:
                    margin_text[re.sub(r"\d+", "#", " ".join(w["text"] for w in line))] += 1
    repeated = {t for t, n in margin_text.items() if n >= max(2, len(pages) // 2)}

    stream, dropped = [], []   # stream of ("line", page, words) | ("row", page, text, top)
    columns = {}
    for num, height, cols, rows in pages:
        columns[num] = len(cols)
        row_items = [("row", num, text, top) for top, texts in rows for text in texts]
        for ci, col in enumerate(cols):
            items = []
            for line in _lines(col):
                text = " ".join(w["text"] for w in line)
                in_margin = line[0]["top"] < 60 or line[0]["top"] > height - 60
                if in_margin and (re.sub(r"\d+", "#", text) in repeated or text.strip().isdigit()):
                    dropped.append((num, text))
                    continue
                items.append(("line", num, line, line[0]["top"]))
            if ci == 0:
                items += row_items
            stream += sorted(items, key=lambda it: it[3])

    body_x = Counter(round(it[2][0]["x0"]) for it in stream if it[0] == "line")
    left_margins = sorted(x for x, n in body_x.items() if n >= 3)
    return _structure(stream, dropped, left_margins, columns)


def _is_heading(line):
    text = " ".join(w["text"] for w in line)
    return all("Bold" in w["fontname"] for w in line) and len(text) < 100 and not text.endswith(".")


def _structure(stream, dropped, left_margins, columns):
    sections = [Section("Front matter", 1)]
    para = []          # [(word text, page, word)] for the paragraph being built
    repairs, last_top, pending_chapter, prev_heading = [], None, None, None
    # Every whole word on any page, to decide whether a line-end hyphen is real.
    # The usual distance between body lines, so a blank line can be told from spacing.
    tops = [it[3] for it in stream if it[0] == "line"]
    line_gap = Counter(round(b - a) for a, b in zip(tops, tops[1:]) if 0 < b - a < 40).most_common(1)[0][0]
    known = {re.sub(r"[^\w-]", "", w["text"]).lower() for it in stream if it[0] == "line" for w in it[2]}

    def margin_of(x):
        return max([m for m in left_margins if m <= x + 1] or [x])

    def flush():
        if para:
            sections[-1].sentences.extend(_sentences(para, repairs, known))
            para.clear()

    for it in stream:
        if it[0] == "row":
            flush()
            sections[-1].sentences.append(Sentence(norm(it[2]), [{"page": it[1], "x0": 0, "top": it[3], "x1": 0, "bottom": it[3]}], "row"))
            continue
        _, page, line, top = it
        text = " ".join(w["text"] for w in line)
        if _is_heading(line):
            flush()
            if re.fullmatch(r"CHAPTER \d+", text):
                pending_chapter = (text, page)
                continue
            if pending_chapter:
                text, page = f"{pending_chapter[0]} {text}", pending_chapter[1]
                pending_chapter = None
            elif prev_heading and prev_heading[0] == page and top - prev_heading[1] < 30 and not sections[-1].sentences:
                sections[-1].heading += " " + text       # a heading that wraps onto a second line
                prev_heading = (page, top)
                continue
            sections.append(Section(text, page))
            prev_heading = (page, top)
            last_top = top
            continue
        indented = line[0]["x0"] > margin_of(line[0]["x0"]) + 20 or (
            line[0]["x0"] - min(left_margins or [line[0]["x0"]]) > 20)
        gap = last_top is not None and page == para[-1][1] and top - last_top > line_gap * 1.6 if para else False
        if para and (indented or gap):
            flush()
        para.extend((w["text"], page, w) for w in line)
        para.append(("\n", page, None))
        last_top = top
    flush()
    return Reading([s for s in sections if s.sentences or s.heading != "Front matter"], dropped, repairs, columns)


def _sentences(para, repairs, known):
    # Join lines; repair a word hyphenated across a line break.
    tokens = []   # (text, word-or-None)
    items = [p for p in para]
    i = 0
    while i < len(items):
        t, page, w = items[i]
        if t == "\n":
            i += 1
            continue
        nxt = items[i + 2] if i + 2 < len(items) and items[i + 1][0] == "\n" else None
        if t.endswith("-") and nxt and nxt[0][:1].isalpha():
            head, tail = t[:-1], nxt[0]
            compound = re.sub(r"[^\w-]", "", head + "-" + tail).lower()
            if "-" in head or tail[:1].isupper() or compound in known:
                joined = head + "-" + tail       # a compound broken at its own hyphen
            else:
                joined = head + tail             # a word Word hyphenated to fit the line
            repairs.append((page, f"{t} / {tail}", joined))
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

    out, start = [], 0
    cuts = [m.end() for m in SENTENCE_END.finditer(text)
            if not any(text[:m.start() + 1].endswith(a) for a in ABBREVIATIONS)] + [len(text)]
    for end in cuts:
        chunk = text[start:end].strip()
        if chunk:
            ws = [w for s, e, wl in spans if s < end and e > start for w in wl if w]
            out.append(Sentence(chunk, _regions(ws)))
        start = end
    return out


def _regions(words):
    lines = {}
    for w in words:
        key = (w["page_number"], round(w["top"]))
        r = lines.setdefault(key, {"page": w["page_number"], "x0": w["x0"], "top": w["top"], "x1": w["x1"], "bottom": w["bottom"]})
        r["x0"], r["x1"] = min(r["x0"], w["x0"]), max(r["x1"], w["x1"])
    return [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in r.items()} for r in lines.values()]


# pdfplumber words carry no page number; add it.
_extract = pdfplumber.page.Page.extract_words


def _with_page(self, *a, **k):
    ws = _extract(self, *a, **k)
    for w in ws:
        w["page_number"] = self.page_number
    return ws


pdfplumber.page.Page.extract_words = _with_page


# ---------------------------------------------------------------- comparing
def compare(a: Reading, b: Reading):
    a_by, b_by = {s.key: s for s in a.sections}, {s.key: s for s in b.sections}
    pairs = [(s, b_by[s.key], None) for s in a.sections if s.key in b_by]
    gone = [s for s in a.sections if s.key not in b_by]
    new = [s for s in b.sections if s.key not in a_by]

    # A renamed section: unmatched on both sides, but mostly the same sentences.
    for s in list(gone):
        best = max(new, key=lambda t: _overlap(s, t), default=None)
        if best and _overlap(s, best) >= 0.5:
            pairs.append((s, best, "renamed"))
            gone.remove(s); new.remove(best)

    # Moved: matched sections that fall out of the longest common order.
    pairs.sort(key=lambda p: a.sections.index(p[0]))
    b_index = [b.sections.index(p[1]) for p in pairs]
    keep = _lis(b_index)

    results = []
    for n, (sa, sb, note) in enumerate(pairs):
        changes = _diff(sa.sentences, sb.sentences)
        status = "changed" if any(c["op"] != "unchanged" for c in changes) else "unchanged"
        flags = [f for f in (note, "moved" if n not in keep else None) if f]
        results.append({"a": sa, "b": sb, "status": status, "flags": flags, "changes": changes})
    for s in gone:
        results.append({"a": s, "b": None, "status": "removed", "flags": [], "changes": []})
    for s in new:
        results.append({"a": None, "b": s, "status": "added", "flags": [], "changes": [
            {"op": "added", "b": x} for x in s.sentences]})

    # Sentences removed in one section and added in another moved.
    removed = {c["a"].key: c for r in results for c in r["changes"] if c["op"] == "removed"}
    for r in results:
        for c in r["changes"]:
            if c["op"] == "added" and c["b"].key in removed:
                c["op"] = "moved here"; removed[c["b"].key]["op"] = "moved away"
    results.sort(key=lambda r: (r["b"] and b.sections.index(r["b"])) if r["b"] else
                 (a.sections.index(r["a"]) - 0.5))
    return results


def _overlap(s, t):
    return difflib.SequenceMatcher(None, [x.key for x in s.sentences], [x.key for x in t.sentences]).ratio()


def _lis(seq):
    """Indices of a longest increasing subsequence."""
    n = len(seq)
    length, prev = [1] * n, [-1] * n
    for i in range(n):
        for j in range(i):
            if seq[j] < seq[i] and length[j] + 1 > length[i]:
                length[i], prev[i] = length[j] + 1, j
    if not n:
        return set()
    i = max(range(n), key=lambda k: length[k])
    out = set()
    while i != -1:
        out.add(i); i = prev[i]
    return out


def _diff(xs, ys):
    sm = difflib.SequenceMatcher(None, [x.key for x in xs], [y.key for y in ys], autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            out += [{"op": "unchanged", "a": x, "b": y} for x, y in zip(xs[i1:i2], ys[j1:j2])]
            continue
        left, right = list(xs[i1:i2]), list(ys[j1:j2])
        for x in list(left):
            best = max(right, key=lambda y: _ratio(x, y), default=None)
            if best is not None and _ratio(x, best) >= 0.6:
                out.append({"op": "changed", "a": x, "b": best, "words": _word_diff(x.text, best.text)})
                left.remove(x); right.remove(best)
        out += [{"op": "removed", "a": x} for x in left]
        out += [{"op": "added", "b": y} for y in right]
    return out


def _ratio(x, y):
    return difflib.SequenceMatcher(None, x.key, y.key).ratio()


def _word_diff(a, b):
    wa, wb = a.split(), b.split()
    parts = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, wa, wb).get_opcodes():
        if op == "equal":
            parts.append(("same", " ".join(wa[i1:i2])))
        else:
            if i2 > i1: parts.append(("del", " ".join(wa[i1:i2])))
            if j2 > j1: parts.append(("ins", " ".join(wb[j1:j2])))
    return parts


# ---------------------------------------------------------------- threads
def find_quote(reading: Reading, quote: str):
    """Where a v1 thread's quote is in another Version, or None (Outdated)."""
    q = norm(re.sub(r"(\w)-\s*\n\s*(?=[a-z])", r"\1", quote).replace("\n", " "))
    for s in reading.sections:
        for x in s.sentences:
            if q in x.text:
                return x
    return None


def nearest(reading: Reading, quote: str):
    """The sentence holding most of the quote, scored against the quote, not the sentence."""
    q = norm(quote.replace("-\n", "").replace("\n", " "))

    def covered(x):
        sm = difflib.SequenceMatcher(None, q, x.text, autojunk=False)
        return sum(m.size for m in sm.get_matching_blocks()) / len(q)
    return max((x for s in reading.sections for x in s.sentences), key=covered)
