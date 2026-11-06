"""PROTOTYPE, throwaway, never merge. Rules vs layout model on the real samples.

    python run.py <folder of sample PDFs>

Each reader reads each paper in a fresh process, so its peak memory and time are
its own. Writes a summary to stdout and out/summary.json beside this file, with
counts only: no text from the papers.
"""
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)

WORKER = r'''
import json, sys
sys.path.insert(0, sys.argv[3])
which, path, _, out = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
if which == "rules":
    sys.path.insert(0, sys.argv[3] + "/..")
    import reader
    r = reader.read(path)
else:
    import layout_reader
    r = layout_reader.read(path)
import psutil
info = psutil.Process().memory_info()
r["peak_mib"] = round(getattr(info, "peak_wset", info.rss) / 2**20)   # Windows keeps the peak
json.dump(r, open(out, "w", encoding="utf-8"))
'''

TERMINAL = re.compile(r"[.!?:;][\"”’')\]]*$|https?://\S+$|\d$")
YEAR = re.compile(r"\((?:19|20)\d{2}[a-z]?(?:, [A-Z][a-z]+(?: \d{1,2})?)?\)\.")


def run(which, pdf):
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "r.json"
        script = Path(d) / "w.py"
        script.write_text(WORKER, encoding="utf-8")
        start = time.time()
        proc = subprocess.Popen([sys.executable, str(script), which, str(pdf), str(HERE), str(out)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ps, peak = psutil.Process(proc.pid), 0
        while proc.poll() is None:
            try:
                peak = max(peak, ps.memory_info().rss)
            except psutil.Error:
                pass
            time.sleep(0.05)
        seconds = time.time() - start
        reading = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    return reading, seconds, peak / 2**20


def quality(r):
    passages = [p for s in r["sections"] for p in s["passages"] if p["kind"] == "sentence"]
    words = [len(p["text"].split()) for p in passages] or [0]
    cut = sum(1 for p in passages if not TERMINAL.search(p["text"]))
    refs = [s for s in r["sections"] if s["key"].startswith("reference")]
    entries = []
    if refs:
        paras = {}
        for p in refs[0]["passages"]:
            paras.setdefault(p["paragraph"], []).append(p["text"])
        entries = [" ".join(v) for v in paras.values()]
    glued = sum(1 for e in entries if len(YEAR.findall(e)) > 1 or len(re.findall(r"\[\d+\]", e)) > 1)
    return {
        "sections": len(r["sections"]),
        "sentences": len(passages),
        "cut_sentences_pct": round(100 * cut / max(1, len(passages)), 1),
        "tiny_pct": round(100 * sum(1 for w in words if w <= 3) / max(1, len(words)), 1),
        "reference_entries": len(entries),
        "references_glued": glued,
        "warnings": [w["code"] for w in r["warnings"]],
        **r.get("stats", {}),
    }


def changed(a, b):
    by_b = {s["key"]: s["text_hash"] for s in b["sections"]}
    by_a = {s["key"]: s["text_hash"] for s in a["sections"]}
    return {
        "changed": sorted(k for k in by_a if k in by_b and by_a[k] != by_b[k]),
        "only_v1": sorted(k for k in by_a if k not in by_b),
        "only_v2": sorted(k for k in by_b if k not in by_a),
    }


def main(folder):
    folder = Path(folder)
    papers = sorted(folder.glob("*.pdf"), key=lambda p: p.name.lower())
    summary, readings = {}, {}
    for pdf in papers:
        for which in ("rules", "layout"):
            reading, seconds, mib = run(which, pdf)
            readings[(pdf.name, which)] = reading
            row = {"seconds": round(seconds, 1),
                   "peak_mib": reading.get("peak_mib") if reading else None}
            row.update(quality(reading) if reading else {"failed": True})
            summary.setdefault(pdf.name, {})[which] = row
            print(f"{pdf.name:16} {which:6} {row}", flush=True)
    pairs = {}
    for v1 in papers:
        if "_v1" not in v1.name:
            continue
        v2 = v1.with_name(v1.name.replace("_v1", "_v2"))
        if not v2.exists():
            continue
        for which in ("rules", "layout"):
            a, b = readings[(v1.name, which)], readings[(v2.name, which)]
            if a and b:
                pairs.setdefault(v1.stem.replace("_v1", ""), {})[which] = changed(a, b)
    for name, result in pairs.items():
        for which, c in result.items():
            print(f"pair {name:8} {which:6} changed={len(c['changed'])} only_v1={len(c['only_v1'])} "
                  f"only_v2={len(c['only_v2'])}")
    (OUT / "summary.json").write_text(json.dumps({"papers": summary, "pairs": pairs}, indent=1),
                                      encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1])
