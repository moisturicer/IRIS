"""IR-1147: each floor against g_hybrid, reranked final-set recall, paired.

    python compare.py   (from this directory; reads the run files beside it)
"""

import glob
import json
from math import comb

SETS = {"proxy-starter": "main", "proxy-record-scoped": "one-paper slice", "figure_reranker_ir1125": "Figure set"}
BASELINE = "g_hybrid"


def load():
    runs = {}
    for path in sorted(glob.glob("*.json")):
        data = json.load(open(path, encoding="utf-8"))
        for run in data["runs"]:
            if not run["config"]["reranking"]:
                continue
            variant = run["provenance"]["chunking"]["variant"]
            runs[(variant, run["question_set"]["name"])] = run
    return runs


def sign_test(wins: int, losses: int) -> float:
    """Two-sided exact binomial test on the discordant questions."""
    n = wins + losses
    if n == 0:
        return 1.0
    tail = sum(comb(n, k) for k in range(min(wins, losses) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def per_question(run):
    return {q["question_id"]: q["final_set_recall"] for q in run["questions"]}


def main():
    runs = load()
    variants = sorted({v for v, _ in runs if v != BASELINE}, key=lambda v: int(v.split("sib")[1]))
    print("| Variant | " + " | ".join(SETS.values()) + " |")
    print("|---|" + "---|" * len(SETS))
    for variant in [BASELINE, *variants]:
        cells = [f"{runs[(variant, s)]['measures']['final_set_recall']:.3f}" for s in SETS]
        print(f"| {variant} | " + " | ".join(cells) + " |")
    print()
    for variant in variants:
        for s, label in SETS.items():
            base, mine = per_question(runs[(BASELINE, s)]), per_question(runs[(variant, s)])
            won = sorted(q for q in base if mine.get(q, 0) > base[q])
            lost = sorted(q for q in base if mine.get(q, 0) < base[q])
            delta = runs[(variant, s)]["measures"]["final_set_recall"] - runs[(BASELINE, s)]["measures"]["final_set_recall"]
            print(f"{variant} {label}: {delta:+.3f}, won {len(won)} {won}, lost {len(lost)} {lost}, "
                  f"p = {sign_test(len(won), len(lost)):.3f}")


if __name__ == "__main__":
    main()
