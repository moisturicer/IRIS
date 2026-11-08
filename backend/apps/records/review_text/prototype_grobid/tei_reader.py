"""PROTOTYPE, throwaway, never merge. GROBID's TEI as the reader's stored shape.

``read(tei_bytes, page_count)`` returns what ``reader.read()`` returns:
``{reader, page_count, sections, warnings}``. Each section is
``{key, heading, page, text_hash, passages}`` and each passage is
``{text, page, paragraph, kind, regions}``, with regions as fractions of the
page (ADR-031), taken from TEI ``coords`` and the ``facsimile`` surface sizes.

Keys, hashes and the fail-safe come from the reader's own ``_finish``, so a
GROBID reading is keyed, hashed and judged exactly as the rules' reading is.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from lxml import etree

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("review_reader", HERE.parent / "reader.py")
reader = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reader)

TEI = "{http://www.tei-c.org/ns/1.0}"
NS = {"t": TEI[1:-1]}


def _text(el) -> str:
    """An element's words, with GROBID's inline references kept as text."""
    return reader._clean(re.sub(r"\s+", " ", "".join(el.itertext())).strip())


class _Doc:
    def __init__(self, root, page_count):
        self.sizes = {}
        for s in root.iterfind(".//t:facsimile/t:surface", NS):
            self.sizes[int(s.get("n"))] = (float(s.get("lrx")), float(s.get("lry")))
        self.page_count = page_count or max(self.sizes, default=1)
        self.paragraph = 0

    def boxes(self, el):
        """(page, x0, top, x1, bottom) in points from ``coords`` on the element
        or, when it has none, on its descendants."""
        found = []
        for e in [el, *el.iterdescendants()]:
            coords = e.get("coords") if isinstance(e.tag, str) else None
            if not coords:
                continue
            for box in coords.split(";"):
                parts = box.split(",")
                if len(parts) < 5:
                    continue
                page, x, y, w, h = int(parts[0]), *map(float, parts[1:5])
                found.append((page, x, y, x + w, y + h))
            if e is el:
                break
        return found

    def regions(self, boxes):
        out = []
        for page, x0, top, x1, bottom in boxes:
            width, height = self.sizes.get(page, (595.0, 842.0))
            clamp = lambda v: min(1.0, max(0.0, v))  # noqa: E731
            left, right = clamp(x0 / width), clamp(x1 / width)
            t, b = clamp(top / height), clamp(bottom / height)
            if right > left and b > t:
                out.append({"page": page, "left": round(left, 4), "top": round(t, 4),
                            "right": round(right, 4), "bottom": round(b, 4)})
        return out

    def passage(self, el, kind="sentence", text=None, fallback_page=1):
        text = text if text is not None else _text(el)
        if not text:
            return None
        boxes = self.boxes(el)
        return {"text": text, "page": boxes[0][0] if boxes else fallback_page,
                "paragraph": self.paragraph, "kind": kind, "regions": self.regions(boxes)}

    def paragraph_passages(self, p, page):
        """One passage per ``<s>``, or the paragraph whole when GROBID gave none."""
        self.paragraph += 1
        sentences = p.findall("t:s", NS)
        out = [self.passage(s, fallback_page=page) for s in sentences] if sentences else [
            self.passage(p, fallback_page=page)]
        return [x for x in out if x]

    def figure_passages(self, fig, page):
        out = []
        caption = " ".join(t for t in (_text(e) for e in fig.findall("t:head", NS) + fig.findall("t:label", NS)) if t)
        desc = fig.find("t:figDesc", NS)
        if desc is not None:
            ss = desc.findall(".//t:s", NS)
            self.paragraph += 1
            if ss:
                out += [self.passage(s, fallback_page=page) for s in ss]
            else:
                out.append(self.passage(desc, text=" ".join(x for x in (caption, _text(desc)) if x),
                                        fallback_page=page))
        for row in fig.iterfind(".//t:table/t:row", NS):
            self.paragraph += 1
            cells = [_text(c) for c in row.findall("t:cell", NS)]
            out.append(self.passage(row, kind="row", text=" | ".join(c for c in cells if c), fallback_page=page))
        return [x for x in out if x]


def _first_page(doc, el, default):
    boxes = doc.boxes(el)
    if boxes:
        return boxes[0][0]
    for e in el.iterdescendants():
        if isinstance(e.tag, str) and e.get("coords"):
            return int(e.get("coords").split(",")[0])
    return default


def sections_from(root, doc):
    """GROBID's divisions, in document order, before keys and hashes."""
    sections = []
    front = {"heading": "", "page": 1, "passages": []}
    header = root.find("t:teiHeader", NS)
    if header is not None:
        title = header.find(".//t:titleStmt/t:title", NS)
        if title is not None:
            doc.paragraph += 1
            p = doc.passage(title)
            if p:
                front["passages"].append(p)
        abstract = header.find(".//t:profileDesc/t:abstract", NS)
    else:
        abstract = None
    sections.append(front)
    if abstract is not None and _text(abstract):
        sec = {"heading": "Abstract", "page": _first_page(doc, abstract, 1), "passages": []}
        for p in abstract.iterfind(".//t:p", NS):
            sec["passages"] += doc.paragraph_passages(p, sec["page"])
        sections.append(sec)

    loose_figures = []
    text = root.find("t:text", NS)
    if text is None:
        return sections
    for part in text:
        if part.tag not in (TEI + "body", TEI + "back"):
            continue
        for child in part:
            if child.tag == TEI + "figure":
                loose_figures.append(child)
                continue
            if child.tag != TEI + "div":
                continue
            if child.get("type") == "references":
                sections.append(_references(child, doc))
                continue
            _division(child, doc, sections, loose_figures)

    # A figure outside every division goes to the section it is printed in,
    # never to the reference list: a caption there would count as an entry
    # (seen on a tuning paper, 2026-11-08).
    for fig in loose_figures:
        page = _first_page(doc, fig, sections[-1]["page"])
        target = sections[0]
        for s in sections:
            if s["page"] <= page and not reader._is_references(s["heading"]):
                target = s
        target["passages"] += doc.figure_passages(fig, page)
    return [s for s in sections if s["passages"] or s["heading"]]


