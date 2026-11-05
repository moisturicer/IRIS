"""Review packets: what one human reviewer may see of a collected run (IR-607).

Pure. The caller supplies the record ids the reviewer can read now. A turn
citing anything else is withheld whole, since its answer may quote it.
Diagnostics, usage, saved Turns and other reviewers' verdicts never enter.
A written packet is a snapshot, so `reauthorize` judges it again at opening
by the opening account's access (IR-721).
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
    # `record_ids` lets a packet opened later be judged again without the run file (IR-721).
    return {**shown, "answer": answer.get("answer") or answer.get("message"),
            "citations": citations, "record_ids": sorted(ids), "withheld": False}, ids


def packet_ids(bundle: Mapping) -> set[int]:
    """Every Record a written packet's shown turns rest on, for the access check at opening."""
    return {rid for packet in bundle.get("packets", ()) for turn in packet.get("turns", ())
            if not turn.get("withheld") for rid in _turn_ids(turn)}


def _turn_ids(turn: Mapping) -> set[int]:
    # A packet written before `record_ids` existed still names its citations.
    cited = {c.get("record_id") for c in turn.get("citations") or ()}
    return {rid for rid in set(turn.get("record_ids") or ()) | cited if rid is not None}


def reauthorize(bundle: Mapping, *, readable: Iterable[int]) -> dict:
    """A written packet, opened again by an account that may read only `readable` now.

    Pure. A packet is a copy, so holding it proves nothing: each turn is judged by
    the opening account's current access, and a turn resting on anything else is
    withheld whole, as when the packet was built. A withheld turn stays withheld,
    since its text is gone and a later grant of access must not bring it back from
    the file. Reviews, questions and run identity are untouched.
    """
    readable = set(readable)
    packets = []
    for packet in bundle.get("packets", ()):
        turns, authorized = [], set()
        for turn in packet.get("turns", ()):
            ids = _turn_ids(turn)
            if turn.get("withheld") or ids - readable:
                turns.append({"number": turn.get("number"), "question": turn.get("question"),
                              "outcome": turn.get("outcome"), "answer": None, "citations": [],
                              "withheld": True})
            else:
                turns.append(dict(turn))
                authorized |= ids
        packets.append({**packet, "turns": turns, "authorized_record_ids": sorted(authorized)})
    return {**bundle, "packets": packets}


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
