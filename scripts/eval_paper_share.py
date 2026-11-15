"""Replay the runtime's passage selection under each per-paper share (IR-1150).

Offline and free: keyword candidates only, ranked once per question as
`ResearchTools.search` ranks them, then handed to `ai.research.selection.select`
under every arm, so only selection varies. Proxy tier (ADR-023).

    python scripts/eval_paper_share.py --db iris_ir1054 --variant g_structural \
        --questions docs/evaluation/proxy_starter.json --out docs/evaluation/runs/<file>.json

Database login comes from backend/.env (DB_HOST, DB_PORT, DB_USER, DB_PASSWORD).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import django
import psycopg2
import psycopg2.extras

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
# The evaluation package imports models; nothing here touches Django's database.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from ai.research.selection import Hit, Policy, choose, neighbour_positions, select  # noqa: E402
from ai.research.tools import CANDIDATES, CONFIG  # noqa: E402
from apps.ai.evaluation.labels import load_question_set  # noqa: E402

SHARES = (0, 25, 33, 50, 75, 100)

COLUMNS = ("c.id, c.record_id, c.chunk_set_id, c.sequence, c.token_count, c.section_key,"
           " c.content, r.title")
SETS = ("FROM ai_documentchunk c JOIN ai_chunkset cs ON cs.id = c.chunk_set_id"
        " JOIN records_record r ON r.id = c.record_id"
        " WHERE c.deleted_at IS NULL AND cs.trial_variant IS NOT DISTINCT FROM %(variant)s"
        " AND (%(variant)s IS NOT NULL OR cs.is_active)")
# The runtime's keyword search, over one chunk-set variant instead of the active sets.
KEYWORD = (f"""WITH q AS (SELECT replace(plainto_tsquery('{CONFIG}', %(query)s)::text, '&', '|')::tsquery AS q)
    SELECT {COLUMNS}, ts_rank(c.search_vector, q.q) AS rank {SETS} AND c.search_vector @@ q.q
     ORDER BY rank DESC, c.id LIMIT %(n)s""").replace("FROM ai_documentchunk c", "FROM q, ai_documentchunk c")
NEIGHBOURS = f"SELECT {COLUMNS} {SETS} AND (c.chunk_set_id, c.sequence) IN %(positions)s"


class Passage:
    """What a label matches against."""

    def __init__(self, row):
        self.record_id, self.record_title, self.content = row["record_id"], row["title"], row["content"]


def hit(row) -> Hit:
    key = row["section_key"]
    tokens = row["token_count"]
    return Hit(row["id"], row["record_id"], row["chunk_set_id"], row["sequence"],
               tuple(key) if key else None, tokens if tokens is not None else len(row["content"]) // 4 + 1)


def kind_of(question) -> str:
    papers = {label.record for label in question.expected}
    if len(papers) >= 2:
        return "multi-paper"
    if len(papers) == 1:
        return "single-paper"
    return "unlabelled"


def connect(db: str):
    env = dict(line.strip().split("=", 1) for line in (ROOT / "backend/.env").read_text().splitlines()
               if "=" in line and not line.lstrip().startswith("#"))
    return psycopg2.connect(host=env["DB_HOST"], port=env["DB_PORT"], user=env["DB_USER"],
                            password=env["DB_PASSWORD"], dbname=db)


def candidates(cur, query: str, variant, limit: int):
    cur.execute(KEYWORD, {"query": query, "variant": variant, "n": max(limit, CANDIDATES)})
    rows = cur.fetchall()
    hits = [hit(r) for r in rows]
    # Every position a section-mate could take under any arm, read once.
    positions = set()
    for share in SHARES:
        positions |= neighbour_positions(choose(hits, limit, Policy(paper_share=share)))
    neighbours = []
    if positions:
        cur.execute(NEIGHBOURS, {"variant": variant, "positions": tuple(positions)})
        neighbours = cur.fetchall()
    return rows, neighbours


def measure(question, rows, neighbours, limit: int, share: int) -> dict:
    by_id = {r["id"]: r for r in (*rows, *neighbours)}
    placed = select([hit(r) for r in rows], limit, Policy(paper_share=share),
                    neighbours=[hit(r) for r in neighbours])
    tokens: dict[int, int] = {}
    for p in placed:
        tokens[p.hit.record_id] = tokens.get(p.hit.record_id, 0) + p.hit.tokens
    total = sum(tokens.values())
    passages = [Passage(by_id[p.hit.id]) for p in placed]
    found = [label for label in question.expected if any(label.matches(p) for p in passages)]
    papers = {label.record for label in question.expected}
    papers_found = {label.record for label in found}
    return {
        "passages": len(placed),
        "mates": sum(p.section_mate for p in placed),
        "papers": len(tokens),
        "tokens": total,
        "top_share": max(tokens.values()) / total if total else 0.0,
        "labels": len(question.expected),
        "labels_found": len(found),
        "papers_expected": len(papers),
        "papers_found": len(papers_found),
    }


def ceiling(question, rows, neighbours) -> int:
    """Labels any candidate or neighbour holds: what no selection can beat."""
    passages = [Passage(r) for r in (*rows, *neighbours)]
    return sum(any(label.matches(p) for p in passages) for label in question.expected)


def summarize(rows: list[dict]) -> dict:
    searched = [r for r in rows if r["tokens"]]
    labelled = [r for r in rows if r["labels"]]
    labels = sum(r["labels"] for r in labelled)
    return {
        "questions": len(rows),
        "searches_with_results": len(searched),
        "labels": labels,
        "label_recall": round(sum(r["labels_found"] for r in labelled) / labels, 3) if labels else None,
        "all_papers_found": (round(sum(r["papers_found"] == r["papers_expected"] for r in labelled)
                                   / len(labelled), 3) if labelled else None),
        "mean_papers": round(statistics.mean(r["papers"] for r in searched), 2) if searched else None,
        "dominated_over_50pct": (round(sum(r["top_share"] > 0.5 for r in searched) / len(searched), 3)
                                 if searched else None),
        "mean_top_share": round(statistics.mean(r["top_share"] for r in searched), 3) if searched else None,
        "mean_tokens": round(statistics.mean(r["tokens"] for r in searched)) if searched else None,
        "p90_tokens": (round(statistics.quantiles([r["tokens"] for r in searched], n=10)[-1])
                       if len(searched) > 1 else None),
        "mean_passages": round(statistics.mean(r["passages"] for r in searched), 2) if searched else None,
        "mean_mates": round(statistics.mean(r["mates"] for r in searched), 2) if searched else None,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default="iris_ir1054")
    parser.add_argument("--variant", default="g_structural",
                        help="chunk_set.trial_variant to search; 'active' for the active sets")
    parser.add_argument("--questions", default=str(ROOT / "docs/evaluation/proxy_starter.json"))
    parser.add_argument("--limits", default="10,5", help="search limits to replay, comma-separated")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    variant = None if args.variant == "active" else args.variant
    limits = [int(n) for n in args.limits.split(",")]

    question_set = load_question_set(args.questions)
    conn = connect(args.db)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT count(*) AS chunks, count(c.section_key) AS keyed,"
                f" count(DISTINCT c.record_id) AS papers {SETS}", {"variant": variant})
    corpus = dict(cur.fetchone())

    runs = []
    for limit in limits:
        per_question = []
        for question in question_set.questions:
            query = question.resolved_question or question.question
            rows, neighbours = candidates(cur, query, variant, limit)
            per_question.append({
                "id": question.id, "kind": question.kind, "type": kind_of(question),
                "candidates": len(rows), "ceiling": ceiling(question, rows, neighbours),
                "arms": {str(share): measure(question, rows, neighbours, limit, share) for share in SHARES},
            })
        table = {}
        for share in SHARES:
            groups = {"all": per_question}
            for name in ("single-paper", "multi-paper", "unlabelled"):
                groups[name] = [q for q in per_question if q["type"] == name]
            groups["cross-paper kind"] = [q for q in per_question if q["kind"] == "cross-paper"]
            table[str(share)] = {g: summarize([q["arms"][str(share)] for q in qs]) for g, qs in groups.items()}
        labelled = [q for q in per_question if q["type"] != "unlabelled"]
        runs.append({
            "limit": limit,
            "budget_tokens": limit * Policy().tokens_per_passage,
            "candidate_ceiling_label_recall": round(sum(q["ceiling"] for q in labelled)
                                                    / sum(q["arms"]["0"]["labels"] for q in labelled), 3),
            "summary": table,
            "per_question": per_question,
        })

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    out = {
        "ticket": "IR-1150",
        "tier": "proxy",
        "note": "Proxy corpus (ADR-023): an engineering measurement, never a finding about CIT-U research.",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": commit,
        "database": args.db,
        "chunk_set_variant": args.variant,
        "corpus": corpus,
        "question_set": {"name": question_set.name, "questions": len(question_set.questions)},
        "candidates": f"runtime keyword search, top max(limit, {CANDIDATES}) by ts_rank; no vector, no rerank",
        "query": "resolved_question when present, else the question text",
        "policy": {"tokens_per_passage": Policy().tokens_per_passage, "join": True, "section_mates": True,
                   "paper_share": list(SHARES)},
        "runs": runs,
    }
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for run in runs:
        print(f"\nlimit {run['limit']} (budget {run['budget_tokens']}), "
              f"candidate ceiling {run['candidate_ceiling_label_recall']}")
        for group in ("all", "single-paper", "multi-paper", "cross-paper kind", "unlabelled"):
            print(f"  {group}")
            for share in SHARES:
                s = run["summary"][str(share)][group]
                print(f"    share {share:>3}: recall {s['label_recall']}  all-papers {s['all_papers_found']}"
                      f"  papers {s['mean_papers']}  >50% {s['dominated_over_50pct']}"
                      f"  top {s['mean_top_share']}  tokens {s['mean_tokens']} (p90 {s['p90_tokens']})"
                      f"  passages {s['mean_passages']} mates {s['mean_mates']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
