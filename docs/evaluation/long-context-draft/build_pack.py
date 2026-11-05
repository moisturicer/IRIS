"""Build the IR-753 review draft. No model, database, or counted output is read."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).parent
THEMES = (
    "coastal flood routing", "campus energy demand", "soil moisture mapping",
    "urban heat shelters", "river sediment transport", "crop disease screening",
    "emergency radio coverage", "bridge fatigue sensing", "water quality sampling",
    "public transit reliability",
)
FAMILIES = {
    "L01": "long_manuscript",
    "L02": "middle_late_evidence",
    "L03": "repeated_manual_compaction",
    "L04": "exact_detail_recovery",
    "L05": "revocation",
    "L06": "partial_outage",
    "L07": "interrupted_research",
}
def turn(user, task, evidence=(), uncertainty="Report limits and cite the original page."):
    return {
        "user": user,
        "intended_task": task,
        "expected_pair": [],
        "required_evidence": list(evidence),
        "clarification_necessary": False,
        "acceptable_uncertainty": uncertainty,
    }


def scenario(family, theme, title, fact, page):
    evidence = {"title": title, "page": page, "quote": fact}
    ask = f"In {title}, what does the {theme} study conclude about its main constraint?"
    if family == "L01":
        return [turn(ask, "read_selected_manuscript", [evidence])], \
            "Read the selected 100-page Manuscript; state covered ranges and the page binding."
    if family == "L02":
        return [turn(f"Check the middle and final sections of {title} before answering: {ask}",
                     "find_middle_late_evidence", [evidence])], \
            "The planted fact is on a middle or late page; an introduction-only read is insufficient."
    if family == "L03":
        return [turn(f"Keep {title} selected and remember I want the {theme} constraint.",
                     "set_research_goal"),
                turn("Compact this conversation now.", "manual_compaction"),
                turn("Continue the same investigation after two automatic compactions.",
                     "continue_after_compaction"),
                turn("What was the constraint, and where was it stated?",
                     "answer_after_compaction", [evidence])], \
            "Harness must trigger two automatic compactions and a manual one; preserve selection, goal and citation."
    if family == "L04":
        return [turn(f"Remember that I selected {title}; inspect the {theme} constraint.",
                     "read_and_remember_detail", [evidence]),
                turn("Compact the earlier exchange.", "manual_compaction"),
                turn("Recover the exact original detail and page, without guessing from the summary.",
                     "recover_original_detail", [evidence])], \
            "Recover the original Turn/source binding; a paraphrased handoff is not exact evidence."
    if family == "L05":
        return [turn(ask, "read_before_revocation", [evidence]),
                turn("What did you find in that paper earlier?",
                     "continue_after_revocation", (),
                     "Do not repeat the revoked fact, citation or derived summary.")], \
            "After turn 1, harness revokes Record access before turn 2; no later answer, provider prompt, citation or handoff may expose it."
    if family == "L06":
        return [turn(f"Compare the available evidence for {theme}; read {title} first.",
                     "read_before_partial_outage", [evidence]),
                turn("What can you conclude so far, and what remains unchecked?",
                     "partial_answer_after_tool_failure", [evidence],
                     "Identify the failed read and do not claim complete coverage.")], \
            "Harness fails a subsequent read after the first succeeds; record fault=fired and retain only the supported partial result."
    return [turn(f"Investigate {theme} in {title} and cite the original source.",
                 "start_research", [evidence]),
            turn("Continue the investigation from where we left off.",
                 "resume_interrupted_research", [evidence],
                 "No duplicate final Turn; retain original source and run identity.")], \
        "Harness interrupts the worker after a committed step, then reconnects the same run before turn 2; record the recovery event."


def build():
    sources, conversations = [], []
    for family, name in FAMILIES.items():
        for index, theme in enumerate(THEMES, 1):
            split = "development" if index <= 6 else "held_out"
            title = f"Synthetic {theme.title()} Manuscript {family}-{index:02d}"
            page = 52 if index % 2 else 91
            fact = f"Constraint {family}-{index:02d}: the {theme} estimate is limited by missing late-season observations."
            sources.append({"title": title, "split": split, "pages": 100,
                            "planted_fact": {"page": page, "quote": fact},
                            "fixture_status": "planned_not_ingested"})
            turns, setup = scenario(family, theme, title, fact, page)
            conversations.append({
                "id": f"{family}-{'D' if split == 'development' else 'H'}{index:02d}",
                "family": family, "scenario": name, "split": split,
                "topic": f"{theme} {family}", "papers": [title],
                "supported_unambiguous": True, "turns": turns,
                "harness_setup": setup,
                "source_state": "synthetic_planned_unverified",
            })
    blob = json.dumps(sources, sort_keys=True, ensure_ascii=False).encode()
    digest = hashlib.sha256(blob).hexdigest()
    pack = {
        "schema_version": 1, "set_id": "long-context-ir753-draft-v1",
        "label_status": "draft_unreviewed", "labelled_by": [],
        "families": list(FAMILIES), "min_family_cases": 10,
        "rubric_version": 1,
        "corpus": {"snapshot_id": "ir753-synthetic-plan-v1",
                   "paper_set_sha256": digest, "source_kind": "synthetic_planned",
                   "source": "sources.json", "ingested": False},
        "partition_method": "Distinct synthetic source and theme per case; D01-D06 development, H07-H10 held out.",
        "shared_allowed": [], "conversations": conversations,
    }
    return sources, pack


if __name__ == "__main__":
    sources, pack = build()
    for name, value in (("sources.json", sources), ("conversation_set_v1.json", pack)):
        (ROOT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n",
                                 encoding="utf-8")
