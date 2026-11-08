"""PROTOTYPE, throwaway, never merge. The measures every reading is scored on.

Each returns counts only, never paper text, so out/scores.json can be shared.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

from tei_reader import reader

YEAR = re.compile(r"\((\d{4}[a-z]?|n\.d\.)[^)]*\)")
IEEE = re.compile(r"\[\d{1,3}\]")
TOKEN = re.compile(r"[a-z0-9]{3,}")
BAND = 0.06   # words this close to the top or bottom edge are running heads or page numbers


def collapsed(r) -> bool:
    return len(r["sections"]) <= 1 or any(w["code"] == "sections_unreliable" for w in r["warnings"])


def _heading_form(text) -> str:
    text = reader.norm(text or "").lower()
    text = reader.NUMBERING.sub("", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def bookmarks(pdf_path) -> list[str]:
    """The PDF's bookmark titles, the answer key for headings, or []."""
    import pdfplumber

    try:
        with pdfplumber.open(pdf_path) as pdf:
            titles = [o[1] for o in pdf.doc.get_outlines()]
    except Exception:
        return []
    return sorted({_heading_form(t) for t in titles if t and _heading_form(t)})


def headings(r, key) -> dict:
    """Precision and recall of the reading's headings against the bookmarks."""
    if not key:
        return {}
    found = {_heading_form(s["heading"]) for s in r["sections"] if s["heading"]}
    found.discard("")
    keyset = set(key)
    hit = found & keyset
    return {"bookmarks": len(keyset), "headings": len(found), "matched": len(hit),
            "precision": round(len(hit) / len(found), 3) if found else None,
            "recall": round(len(hit) / len(keyset), 3)}


def reference_entries(r) -> dict:
    texts = [p["text"] for s in r["sections"] if reader._is_references(s["heading"]) for p in s["passages"]]
    if not texts:
        return {"entries": 0}
    ieee = sum(bool(IEEE.match(t)) for t in texts) > len(texts) / 2
    off = [t for t in texts if not IEEE.match(t)] if ieee else [t for t in texts if len(YEAR.findall(t)) != 1]
    return {"entries": len(texts), "style": "ieee" if ieee else "apa", "off_pattern": len(off),
            "over_120_words": sum(1 for t in texts if len(t.split()) > 120)}


def _tokens(text) -> list[str]:
    return TOKEN.findall(unicodedata.normalize("NFKC", text).lower())


def pdf_words(pdf_path) -> Counter:
    """pdfplumber's body words: every word not hard against the top or bottom
    edge, a word broken by a line-end hyphen left out (it is joined in output)."""
    import pdfplumber

    counts = Counter()
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            h = float(page.height)
            for w in page.extract_words():
                if w["top"] < BAND * h or w["bottom"] > (1 - BAND) * h or w["text"].endswith("-"):
                    continue
                counts.update(_tokens(w["text"]))
    return counts


def coverage(r, body: Counter) -> float | None:
    out = Counter()
    for s in r["sections"]:
        out.update(_tokens(s["heading"] or ""))
        for p in s["passages"]:
            out.update(_tokens(p["text"]))
    total = sum(body.values())
    if not total:
        return None
    return round(sum(min(n, out[t]) for t, n in body.items()) / total, 4)


def _base_key(key) -> str:
    return key.split("#")[0].replace("-", " ").strip()


def version_pair(a, b, edited) -> dict:
    """Sections that changed between two Versions, against the edits made."""
    h1 = {s["key"]: s["text_hash"] for s in a["sections"]}
    h2 = {s["key"]: s["text_hash"] for s in b["sections"]}
    changed = {_base_key(k) for k in set(h1) | set(h2) if h1.get(k) != h2.get(k)}
    edited = set(edited)
    return {"changed": len(changed), "true_changes": len(changed & edited),
            "false_changes": len(changed - edited), "missed_edits": len(edited - changed),
            "collapsed": collapsed(a) or collapsed(b)}
