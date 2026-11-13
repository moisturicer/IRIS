"""Crop every hi_res Formula box from the PDF at 300 dpi."""
import json, sys
from pathlib import Path
import pypdfium2 as pdfium
result, pdf_path, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
els = json.load(open(result, encoding="utf-8"))["elements"]
pdf = pdfium.PdfDocument(pdf_path)
scale, pad = 300 / 72, 4
index = []
for i, e in enumerate(x for x in els if x["type"] == "Formula"):
    md = e["metadata"]; c = md["coordinates"]; page = pdf[md["page_number"] - 1]
    w, h = page.get_size()
    sx, sy = w / c["layout_width"], h / c["layout_height"]
    xs = [p[0] * sx for p in c["points"]]; ys = [p[1] * sy for p in c["points"]]
    box = (max(min(xs) - pad, 0), max(min(ys) - pad, 0), min(max(xs) + pad, w), min(max(ys) + pad, h))
    img = page.render(scale=scale, crop=(box[0], h - box[3], w - box[2], box[1])).to_pil()
    name = f"f{i:02d}_p{md['page_number']}.png"; img.save(out / name)
    index.append({"file": name, "page": md["page_number"], "box_pt": [round(v, 1) for v in box], "ocr_text": e["text"]})
json.dump(index, open(out / "index.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print(len(index), "crops")
