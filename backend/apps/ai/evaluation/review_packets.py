"""Review packets: what one human reviewer may see of a collected run (IR-607).

Pure. The caller supplies the record ids the reviewer can read now. A turn
citing anything else is withheld whole, since its answer may quote it.
Diagnostics, usage, saved Turns and other reviewers' verdicts never enter.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from .conversation_scoring import EXPLICIT, NOT_REVIEWED

CITATION_FIELDS = ("marker", "record_id", "record_title", "page", "text")


def cited_ids(run: Mapping) -> set[int]:
    return {rid for row in run.get("conversations", ()) for t in row.get("turns", ())
            for rid in t.get("citation_record_ids") or ()}


def _turn(turn: Mapping, readable: set[int]) -> tuple[dict, set[int]]:
    answer = turn.get("public_answer") or {}
    ids = set(turn.get("citation_record_ids") or ())
    shown = {"number": turn.get("number"), "question": turn.get("question"),
             "outcome": turn.get("outcome")}
    if ids - readable:
        return {**shown, "answer": None, "citations": [], "withheld": True}, set()
    citations = [{k: c.get(k) for k in CITATION_FIELDS}
                 for c in answer.get("citations") or ()]
    return {**shown, "answer": answer.get("answer") or answer.get("message"),
            "citations": citations, "withheld": False}, ids


def template(conversation: str, arm: str, reviewer: str, rubric_version) -> dict:
    return {"conversation": conversation, "arm": arm, "reviewer": reviewer,
            "reviewer_kind": "human", "role": "independent", "rubric_version": rubric_version,
            "status": NOT_REVIEWED, "task_completion": None, "pair_usefulness": None,
            "claims": [], "evidence_record_ids": [], "presentation_leak": None,
            "no_answer": None,
            **{field: None for field in EXPLICIT}}


def build_packets(run: Mapping, *, reviewer: str, readable: Iterable[int]) -> dict:
    readable = set(readable)
    arm = run.get("arm")
    rubric = (run.get("manifest") or {}).get("rubric_version")
    packets = []
    for row in run.get("conversations", ()):
        turns, authorized = [], set()
        for turn in row.get("turns", ()):
            shown, ids = _turn(turn, readable)
            turns.append(shown)
            authorized |= ids
        packets.append({"conversation": row["id"], "family": row.get("family"),
                        "turns": turns, "authorized_record_ids": sorted(authorized),
                        "review": template(row["id"], arm, reviewer, rubric)})
    return {"run_id": run.get("run_id"), "arm": arm, "reviewer": reviewer,
            "rubric_version": rubric, "packets": packets}
