"""PROTOTYPE, throwaway, never merge. A review text reader guided by a layout model.

The question: does a small self-hosted layout detector read real papers better
than IR-871's rules, and at what memory and time cost?

PaddlePaddle's PP-DocLayout v2 (Apache-2.0, ONNX, CPU, via rapid-layout) looks
at each page as an image and returns boxes in reading order: header, footer,
page number, paragraph title, text, table, image, caption and so on. Nothing is
generated: pdfplumber still reads every word, and each word goes into the box
its centre falls in. IR-871's own sentence, hyphen and key code (reader.py)
then makes the passages, so the comparison tests only the layout.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reader as R  # noqa: E402  IR-871's reader, for its sentence and key rules

#: Never text a reviewer comments on.
DROP = {"header", "footer", "number", "header_image", "footer_image", "seal", "aside_text"}
HEADINGS = {"paragraph_title", "doc_title"}
#: Words drawn inside a picture or chart (axis labels, diagram text).
PICTURES = {"image", "chart"}
DPI = 120

_model = None


def model():
    global _model
    if _model is None:
        from rapid_layout import ModelType, RapidLayout, RapidLayoutInput

        _model = RapidLayout(cfg=RapidLayoutInput(model_type=ModelType.PP_DOC_LAYOUTV2))
    return _model


def _words(page):
    words = page.extract_words(extra_attrs=["fontname", "size"], keep_blank_chars=False,
                               x_tolerance=R.X_TOLERANCE)
    for w in words:
        w["text"] = R._clean(w["text"])
        w["page"] = page.page_number
    return R._join_small_caps([w for w in words if w["text"].strip()])


def _boxes(page):
    img = page.to_image(resolution=DPI).original.convert("RGB")
    res = model()(np.array(img))
    scale = float(page.width) / img.width
    return [(c, [v * scale for v in b]) for b, c in zip(res.boxes, res.class_names)]


def _inside(w, box, slack=2.0):
    cx, cy = (w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2
    return box[0] - slack <= cx <= box[2] + slack and box[1] - slack <= cy <= box[3] + slack


def read(path) -> dict:
    pages, blocks, unplaced, total = [], [], 0, 0
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = _words(page)
            total += len(words)
            boxes = _boxes(page)
            owner = {}
            for w in words:
                hits = [i for i, (_, b) in enumerate(boxes) if _inside(w, b)]
                if hits:
                    owner[id(w)] = min(hits, key=lambda i: (boxes[i][1][2] - boxes[i][1][0])
                                       * (boxes[i][1][3] - boxes[i][1][1]))
                else:
                    unplaced += 1
            for i, (cls, box) in enumerate(boxes):
                mine = [w for w in words if owner.get(id(w)) == i]
                rows = []
                if cls == "table":
                    table = page.crop([max(0, box[0] - 2), max(0, box[1] - 2),
                                       min(page.width, box[2] + 2), min(page.height, box[3] + 2)]).extract_table()
                    rows = [R._clean(" | ".join((c or "").replace("\n", " ") for c in r)).strip(" |")
                            for r in (table or [])]
                blocks.append((page.page_number, cls, mine, box, [r for r in rows if r]))
            pages.append({"number": page.page_number, "width": float(page.width),
                          "height": float(page.height), "has_words": bool(words)})

    known = Counter(R._word(w["text"]) for _, cls, ws, _, _ in blocks if cls not in DROP for w in ws)
    sections = [{"heading": "", "page": 1, "passages": []}]
    paragraph, carry, dropped = 0, [], 0

    def flush():
        nonlocal paragraph
        if carry:
            paragraph += 1
            sections[-1]["passages"].extend(R._sentences(carry, known, paragraph, pages))
            carry.clear()

    for pno, cls, ws, box, rows in blocks:
        if cls in DROP:
            dropped += len(ws)
            continue
        if cls in PICTURES:
            dropped += len(ws)
            continue
        if cls == "table" and rows:
            flush()
            for text in rows:
                paragraph += 1
                sections[-1]["passages"].append({"text": text, "page": pno, "paragraph": paragraph,
                                                 "kind": "row", "regions": R._normalize([(pno, *box)], pages)})
            continue
        if not ws:
            continue
        lines = R._lines(ws)
        if cls in HEADINGS:
            flush()
            heading = ""
            for line in lines:
                text = R._line_text(line)
                heading = R._join_heading(heading, text, known) if heading else text
            sections.append({"heading": heading, "page": pno, "passages": []})
            continue
        # A paragraph carried on from the last box: it didn't end, and this
        # box opens in lower case (a column or page break mid-sentence).
        first = lines[0][0]["text"]
        prev_text = carry[-2][0] if len(carry) >= 2 else ""
        if not (carry and not re.search(r"[.!?:][\"”’')\]]*$", prev_text)
                and (first[:1].islower() or prev_text.endswith("-"))):
            flush()
        for line in lines:
            carry.extend((w["text"], pno, w) for w in line)
            carry.append(("\n", pno, None))
    flush()
    if not sections[0]["passages"]:
        sections.pop(0)
    if not any(s["passages"] for s in sections):
        out, warnings = [], []
    else:
        out, warnings = R._finish(sections, pages)
    return {"reader": "layout-prototype/pp_doc_layoutv2", "page_count": len(pages),
            "sections": out, "warnings": warnings,
            "stats": {"words": total, "unplaced": unplaced, "dropped": dropped}}
