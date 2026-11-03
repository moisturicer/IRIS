import json, re, sys
from apps.ai.chunking.document import FORMULA, HEADING
from apps.ai.models import ChunkSet, DocumentChunk
from apps.documents.models import PdfExtraction

LATEX = re.compile(r"\\[A-Za-z]+|[\^_]\{|\$")
NUMBERED = re.compile(r"^((?:\d+|[A-Z])(?:\.\d+)*)\.?\s+\S")
# A word cut at a line end and rejoined with a space: "compu- tation".
BROKEN = re.compile(r"\b[a-z]{2,}- [a-z]{2,}\b")
LEGIT_PREFIX = re.compile(r"\b(?:and|or|to)\b")

out = []
for e in PdfExtraction.objects.select_related("record").order_by("record__title"):
    doc = e.as_normalized_document()
    row = {"title": e.record.title, "extractor": e.extractor, "status": e.status,
           "pages": e.pages_read, "credits": float(e.credits) if e.credits is not None else None,
           "failed_pages": [w["page"] for w in e.warnings if w.get("kind") == "page_failed"]}
    meta = ((e.raw_result or {}).get("metadata") or {}).get("pages") or []
    if meta:
        conf = {p["page_number"]: p.get("confidence") for p in meta}
        row["confidence_min"] = min(c for c in conf.values() if c is not None)
        row["low_confidence_pages"] = sorted(p for p, c in conf.items() if c is not None and c < 0.5)
        row["cost_optimized_pages"] = sorted(p["page_number"] for p in meta if p.get("cost_optimized"))
    els = doc.elements if doc else ()
    formulas = [x.text for x in els if x.kind == FORMULA]
    row["formula_elements"] = len(formulas)
    row["formula_elements_latex"] = sum(1 for f in formulas if LATEX.search(f))
    row["formula_samples"] = formulas[:3]
    inline = [m for x in els if x.kind != FORMULA for m in re.findall(r"\$[^$\n]{1,80}\$", x.text)]
    row["inline_dollar_math"] = len(inline)
    row["inline_samples"] = inline[:3]
    heads = [(x.level, x.text.strip()) for x in els if x.kind == HEADING]
    row["headings"] = len(heads)
    row["heading_outline"] = [(lv, t[:70]) for lv, t in heads]
    cs = ChunkSet.objects.filter(record=e.record, is_active=True).first()
    texts = list(DocumentChunk.objects.filter(chunk_set=cs).values_list("text", flat=True)) if cs else []
    row["chunks"] = len(texts)
    broken = [m.group(0) for t in texts for m in BROKEN.finditer(t)
              if not LEGIT_PREFIX.search(t[m.end():m.end() + 6])]
    row["broken_hyphen_candidates"] = len(broken)
    row["broken_hyphen_samples"] = sorted(set(broken))[:12]
    out.append(row)

json.dump(out, open(sys.argv[1] if len(sys.argv) > 1 else "/ir851/analysis.json", "w", encoding="utf-8"),
          indent=1, ensure_ascii=False)
for r in out:
    print(r["extractor"], r["pages"], r["credits"], "formulas", r["formula_elements"], r["formula_elements_latex"],
          "inline$", r["inline_dollar_math"], "heads", r["headings"],
          "broken", r["broken_hyphen_candidates"], "lowconf", r.get("low_confidence_pages"), "|", r["title"][:40])
