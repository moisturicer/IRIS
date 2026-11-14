"""Shaping rules that read IRIS's own PDF evidence (IR-1057, ADR-067 decisions 5-7).

Pure: the evidence is the stored output of ``apps.documents.pdf_evidence.reader``.
"""

import re
import unicodedata
from dataclasses import replace
from typing import Mapping, Optional

from apps.ai.chunking.document import BoundingBox
from apps.ai.extraction.numbering import outline_depths
from apps.ai.extraction.shaping import FRONT_MATTER

SECTION_LEVEL = 2
# Decision 7, signal 5: top-level whatever their numbering or font.
KNOWN_TOP = re.compile(
    r"^(chapter\s+\S+|introduction|acknowledge?ments?|references|bibliography|appendix|appendices)\b",
    re.IGNORECASE,
)
# A leading section number, "Chapter N" or "Appendix X", dropped to match a
# bookmark or contents entry that omits it.
_NUMBER_PREFIX = re.compile(r"^((chapter|appendix)\s+\S+|\d+(\.\d+)*\.?|[A-Z]\.|[IVXLC]+\.)\s+", re.IGNORECASE)
_CONTENTS_NUMBER = re.compile(r"^\d+(\.\d+)*$")
# A printed page number alone: "12", "- 12 -", "Page 12", "Page 12 of 40", "xii".
_PRINTED = re.compile(
    r"^[-–—\s]*(?:page\s+)?(\d{1,4}|[ivxlcdm]{1,7})(?:\s+of\s+\d+)?[-–—\s]*$", re.IGNORECASE,
)
# Contents entries indented within this many points share a depth.
_INDENT_STEP = 4.0
# A word belongs to an element when its centre lies this close to the box.
_BOX_TOLERANCE = 3.0


def usable(evidence: Optional[Mapping]) -> Optional[Mapping]:
    """Evidence the reader produced without an error, else nothing."""
    return evidence if evidence and not evidence.get("error") else None


def key(text: str) -> str:
    """Letters and digits only, case-folded; ligatures and spacing do not count."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", text).casefold() if ch.isalnum())


def _keys(text: str) -> set[str]:
    stripped = _NUMBER_PREFIX.sub("", text.strip())
    return {k for k in (key(text), key(stripped)) if k}


# ---------------------------------------------------------------- headings
def place_headings(elements: list, evidence: Optional[Mapping], parents: Mapping[str, str]) -> list:
    """Every heading's level and the signal that decided it, first answer wins."""
    evidence = usable(evidence) or {}
    indexes = [i for i, e in enumerate(elements) if e.kind == "heading"]
    heads = [elements[i] for i in indexes]
    static = [
        ("bookmark", _bookmark_depths(heads, evidence.get("bookmarks") or [])),
        ("contents", _contents_depths(heads, evidence.get("contents") or [])),
        ("numbering", outline_depths([h.text for h in heads])),
    ]
    title = _title(heads, static)
    fonts = _font_depths(heads, evidence, title)
    depths: dict[str, int] = {}
    anchor = 0
    for position, (index, head) in enumerate(zip(indexes, heads)):
        if position == title:
            depth, source = 0, "title"
        else:
            depth, source = _decide(position, head, static, fonts, parents, depths, anchor)
        if source != "open_section":
            anchor = depth
        if head.element_id:
            depths[head.element_id] = depth
        elements[index] = replace(head, level=1 if depth == 0 else SECTION_LEVEL + depth - 1,
                                  level_source=source)
    return elements


def _decide(position, head, static, fonts, parents, depths, anchor):
    for source, answers in (*static, ("font", fonts)):
        if answers[position] is not None:
            return answers[position], source
    parent = parents.get(head.element_id)
    if parent in depths:
        return depths[parent] + 1, "parent_id"
    if KNOWN_TOP.match(head.text.strip()):
        return 1, "known_heading"
    return anchor + 1, "open_section"


def _title(heads, static) -> Optional[int]:
    """The first heading is the paper's title when nothing places it as a
    section and it is on page 1: the IR-859 rule, kept at level 1."""
    if not heads or heads[0].page != 1 or any(answers[0] is not None for _, answers in static):
        return None
    text = heads[0].text.strip()
    return None if FRONT_MATTER.match(text) or KNOWN_TOP.match(text) else 0


def _matched(heads, entries, entry_keys, entry_page):
    """Each heading's entry by text, preferring one on the heading's page;
    each entry is used once, so a repeated "Introduction" finds its own."""
    used: set[int] = set()
    found = []
    for head in heads:
        wanted = _keys(head.text)
        candidates = [i for i, e in enumerate(entries) if i not in used and entry_keys(e) & wanted]
        same_page = [i for i in candidates if entry_page(entries[i]) == head.page]
        choice = (same_page or candidates or [None])[0]
        if choice is not None:
            used.add(choice)
        found.append(choice)
    return found


