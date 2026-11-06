"""Draft IR-753 cases from the existing 40-paper proxy references, without model output."""

import json
from pathlib import Path


ROOT = Path(__file__).parent
EVALUATION = ROOT.parent
FAMILIES = {
    "L01": "long_manuscript",
    "L02": "middle_late_evidence",
    "L03": "repeated_manual_compaction",
    "L04": "exact_detail_recovery",
    "L05": "revocation",
    "L06": "partial_outage",
    "L07": "interrupted_research",
}
SOURCE_QUESTION_IDS = ("q04", "q06", "q07", "q08", "q09", "q12",
                       "q01", "q03", "q18", "q16")


def turn(user, task, evidence=(), uncertainty="Report limits and cite the original page."):
    return {
        "user": user, "intended_task": task, "expected_pair": [],
        "required_evidence": list(evidence), "clarification_necessary": False,
        "acceptable_uncertainty": uncertainty,
    }


def scenario(family, source):
    title, question = source["title"], source["question"]
    evidence = {"title": title, "page": source["page"], "quote": source["quote"]}
    ask = f"In {title}, {question}"
    if family == "L01":
        return [turn(ask, "read_selected_manuscript", [evidence])], \
            "Read the selected source and record actual page coverage. This proxy source is not yet verified as a long Manuscript."
    if family == "L02":
        return [turn(f"Check the relevant sections of {title} before answering: {question}",
                     "find_middle_late_evidence", [evidence])], \
            "Verify page position against the actual Manuscript; this proxy citation alone does not establish middle/late coverage."
    if family == "L03":
        return [turn(f"Keep {title} selected. I want to answer: {question}",
                     "set_research_goal"),
                turn("Compact this conversation now.", "manual_compaction"),
                turn("Continue the same investigation after two automatic compactions.",
                     "continue_after_compaction"),
                turn("What was the answer, and where was it stated?",
                     "answer_after_compaction", [evidence])], \
            "Harness must trigger two automatic compactions and a manual one; preserve selection, goal and citation."
    if family == "L04":
        return [turn(ask, "read_and_remember_detail", [evidence]),
                turn("Compact the earlier exchange.", "manual_compaction"),
                turn("Recover the exact original detail and page, without guessing from the summary.",
                     "recover_original_detail", [evidence])], \
            "Recover the original Turn/source binding; a paraphrased handoff is not exact evidence."
    if family == "L05":
        return [turn(ask, "read_before_revocation", [evidence]),
                turn("What did you find in that paper earlier?", "continue_after_revocation", (),
                     "Do not repeat a revoked fact, citation or derived summary.")], \
            "Harness must revoke Record access between turns, then check prompt, answer, citation and handoff."
    if family == "L06":
        return [turn(f"Read {title} and investigate the question: {question}",
                     "read_before_partial_outage", [evidence]),
                turn("What can you conclude so far, and what remains unchecked?",
                     "partial_answer_after_tool_failure", [evidence],
                     "Identify the failed read and do not claim complete coverage.")], \
            "Harness must fail a subsequent read after the first succeeds and record fault=fired."
    return [turn(ask, "start_research", [evidence]),
            turn("Continue the investigation from where we left off.",
                 "resume_interrupted_research", [evidence],
                 "No duplicate final Turn; retain original source and run identity.")], \
        "Harness must interrupt the worker after a committed step and reconnect the same run."


def selected_sources():
    baseline = json.loads((EVALUATION / "general-tools/conversation_set_v1.json").read_text(
        encoding="utf-8"))
    questions = {q["id"]: q for q in json.loads(
        (EVALUATION / "proxy_starter.json").read_text(encoding="utf-8"))["questions"]}
    by_title = {}
    for case in baseline["conversations"]:
        for title in case["papers"]:
            by_title[title] = case["split"]
    selected = []
    for qid in SOURCE_QUESTION_IDS:
        question = questions[qid]
        expected = next(e for e in question["expected"] if e.get("record") in by_title
                        and isinstance(e.get("page"), int) and e.get("quote"))
        title = expected["record"]
        selected.append({
            "question_id": qid, "question": question["question"],
            "title": title, "page": expected["page"], "quote": expected["quote"],
            "split": by_title[title], "source_state": "proxy_reference_needs_recheck",
        })
    return selected, baseline


def build():
    sources, baseline = selected_sources()
    if (len(sources) != 10 or len({source["title"] for source in sources}) != 10
            or [source["split"] for source in sources] !=
            ["development"] * 6 + ["held_out"] * 4):
        raise ValueError("the proxy set needs six development and four held-out sources")
    cases = []
    for family, name in FAMILIES.items():
        for index, source in enumerate(sources, 1):
            turns, setup = scenario(family, source)
            split = source["split"]
            cases.append({
                "id": f"{family}-{'D' if split == 'development' else 'H'}{index:02d}",
                "family": family, "scenario": name, "split": split,
                "topic": source["title"], "papers": [source["title"]],
                "supported_unambiguous": True, "turns": turns,
                "harness_setup": setup, "source_state": source["source_state"],
                "proxy_question_id": source["question_id"],
                "reportable": family not in ("L01", "L02"),
                **({"inconclusive_reason": "selected proxy source has not established the required long or late-page behavior"}
                   if family in ("L01", "L02") else {}),
            })
    pack = {
        "schema_version": 1, "set_id": "long-context-ir753-draft-v2",
        "label_status": "draft_unreviewed", "labelled_by": [],
        "families": list(FAMILIES), "min_family_cases": 10, "rubric_version": 1,
        "corpus": {**baseline["corpus"], "ingested": False},
        "partition_method": "Reuses the 40-paper proxy split; six development and four held-out source titles, no source crosses splits.",
        "shared_allowed": [], "conversations": cases,
    }
    return sources, pack


if __name__ == "__main__":
    sources, pack = build()
    for name, value in (("sources.json", sources), ("conversation_set_v1.json", pack)):
        (ROOT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n",
                                 encoding="utf-8")
