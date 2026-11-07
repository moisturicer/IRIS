"""Review packets: what one human reviewer may see of a collected run (IR-607, IR-721).

Pure. A packet holds **no text**: no question, answer, title or quotation, only
which turns a reviewer may see, the Records and source revisions each rests on,
citation markers and pages, and a blank review template. Copying the file
reveals nothing a reader could not already name.

The text is rendered only on demand, by `render`, from the run file the packet
was built from (pinned by its SHA-256), after the opening account's access and
each source's current revision are checked again by `reauthorize`. A turn
resting on anything unreadable or replaced, cited or only read, is withheld
whole and is never rendered again. Diagnostics, usage, saved Turns and other
reviewers' verdicts never enter.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Optional

from .conversation_scoring import EXPLICIT, NOT_REVIEWED

#: What a packet keeps of a citation: where it points, never what it says.
CITATION_FIELDS = ("marker", "record_id", "page")
TEXT_NOT_STORED = ("not stored: render it with eval_review_packets --show, which checks the "
                   "opening account's access first")


class PacketRefused(ValueError):
    """The run file is not the one the packet was built from."""


def cited_ids(run: Mapping) -> set[int]:
    """Every Record a run's turns rest on: cited, or read without a citation."""
    return {rid for row in run.get("conversations", ()) for t in row.get("turns", ())
            for rid in _run_turn_ids(t)}


def _run_turn_ids(turn: Mapping) -> set[int]:
    return {rid for rid in (*(turn.get("citation_record_ids") or ()),
                            *(turn.get("source_ids") or ())) if rid is not None}


def _withheld(turn: Mapping) -> dict:
    return {"number": turn.get("number"), "outcome": turn.get("outcome"), "citations": [],
            "withheld": True}


def _turn(turn: Mapping, readable: set[int],
          revisions: Mapping[int, Optional[int]]) -> tuple[dict, set[int]]:
    answer = turn.get("public_answer") or {}
    ids = _run_turn_ids(turn)
    if ids - readable:
        return _withheld(turn), set()
    citations = [{k: c.get(k) for k in CITATION_FIELDS} for c in answer.get("citations") or ()]
    return {"number": turn.get("number"), "outcome": turn.get("outcome"),
            "citations": citations, "record_ids": sorted(ids),
            "revisions": {str(rid): revisions.get(rid) for rid in sorted(ids)},
            "withheld": False}, ids


def packet_ids(bundle: Mapping) -> set[int]:
    """Every Record a written packet's shown turns rest on, for the access check at opening."""
    return {rid for packet in bundle.get("packets", ()) for turn in packet.get("turns", ())
            if not turn.get("withheld") for rid in _turn_ids(turn)}


def _turn_ids(turn: Mapping) -> set[int]:
    cited = {c.get("record_id") for c in turn.get("citations") or ()}
    return {rid for rid in set(turn.get("record_ids") or ()) | cited if rid is not None}


def _replaced(turn: Mapping, current: Mapping[int, Optional[int]]) -> bool:
    """A source read at another revision than its current one."""
    recorded = turn.get("revisions")
    if not isinstance(recorded, Mapping):
        return True                     # no recorded revisions: nothing to judge it by
    return any(current.get(int(rid)) != rev for rid, rev in recorded.items())


def _own_review(review: Mapping, reviewer: str, authorized: set[int], conversation, arm,
                rubric) -> dict:
    """Another reviewer's work never passes to a new holder; the same reviewer keeps only
    judgments on what is still shown."""
    if not review or review.get("reviewer") != reviewer:
        return template(conversation, arm, reviewer, rubric)
    claims = [c for c in review.get("claims") or () if c.get("record_id") in authorized]
    evidence = [r for r in review.get("evidence_record_ids") or () if r in authorized]
    return {**review, "claims": claims, "evidence_record_ids": evidence}


