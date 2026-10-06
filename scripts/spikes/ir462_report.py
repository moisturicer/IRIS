"""THROWAWAY (IR-462): tabulate ir462_runs.json."""

import json
import statistics as st
import sys
from collections import Counter, defaultdict

d = json.load(open(sys.argv[1], encoding="utf-8"))
rows = d["rows"]
print("config", d["config"], "rows", len(rows))


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))]


groups = defaultdict(list)
for r in rows:
    groups[(r["mech"], r["effort"])].append(r)

for (mech, effort), g in sorted(groups.items()):
    print(f"\n=== {mech} / reasoning={effort}  n={len(g)}")
    for run in sorted({r["run"] for r in g}):
        rr = [r for r in g if r["run"] == run]
        parsed = [r for r in rr if r["decision"]]
        correct = [r for r in parsed if r["decision"] == r["label"]]
        print(
            f"  run {run}: parseable {len(parsed)}/{len(rr)}  "
            f"accuracy(all) {len(correct)/len(rr):.3f}  "
            f"accuracy(parsed) {len(correct)/max(1,len(parsed)):.3f}"
        )
    parsed = [r for r in g if r["decision"]]
    correct = [r for r in parsed if r["decision"] == r["label"]]
    s = [r for r in g if r["label"] == "search"]
    a = [r for r in g if r["label"] == "answer"]
    miss = sum(1 for r in s if r["decision"] != "search")
    over = sum(1 for r in a if r["decision"] != "answer")
    print(f"  pooled accuracy {len(correct)/len(g):.3f}; missed-search {miss}/{len(s)} ({miss/len(s):.3f}); over-search {over}/{len(a)} ({over/len(a):.3f})")
    lat = [r["latency"] for r in g if r["latency"]]
    print(f"  latency s: mean {st.mean(lat):.2f} p50 {pct(lat,.5):.2f} p95 {pct(lat,.95):.2f} max {max(lat):.2f}")
    rt = [r["reasoning_tokens"] for r in g if r["reasoning_tokens"] is not None]
    if rt:
        print(f"  reasoning tokens mean {st.mean(rt):.0f}")
    print("  failures:", dict(Counter(r["failure"] for r in g if r["failure"])))
    ex = {}
    for r in g:
        if r["failure"] and r.get("example") and r["failure"] not in ex:
            ex[r["failure"]] = (r["id"], r["example"])
    for k, v in ex.items():
        print(f"    e.g. {k}: {v}")
    # run-to-run flips
    by_q = defaultdict(set)
    for r in g:
        by_q[r["id"]].add(r["decision"])
    flips = sorted(q for q, v in by_q.items() if len(v) > 1)
    print(f"  questions whose decision changed between runs: {len(flips)} {flips}")
    wrong = Counter(r["id"] for r in g if r["decision"] != r["label"])
    print("  most-missed:", wrong.most_common(8))
    kinds = defaultdict(lambda: [0, 0])
    for r in g:
        kinds[r["kind"]][1] += 1
        kinds[r["kind"]][0] += r["decision"] == r["label"]
    print("  by kind:", {k: f"{c}/{n}" for k, (c, n) in sorted(kinds.items())})
