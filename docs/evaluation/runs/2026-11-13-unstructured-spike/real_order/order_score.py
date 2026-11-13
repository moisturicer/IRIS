"""Score extractor reading order on two-column PDFs against pdfplumber's word positions."""
import json, re, sys, unicodedata
from pathlib import Path
import pdfplumber

def chars(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    return "".join(re.findall(r"[a-z0-9]", s))

def columns(pdf_path):
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for p in pdf.pages:
            mid = p.width / 2
            left = p.filter(lambda o: o.get("object_type") != "char" or o["x1"] <= mid + 1)
            right = p.filter(lambda o: o.get("object_type") != "char" or o["x0"] >= mid - 1)
            lines = {}
            for c in p.chars:
                if c["text"].strip(): lines.setdefault(round(c["top"]), []).append(c)
            cross = sum(1 for l in lines.values() if min(c["x0"] for c in l) < mid - 20
                        and max(c["x1"] for c in l) > mid + 20
                        and any(abs((c["x0"] + c["x1"]) / 2 - mid) < 4 for c in l))
            two_col = len(lines) > 20 and cross / len(lines) < 0.05
            pages.append({"L": chars(left.extract_text()), "R": chars(right.extract_text()), "two_col": two_col})
    return pages

def locate(key, pages):
    hits = [(i, s, sides[s].find(key) / max(len(sides[s]), 1)) for i, sides in enumerate(pages)
            for s in ("L", "R") if key in sides[s]]
    return hits[0] if len(hits) == 1 else None

def place(text, pages, from_end=False, n=40, step=10, tries=15):
    for k in range(tries):
        a = len(text) - n - k * step if from_end else k * step
        w = text[a:a + n]
        if a < 0 or len(w) < n: return None
        hit = locate(w, pages)
        if hit: return hit
    return None

def score(texts, pdf_path):
    pages = columns(pdf_path)
    seq, merges, matched = [], 0, 0
    for t in texts:
        tk = chars(t)
        if len(tk) < 100: continue
        a = place(tk, pages); b = place(tk, pages, from_end=True)
        if not a or not pages[a[0]]["two_col"]: continue
        matched += 1
        # A paragraph may flow from the foot of the left column to the head of the right.
        flows_on = a[1] == "L" and b and b[1] == "R" and (a[2] > 0.6 or b[2] < 0.4)
        if b and b[0] == a[0] and b[1] != a[1] and not flows_on: merges += 1
        seq.append(a[:2])
    inversions = 0
    for (p0, s0), (p1, s1) in zip(seq, seq[1:]):
        if p0 == p1 and s0 == "R" and s1 == "L": inversions += 1
    return {"two_column_pages": sum(p["two_col"] for p in pages), "blocks_scored": matched, "inversions": inversions, "merged_across_columns": merges}

def texts_from(kind, path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if kind == "unstructured":
        return [e.get("text") or "" for e in (d["elements"] if isinstance(d, dict) else d)]
    if kind == "llamaparse":
        return [it.get("value") or it.get("md") or "" for p in d["items"]["pages"] for it in p["items"] if it.get("type") not in ("table", "image")]
    if kind == "docling":
        doc = d["document"]["json_content"]
        out = []
        def walk(ref):
            kind_, idx = ref["$ref"].split("/")[1:3]
            node = doc[kind_][int(idx)]
            if kind_ == "texts": out.append(node.get("text") or "")
            for c in node.get("children", []): walk(c)
        for c in doc["body"]["children"]: walk(c)
        return out
    raise ValueError(kind)

if __name__ == "__main__":
    kind, result, pdf = sys.argv[1:4]
    print(json.dumps(score(texts_from(kind, result), pdf)))
