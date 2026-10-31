"""Label review for a conversation set (IR-605 / IR-607 step 1).

prep      builds a self-contained HTML worksheet with machine checks beside each
          conversation. The reviewer ticks the four checks and exports verdicts.
finalize  turns exported verdicts into the label-review file that
          `eval_conversations --label-review` reads, and optionally signs the set.

The machine checks compare the set against docs/evaluation/proxy_starter.json
only. They never confirm a check; only the reviewer's ticks do.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import django

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from apps.ai.evaluation.conversations import (  # noqa: E402
    LABEL_CHECKS, check_label_review, split_digests,
)

DEFAULT_SET = ROOT / "docs/evaluation/general-tools/conversation_set_v1.json"
PROXY = ROOT / "docs/evaluation/proxy_starter.json"
OUT_DIR = ROOT / "docs/evaluation/general-tools/review"

COUNT_TASKS = {"metadata_count", "metadata_count_zero_category", "semantic_topic_count",
               "list_counted_papers", "explain_count_basis", "corpus_facets"}
CATEGORY_TASKS = {"list_by_category", "nonexistent_category_listing", "list_available_categories",
                  "metadata_count_zero_category", "corpus_facets"}
CATEGORY_WORDS = re.compile(r"\b(categor\w*|areas?|under [A-Z])", re.I)


def norm(text):
    return " ".join(str(text or "").lower().split())


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def proxy_facts():
    titles, passages = set(), {}
    for q in load(PROXY)["questions"]:
        for e in q.get("expected") or ():
            titles.add(e["record"])
            passages.setdefault(norm(e["record"]), []).append((e.get("page"), norm(e.get("quote"))))
    return titles, passages


def conversation_titles(c):
    out = list(c.get("papers") or ())
    for t in c["turns"]:
        out += t.get("expected_pair") or []
        out += [e["title"] for e in t.get("required_evidence") or () if e.get("title")]
    return list(dict.fromkeys(out))


def machine_checks(c, titles, passages):
    known = {norm(t) for t in titles}
    unknown = [t for t in conversation_titles(c) if norm(t) not in known]
    evidence = []
    for n, t in enumerate(c["turns"], 1):
        for e in t.get("required_evidence") or ():
            if e.get("page") is None and e.get("quote") is None:
                evidence.append({"turn": n, "title": e["title"], "result": "no_page"})
                continue
            hit = any(p == e.get("page") and q == norm(e.get("quote"))
                      for p, q in passages.get(norm(e["title"]), ()))
            evidence.append({"turn": n, "title": e["title"], "page": e.get("page"),
                             "quote": e.get("quote"), "result": "matches" if hit else "mismatch"})
    counts = [n for n, t in enumerate(c["turns"], 1) if t["intended_task"] in COUNT_TASKS]
    categories = [n for n, t in enumerate(c["turns"], 1)
                  if t["intended_task"] in CATEGORY_TASKS or CATEGORY_WORDS.search(t["user"])]
    has_facts = bool(conversation_titles(c))
    flags = []
    if unknown:
        flags.append("Title not in the 40-paper proxy corpus: " + "; ".join(unknown))
    if any(e["result"] == "mismatch" for e in evidence):
        flags.append("A page or quote does not match proxy_starter.json")
    if c.get("family") == "A09" and "a09_case" not in c:
        flags.append("A09 conversation with no a09_case tag (optional, but it carries no A09 outcome)")
    if any(t["intended_task"] == "partial_answer_after_tool_failure" for t in c["turns"]):
        flags.append("Outage turn: replay makes reads after the first fail; check the turn's "
                     "tolerance fits a partial answer")
    return {
        "unknown_titles": unknown, "evidence": evidence, "count_turns": counts,
        "category_turns": categories, "flags": flags,
        "suggest_na": {
            "category_names": not categories,
            "exact_counts": not counts,
            "paper_page_facts": not has_facts,
            "supported_unambiguous": False,
        },
    }


def topic_index(data):
    groups = {}
    for c in data["conversations"]:
        groups.setdefault(c["topic"], set()).update(c.get("papers") or ())
    return {k: sorted(v) for k, v in sorted(groups.items()) if v}


def prep(args):
    data = load(args.set)
    titles, passages = proxy_facts()
    rows = [{**c, "machine": machine_checks(c, titles, passages)} for c in data["conversations"]]
    payload = {
        "set_id": data["set_id"], "set_path": str(Path(args.set).relative_to(ROOT)),
        "digests": split_digests(data), "checks": list(LABEL_CHECKS),
        "titles": sorted(titles), "topics": topic_index(data), "conversations": rows,
        "drafts": (load(args.drafts)["conversations"] if Path(args.drafts).exists() else {}),
    }
    template = (Path(__file__).with_name("label_review_template.html")).read_text(encoding="utf-8")
    page = template.replace("/*DATA*/null", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))
    out = Path(args.out)
    out.write_text(page, encoding="utf-8")
    flagged = sum(bool(r["machine"]["flags"]) for r in rows)
    print(f"wrote {out} ({len(rows)} conversations, {flagged} with machine flags)")


def finalize(args):
    data = load(args.set)
    verdicts = load(args.verdicts)
    reviewer = args.reviewer.strip()
    untouched = sorted(cid for cid, v in (verdicts.get("conversations") or {}).items()
                       if v.get("source") == "ai_draft")
    if untouched:
        sys.exit(f"not written: {len(untouched)} conversations still hold the AI draft "
                 f"untouched ({', '.join(untouched[:10])}{' …' if len(untouched) > 10 else ''}); "
                 "accept or change each one in the worksheet")
    entries = {}
    for cid, v in (verdicts.get("conversations") or {}).items():
        entries[cid] = {"status": v.get("status", "not_reviewed"),
                        "checks": {k: v.get("checks", {}).get(k) for k in LABEL_CHECKS}}
        if v.get("notes"):
            entries[cid]["notes"] = v["notes"]
    review = {"set_id": data["set_id"], "reviewer": reviewer, "fixture": False,
              "corpus": data["corpus"], "set_digests": split_digests(data),
              "conversations": entries}
    if args.sign:
        data["labelled_by"] = sorted({*data.get("labelled_by", ()), reviewer})
        data["label_status"] = "human_reviewed"
    problems = check_label_review(data, review)
    if problems:
        print("\n".join(problems[:40]))
        if len(problems) > 40:
            print(f"... and {len(problems) - 40} more")
        sys.exit("not written: the review does not yet cover every conversation")
    if args.sign:
        Path(args.set).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"signed {args.set}: labelled_by={data['labelled_by']}, label_status=human_reviewed")
    Path(args.out).write_text(json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {args.out}")
    print("next, from backend/:\n  python manage.py eval_conversations --set "
          f"{Path(args.set).resolve()} --validate --label-review {Path(args.out).resolve()} "
          f"--write-lock {Path(args.set).with_suffix('.lock.json').resolve()}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prep")
    p.add_argument("--set", default=DEFAULT_SET)
    p.add_argument("--out", default=OUT_DIR / "label_review_worksheet.html")
    p.add_argument("--drafts", default=OUT_DIR / "label_review_ai_draft.json",
                   help="AI-suggested verdicts to pre-fill; the reviewer accepts or changes each")
    f = sub.add_parser("finalize")
    f.add_argument("--set", default=DEFAULT_SET)
    f.add_argument("--verdicts", required=True)
    f.add_argument("--reviewer", required=True, help="full name, as it will appear in labelled_by")
    f.add_argument("--out", default=OUT_DIR / "label_review.json")
    f.add_argument("--sign", action="store_true",
                   help="add the reviewer to labelled_by and mark the set human_reviewed")
    args = parser.parse_args()
    prep(args) if args.cmd == "prep" else finalize(args)


if __name__ == "__main__":
    main()