def _division(div, doc, sections, loose_figures):
    head = div.find("t:head", NS)
    if head is not None and _text(head):
        number = (head.get("n") or "").strip()
        heading = f"{number} {_text(head)}".strip() if number else _text(head)
        sections.append({"heading": heading, "page": _first_page(doc, head, sections[-1]["page"]),
                         "passages": []})
    elif div.get("type") in ("acknowledgement", "annex", "availability", "funding"):
        sections.append({"heading": div.get("type").title(), "page": _first_page(doc, div, sections[-1]["page"]),
                         "passages": []})
    current = sections[-1]
    for child in div:
        if child.tag == TEI + "p":
            current["passages"] += doc.paragraph_passages(child, current["page"])
        elif child.tag == TEI + "formula":
            doc.paragraph += 1
            p = doc.passage(child, fallback_page=current["page"])
            if p:
                current["passages"].append(p)
        elif child.tag == TEI + "figure":
            current["passages"] += doc.figure_passages(child, current["page"])
        elif child.tag == TEI + "list":
            for item in child.iterfind("t:item", NS):
                current["passages"] += doc.paragraph_passages(item, current["page"])
        elif child.tag == TEI + "div":
            _division(child, doc, sections, loose_figures)
            current = sections[-1]
        elif child.tag == TEI + "listBibl":
            current["passages"] += reference_passages(child, doc, current["page"])


def reference_passages(listbibl, doc, page):
    """One passage per entry: GROBID's raw citation text, as printed."""
    out = []
    for bib in listbibl.iterfind(".//t:biblStruct", NS):
        raw = bib.find("t:note[@type='raw_reference']", NS)
        text = _text(raw) if raw is not None else _text(bib)
        doc.paragraph += 1
        p = doc.passage(bib, text=text, fallback_page=page)
        if p:
            out.append(p)
    return out


def _references(div, doc):
    head = div.find("t:head", NS)
    heading = _text(head) if head is not None and _text(head) else "References"
    page = _first_page(doc, div, 1)
    passages = []
    for lb in div.iterfind(".//t:listBibl", NS):
        passages += reference_passages(lb, doc, page)
    if passages:
        page = passages[0]["page"]
    return {"heading": heading, "page": page, "passages": passages}


def parse(tei: bytes):
    return etree.fromstring(tei, parser=etree.XMLParser(huge_tree=True, resolve_entities=False, no_network=True))


def references(tei: bytes, page_count=None):
    """The reference entries alone, for the hybrid: (heading, passages) or None."""
    root = parse(tei)
    doc = _Doc(root, page_count)
    for div in root.iterfind(".//t:text/t:back//t:div[@type='references']", NS):
        sec = _references(div, doc)
        if sec["passages"]:
            return sec
    return None


def read(tei: bytes, page_count=None) -> dict:
    root = parse(tei)
    doc = _Doc(root, page_count)
    sections = sections_from(root, doc)
    pages = [{"number": n, "has_words": True} for n in range(1, doc.page_count + 1)]
    out, warnings = reader._finish(sections, pages)
    return {"reader": "grobid-0.9.1-crf/tei-map-1", "page_count": doc.page_count,
            "sections": out, "warnings": warnings}
