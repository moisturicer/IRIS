"""Review packets: what one human reviewer may see of a collected run (IR-607).

Pure. The caller supplies the record ids the reviewer can read now and each
one's active source revision. A turn resting on anything else, cited or only
read, is withheld whole, question included, since its answer may quote it.
Diagnostics, usage, saved Turns and other reviewers' verdicts never enter.

A written packet is a plaintext snapshot, not access control: whoever holds
the file can read what it holds. `reauthorize` is the re-check an honest
holder runs before reading, by the opening account's access and the sources'
current revisions (IR-721).
"""

from __future__ import annotations

from typing import Iterable, Mapping, Optional

from .conversation_scoring import EXPLICIT, NOT_REVIEWED

CITATION_FIELDS = ("marker", "record_id", "record_title", "page", "text")


def cited_ids(run: Mapping) -> set[int]:
    """Every Record a run's turns rest on: cited, or read without a citation."""
    return {rid for row in run.get("conversations", ()) for t in row.get("turns", ())
            for rid in _run_turn_ids(t)}


def _run_turn_ids(turn: Mapping) -> set[int]:
    return {rid for rid in (*(turn.get("citation_record_ids") or ()),
                            *(turn.get("source_ids") or ())) if rid is not None}


def _withheld(turn: Mapping) -> dict:
    """A turn shown as present but empty: nothing it said or asked survives."""
    return {"number": turn.get("number"), "question": None, "outcome": turn.get("outcome"),
            "answer": None, "citations": [], "withheld": True}


def _turn(turn: Mapping, readable: set[int],
          revisions: Mapping[int, Optional[int]]) -> tuple[dict, set[int]]:
    answer = turn.get("public_answer") or {}
    ids = _run_turn_ids(turn)
    if ids - readable:
        return _withheld(turn), set()
    citations = [{k: c.get(k) for k in CITATION_FIELDS}
                 for c in answer.get("citations") or ()]
    # `record_ids` and `revisions` let a packet opened later be judged again without
    # the run file (IR-721).
    return {"number": turn.get("number"), "question": turn.get("question"),
            "outcome": turn.get("outcome"),
            "answer": answer.get("answer") or answer.get("message"), "citations": citations,
            "record_ids": sorted(ids),
            "revisions": {str(rid): revisions.get(rid) for rid in sorted(ids)},
            "withheld": False}, ids


def packet_ids(bundle: Mapping) -> set[int]:
    """Every Record a written packet's shown turns rest on, for the access check at opening."""
    return {rid for packet in bundle.get("packets", ()) for turn in packet.get("turns", ())
            if not turn.get("withheld") for rid in _turn_ids(turn)}


def _turn_ids(turn: Mapping) -> set[int]:
    # A packet written before `record_ids` existed still names its citations.
    cited = {c.get("record_id") for c in turn.get("citations") or ()}
    return {rid for rid in set(turn.get("record_ids") or ()) | cited if rid is not None}


def _replaced(turn: Mapping, current: Mapping[int, Optional[int]]) -> bool:
    """A source read at another revision than its current one. A packet written
    before `revisions` existed records none and is judged by access alone."""
    recorded = turn.get("revisions")
    if not isinstance(recorded, Mapping):
        return False
    return any(current.get(int(rid)) != rev for rid, rev in recorded.items())


def _own_review(review: Mapping, reviewer: str, authorized: set[int], conversation, arm,
                rubric) -> dict:
    """The review a reopened packet carries for `reviewer`. Another reviewer's work never
    passes to a new holder; the same reviewer keeps only judgments on what is still shown."""
    if not review or review.get("reviewer") != reviewer:
        return template(conversation, arm, reviewer, rubric)
    claims = [c for c in review.get("claims") or () if c.get("record_id") in authorized]
    evidence = [r for r in review.get("evidence_record_ids") or () if r in authorized]
    return {**review, "claims": claims, "evidence_record_ids": evidence}


def reauthorize(bundle: Mapping, *, readable: Iterable[int], reviewer: str,
                revisions: Optional[Mapping[int, Optional[int]]] = None) -> dict:
    """A written packet, opened again by `reviewer`, whose account may read only `readable`.

    Pure. Each turn is judged by that account's current access and, where the packet
    recorded them, by its sources' current revisions; a turn resting on anything
    unreadable or replaced is withheld whole. A withheld turn stays withheld, since its
    text is gone and a later grant of access must not bring it back from the file. This
    is a re-check for an honest holder: the file itself is plaintext.
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


def template(conversation: str, arm: str, reviewer: str, rubric_version) -> dict:
    return {"conversation": conversation, "arm": arm, "reviewer": reviewer,
            "reviewer_kind": "human", "role": "independent", "rubric_version": rubric_version,
            "status": NOT_REVIEWED, "task_completion": None, "pair_usefulness": None,
            "claims": [], "evidence_record_ids": [], "presentation_leak": None,
            "no_answer": None,
            **{field: None for field in EXPLICIT}}


def build_packets(run: Mapping, *, reviewer: str, readable: Iterable[int],
                  revisions: Optional[Mapping[int, Optional[int]]] = None) -> dict:
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
    return {"run_id": run.get("run_id"), "arm": arm, "reviewer": reviewer,
            "rubric_version": rubric, "packets": packets}