def reauthorize(bundle: Mapping, *, readable: Iterable[int], reviewer: str,
                revisions: Optional[Mapping[int, Optional[int]]] = None) -> dict:
    """A packet judged again for `reviewer`, whose account may read only `readable` now.

    Each shown turn needs every Record it rests on readable and at the revision the packet
    recorded; otherwise it is withheld, and a withheld turn stays withheld.
    """
    readable = set(readable)
    current = dict(revisions or {})
    packets = []
    for packet in bundle.get("packets", ()):
        turns, authorized = [], set()
        for turn in packet.get("turns", ()):
            ids = _turn_ids(turn)
            if turn.get("withheld") or ids - readable or _replaced(turn, current):
                turns.append(_withheld(turn))
            else:
                turns.append(dict(turn))
                authorized |= ids
        review = _own_review(packet.get("review") or {}, reviewer, authorized,
                             packet.get("conversation"), bundle.get("arm"),
                             bundle.get("rubric_version"))
        packets.append({**packet, "turns": turns, "authorized_record_ids": sorted(authorized),
                        "review": review})
    return {**bundle, "reviewer": reviewer, "packets": packets}


def render(bundle: Mapping, run: Mapping, run_sha256: str, *, readable: Iterable[int],
           revisions: Mapping[int, Optional[int]]) -> list[dict]:
    """The text of every turn `bundle` (already reauthorized) still shows, from `run`.

    Refuses a run file other than the one the packet pins. A turn's dependencies are read
    again from the run file, not from the packet, so editing a packet's references cannot
    unlock a turn: each must be readable now and at the revision the packet recorded.
    Withheld turns render nothing.
    """
    readable = set(readable)
    if run_sha256 != bundle.get("run_sha256"):
        raise PacketRefused("the run file is not the one this packet was built from "
                            "(run_sha256 differs)")
    rows = {row.get("id"): row for row in run.get("conversations", ())}
    shown = []
    for packet in bundle.get("packets", ()):
        source = {t.get("number"): t for t in (rows.get(packet.get("conversation")) or {})
                  .get("turns", ())}
        turns = []
        for turn in packet.get("turns", ()):
            if turn.get("withheld"):
                turns.append({"number": turn.get("number"), "withheld": True})
                continue
            original = source.get(turn.get("number")) or {}
            recorded = turn.get("revisions") if isinstance(turn.get("revisions"), Mapping) else {}
            needs = _run_turn_ids(original)
            if (not original or needs - readable
                    or any(str(rid) not in recorded or recorded[str(rid)] != revisions.get(rid)
                           for rid in needs)):
                turns.append({"number": turn.get("number"), "withheld": True})
                continue
            answer = original.get("public_answer") or {}
            turns.append({
                "number": turn.get("number"), "withheld": False,
                "question": original.get("question"),
                "answer": answer.get("answer") or answer.get("message"),
                "citations": [{k: c.get(k) for k in ("marker", "record_id", "record_title",
                                                     "page", "text")}
                              for c in answer.get("citations") or ()]})
        shown.append({"conversation": packet.get("conversation"), "turns": turns})
    return shown


def template(conversation: str, arm: str, reviewer: str, rubric_version) -> dict:
    return {"conversation": conversation, "arm": arm, "reviewer": reviewer,
            "reviewer_kind": "human", "role": "independent", "rubric_version": rubric_version,
            "status": NOT_REVIEWED, "task_completion": None, "pair_usefulness": None,
            "claims": [], "evidence_record_ids": [], "presentation_leak": None,
            "no_answer": None,
            **{field: None for field in EXPLICIT}}


def build_packets(run: Mapping, *, reviewer: str, readable: Iterable[int],
                  revisions: Optional[Mapping[int, Optional[int]]] = None,
                  run_sha256: Optional[str] = None) -> dict:
    readable = set(readable)
    revisions = dict(revisions or {})
    arm = run.get("arm")
    rubric = (run.get("manifest") or {}).get("rubric_version")
    packets = []
    for row in run.get("conversations", ()):
        turns, authorized = [], set()
        for turn in row.get("turns", ()):
            shown, ids = _turn(turn, readable, revisions)
            turns.append(shown)
            authorized |= ids
        packets.append({"conversation": row["id"], "family": row.get("family"),
                        "turns": turns, "authorized_record_ids": sorted(authorized),
                        "review": template(row["id"], arm, reviewer, rubric)})
    return {"run_id": run.get("run_id"), "run_sha256": run_sha256, "arm": arm,
            "reviewer": reviewer, "rubric_version": rubric, "text": TEXT_NOT_STORED,
            "packets": packets}
