"""PROTOTYPE, throwaway, never merge. Rules vs GROBID vs the hybrid, scored per set.

    python -I fetch.py <folder of sample PDFs>        # first, with GROBID running
    python -I run.py <folder of sample PDFs> tuning   # or held_out

Writes out/scores-<set>.json and prints a summary: counts only, no paper text.
The rules read each paper in a fresh process, so its time and peak memory are
its own; GROBID's come from fetch.py (request time, container peak).
"""
import copy
import hashlib
import json
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import psutil  # noqa: E402

import score  # noqa: E402
import tei_reader  # noqa: E402
from tei_reader import reader  # noqa: E402

OUT = HERE / "out"

# Chosen on the tuning set only, 2026-11-08, before any held-out output was
# read: the plain hybrid, no guard. No guard beat the rules on references
# there, and the fallback never fired (no tuning paper collapsed), so
# hybrid_fallback is reported beside it rather than put forward.
CANDIDATE = "hybrid"

WORKER = r'''
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("r", sys.argv[1]); r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
json.dump(r.read(sys.argv[2]), open(sys.argv[3], "w", encoding="utf-8"))
'''


def rules_reading(pdf):
    """Today's rules on one paper, cached in out/rules/."""
    target = OUT / "rules" / (pdf.name + ".json")
    if target.exists():
        return json.loads(target.read_text(encoding="utf-8"))
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        out, script = Path(d) / "r.json", Path(d) / "w.py"
        script.write_text(WORKER, encoding="utf-8")
        start = time.time()
        proc = subprocess.Popen([sys.executable, "-I", str(script), str(HERE.parent / "reader.py"), str(pdf), str(out)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ps, peak = psutil.Process(proc.pid), 0
        while proc.poll() is None:
            # A Windows venv's python.exe is a launcher that runs the real
            # interpreter as a child, so the reader's memory is the tree's.
            try:
                tree = [ps, *ps.children(recursive=True)]
            except psutil.Error:
                tree = []
            rss = 0
            for p in tree:
                try:
                    rss += p.memory_info().rss
                except psutil.Error:
                    pass
            peak = max(peak, rss)
            time.sleep(0.05)
        seconds = time.time() - start
        r = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    if r is None:
        r = {"failed": True, "sections": [], "warnings": [], "page_count": 0}
    r["_seconds"], r["_peak_mib"] = round(seconds, 1), round(peak / 2**20)
    target.write_text(json.dumps(r), encoding="utf-8")
    return r


def _rehash(section):
    section["text_hash"] = hashlib.sha256(
        "\n".join(reader.norm(p["text"]) for p in section["passages"]).encode()).hexdigest()


def hybrid(rules, tei, fallback=False):
    """The rules for the body, GROBID for the reference list.

    ``fallback`` also takes GROBID's whole reading when the rules' fail-safe
    fired and GROBID's did not (a choice made on the tuning set only)."""
    out = copy.deepcopy(rules)
    out["reader"] = "hybrid-" + ("refs+fallback" if fallback else "refs")
    if tei is None:
        return out
    if fallback and score.collapsed(rules):
        g = tei_reader.read(tei, rules.get("page_count"))
        if not score.collapsed(g):
            g["reader"] = out["reader"]
            return g
    refs = tei_reader.references(tei, rules.get("page_count"))
    at = next((i for i, s in enumerate(out["sections"]) if reader._is_references(s["heading"])), None)
    if refs is None or at is None:
        return out
    base = max((p["paragraph"] for s in out["sections"] for p in s["passages"]), default=0)
    for n, p in enumerate(refs["passages"], start=1):
        p["paragraph"] = base + n
    out["sections"][at]["passages"] = refs["passages"]
    _rehash(out["sections"][at])
    return out


def summarize(rows):
    def total(field, sub):
        return sum(r[field].get(sub, 0) or 0 for r in rows)

    keyed = [r for r in rows if r["headings"]]
    found, matched, marks = total("headings", "headings"), total("headings", "matched"), total("headings", "bookmarks")
    cov = [r["coverage"] for r in rows if r["coverage"] is not None]
    secs = [r["seconds"] for r in rows if r["seconds"] is not None]
    return {
        "papers": len(rows),
        "collapsed": sum(r["collapsed"] for r in rows),
        "heading_papers": len(keyed),
        "heading_precision": round(matched / found, 3) if found else None,
        "heading_recall": round(matched / marks, 3) if marks else None,
        "papers_with_references": sum(1 for r in rows if r["references"]["entries"]),
        "reference_entries": total("references", "entries"),
        "references_off_pattern": total("references", "off_pattern"),
        "references_over_120_words": total("references", "over_120_words"),
        "ieee_papers": sum(1 for r in rows if r["references"].get("style") == "ieee"),
        "references_unlabelled": total("references", "unlabelled"),
        "ieee_papers_too_few": sum(1 for r in rows if r["references"].get("too_few")),
        "ieee_entries_too_few": total("references", "too_few"),
        "ieee_papers_too_many": sum(1 for r in rows if r["references"].get("too_many")),
        "ieee_entries_too_many": total("references", "too_many"),
        "coverage_mean": round(statistics.mean(cov), 4) if cov else None,
        "coverage_min": min(cov) if cov else None,
        "seconds_median": statistics.median(secs) if secs else None,
        "seconds_max": max(secs) if secs else None,
        "peak_mib_max": max((r["peak_mib"] or 0) for r in rows),
    }


def main(folder, which):
    folder = Path(folder)
    split = json.loads((HERE / "split.json").read_text(encoding="utf-8"))
    # Papers not on this machine (a licence that doesn't allow sharing) are
    # left out and named, never silently: the README must list them.
    missing = [n for n in split[which] if not (folder / n).exists()]
    names = [n for n in split[which] if n not in missing]
    if missing:
        print(f"left out of {which} (not in {folder}): {', '.join(missing)}", flush=True)
    fetch = json.loads((OUT / "fetch.json").read_text(encoding="utf-8"))
    readings = {}
    per_paper = {}
    for name in names:
        pdf = folder / name
        rules = rules_reading(pdf)
        tei_path = OUT / "tei" / (name + ".xml")
        tei = tei_path.read_bytes() if tei_path.exists() else None
        g = tei_reader.read(tei, rules.get("page_count")) if tei else None
        f = fetch.get(name, {})
        approaches = {
            "rules": (rules, rules["_seconds"], rules["_peak_mib"]),
            "grobid": (g, f.get("seconds"), f.get("peak_mib")),
            "hybrid": (hybrid(rules, tei), _add(rules["_seconds"], f.get("seconds")),
                       max(rules["_peak_mib"], f.get("peak_mib") or 0)),
            "hybrid_fallback": (hybrid(rules, tei, True), _add(rules["_seconds"], f.get("seconds")),
                                max(rules["_peak_mib"], f.get("peak_mib") or 0)),
        }
        key = score.bookmarks(pdf)
        style = score.reference_style(rules)   # every approach is judged by the paper's own style
        body = score.pdf_words(pdf)
        for label, (r, seconds, mib) in approaches.items():
            readings[(name, label)] = r
            if r is None:
                row = {"failed": True, "collapsed": True, "headings": {}, "references": {"entries": 0},
                       "coverage": 0.0, "seconds": seconds, "peak_mib": mib}
            else:
                row = {"sections": len(r["sections"]), "collapsed": score.collapsed(r),
                       "warnings": sorted({w["code"] for w in r["warnings"]}),
                       "headings": score.headings(r, key), "references": score.reference_entries(r, style),
                       "coverage": score.coverage(r, body), "seconds": seconds, "peak_mib": mib}
            per_paper.setdefault(name, {})[label] = row
        print(f"{name:18} " + "  ".join(
            f"{k}: sec={v.get('sections')} col={int(v['collapsed'])} cov={v['coverage']} "
            f"ref={v['references'].get('entries')}/{v['references'].get('off_pattern')}"
            for k, v in per_paper[name].items()), flush=True)

    pairs = {}
    for pair, spec in split["pairs"].items():
        v1, v2 = spec["files"]
        if v1 not in names or v2 not in names:
            continue   # a pair counts only with both Versions present
        for label in ("rules", "grobid", "hybrid", "hybrid_fallback"):
            a, b = readings.get((v1, label)), readings.get((v2, label))
            if a and b:
                pairs.setdefault(pair, {})[label] = score.version_pair(a, b, spec["edited"])

    labels = ("rules", "grobid", "hybrid", "hybrid_fallback")
    summary = {label: summarize([per_paper[n][label] for n in names]) for label in labels}
    for label in labels:
        ps = [p[label] for p in pairs.values() if label in p]
        summary[label].update({"pairs": len(ps), "pair_false_changes": sum(p["false_changes"] for p in ps),
                               "pair_missed_edits": sum(p["missed_edits"] for p in ps),
                               "pair_true_changes": sum(p["true_changes"] for p in ps),
                               "pairs_collapsed": sum(p["collapsed"] for p in ps)})
    (OUT / f"scores-{which}.json").write_text(
        json.dumps({"set": which, "left_out": missing, "summary": summary, "pairs": pairs,
                    "papers": per_paper}, indent=1),
        encoding="utf-8")
    print()
    for label in labels:
        print(f"{label:16} {summary[label]}")
    for pair, result in pairs.items():
        print(f"pair {pair:10} " + "  ".join(
            f"{k}: false={v['false_changes']} missed={v['missed_edits']} col={int(v['collapsed'])}"
            for k, v in result.items()))


def _add(a, b):
    return None if a is None or b is None else round(a + b, 1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
