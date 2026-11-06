"""Audit source PDF lengths and labelled-page positions without reading model output."""

import argparse
import hashlib
import json
import re
from pathlib import Path

import fitz


HERE = Path(__file__).parent


def tokens(value):
    return re.findall(r"[a-z0-9]+", value.lower())


def normalized(value):
    return " ".join(tokens(value))


def audit(sources, directory):
    by_title = {source["title"]: source for source in sources}
    title_tokens = {title: set(tokens(title)) for title in by_title}
    matches = {title: [] for title in by_title}
    for path in directory.glob("*.pdf"):
        try:
            with fitz.open(path) as pdf:
                if not pdf.page_count:
                    continue
                first_page = set(tokens(pdf[0].get_text()[:7000]))
                for title, expected in title_tokens.items():
                    if expected and expected <= first_page:
                        matches[title].append(path)
        except (fitz.FileDataError, OSError, ValueError):
            continue

    rows = []
    for source in sources:
        title = source["title"]
        paths = matches[title]
        if len(paths) != 1:
            rows.append({"title": title, "split": source["split"],
                         "status": "missing" if not paths else "ambiguous",
                         "match_count": len(paths)})
            continue
        path = paths[0]
        data = path.read_bytes()
        with fitz.open(stream=data, filetype="pdf") as pdf:
            page = source["page"]
            quote = normalized(source["quote"])
            text = pdf[page - 1].get_text() if 0 < page <= pdf.page_count else ""
            rows.append({
                "title": title, "split": source["split"], "status": "pdf_found",
                "file": path.name, "sha256": hashlib.sha256(data).hexdigest(),
                "page_count": pdf.page_count,
                "word_count": sum(len(tokens(p.get_text())) for p in pdf),
                "labelled_page": page,
                "labelled_page_fraction": round(page / pdf.page_count, 3),
                "quote_on_labelled_pdf_page": quote in normalized(text),
            })
    source_blob = json.dumps(sources, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return {"schema_version": 1, "purpose": "local PDF source audit, not human label review",
            "sources_sha256": hashlib.sha256(source_blob).hexdigest(),
            "sources": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_directory", type=Path)
    parser.add_argument("--out", type=Path, default=HERE / "local_pdf_audit.json")
    args = parser.parse_args()
    sources = json.loads((HERE / "sources.json").read_text(encoding="utf-8"))
    result = audit(sources, args.pdf_directory)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"audited {sum(s['status'] == 'pdf_found' for s in result['sources'])}"
          f"/{len(sources)} sources; wrote {args.out}")