def _bookmark_depths(heads, bookmarks):
    marks = [b for b in bookmarks if b.get("title")]
    found = _matched(heads, marks, lambda b: _keys(b["title"]), lambda b: b.get("page"))
    return [None if i is None else int(marks[i]["level"]) for i in found]


def _contents_depths(heads, contents):
    indents = sorted({round(float(e.get("indent") or 0) / _INDENT_STEP) for e in contents})

    def depth(entry):
        number = (entry.get("number") or "").strip()
        if _CONTENTS_NUMBER.match(number):
            return number.count(".") + 1
        if number:
            return 1  # "Chapter 3", "Appendix A"
        return indents.index(round(float(entry.get("indent") or 0) / _INDENT_STEP)) + 1

    found = _matched(
        heads, contents,
        lambda e: _keys(e.get("title") or "") | _keys(f"{e.get('number') or ''} {e.get('title') or ''}"),
        lambda e: None,
    )
    return [None if i is None else depth(contents[i]) for i in found]


def _font_depths(heads, evidence, title):
    """Larger, then bold, is shallower. Answers only when the headings use at
    least two styles: one style alone says nothing about depth."""
    pages = {p["page"]: p for p in evidence.get("pages") or []}
    styles = [None if i == title else _style(h, pages.get(h.page)) for i, h in enumerate(heads)]
    ranked = sorted({s for s in styles if s}, key=lambda s: (-s[0], not s[1]))
    if len(ranked) < 2:
        return [None] * len(heads)
    return [None if s is None else ranked.index(s) + 1 for s in styles]


def _style(head, page):
    if not page or not page.get("lines"):
        return None
    wanted = key(head.text)
    for line in page["lines"]:
        text = key(" ".join(word[0] for word in line["words"]))
        if text and (text == wanted or (wanted.startswith(text) and len(text) * 2 >= len(wanted))):
            return (float(line["size"]), bool(line["bold"]))
    return None


# ---------------------------------------------------------------- printed pages
def printed_pages(elements, evidence: Optional[Mapping], pages) -> dict[int, str]:
    """Page labels, then PageNumber and Footer text, then gaps filled from the
    arabic sequence on either side (decision 6)."""
    evidence = usable(evidence) or {}
    printed: dict[int, str] = {}
    labels = evidence.get("page_labels") or []
    for page in pages:
        if 0 < page <= len(labels) and labels[page - 1]:
            printed[page] = str(labels[page - 1])
    for label in ("PageNumber", "Footer"):
        for element in elements:
            if element.source_label == label and element.page not in printed:
                match = _PRINTED.match(element.text.strip())
                if match:
                    printed[element.page] = match.group(1)
    return _fill(printed, sorted(pages))


def _fill(printed, pages):
    anchors = sorted((p, int(v)) for p, v in printed.items() if v.isdigit())
    for (start, first), (end, last) in zip(anchors, anchors[1:]):
        if last - first == end - start:
            for page in pages:
                if start < page < end and page not in printed:
                    printed[page] = str(first + page - start)
    return printed


# ---------------------------------------------------------------- line boxes
MATCHED, FALLBACK, NO_TEXT_LAYER = "matched", "fallback", "no_text_layer"


def line_boxes(text: str, boxes: tuple, evidence: Optional[Mapping]):
    """The element's lines among the stored ``pdfplumber`` words, one box per
    line, and whether that matched. The element box stays on any failure."""
    evidence = usable(evidence)
    if not evidence or not boxes:
        return boxes, None
    pages = {p["page"]: p for p in evidence.get("pages") or []}
    if any(not (pages.get(b.page) or {}).get("has_text_layer") for b in boxes):
        return boxes, NO_TEXT_LAYER
    words = [(box.page, line_number, word)
             for box in boxes
             for line_number, line in enumerate(pages[box.page].get("lines") or [])
             for word in line["words"] if _inside(word, box)]
    wanted = key(text)
    joined, starts = "", []
    for _, _, word in words:
        starts.append(len(joined))
        joined += key(word[0])
    at = joined.find(wanted) if wanted else -1
    if at < 0:
        return boxes, FALLBACK
    chosen = [w for w, start in zip(words, starts)
              if start < at + len(wanted) and start + len(key(w[2][0])) > at]
    lines: dict[tuple[int, int], list] = {}
    for page, line_number, word in chosen:
        lines.setdefault((page, line_number), []).append(word)
    return tuple(
        BoundingBox(page=page, left=min(w[1] for w in ws), top=min(w[2] for w in ws),
                    right=max(w[3] for w in ws), bottom=max(w[4] for w in ws))
        for (page, _), ws in lines.items()
    ), MATCHED


def _inside(word, box):
    x = (word[1] + word[3]) / 2
    y = (word[2] + word[4]) / 2
    return (box.left - _BOX_TOLERANCE <= x <= box.right + _BOX_TOLERANCE
            and box.top - _BOX_TOLERANCE <= y <= box.bottom + _BOX_TOLERANCE)
