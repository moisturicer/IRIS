"""The IR-598 conversation set: schema, leakage, coverage and locks.

Pure: no database, no file I/O, no vendor. A set is authored by people and
validated here before any model is scored against it. Development and
held-out conversations share no paper and no topic unless the set names the
overlap and says why. Locks pin each split's content by digest, so a case
moved or edited after seeing output is detectable.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from typing import Any, Mapping

from .conversation_scoring import TARGETS

SCHEMA_VERSION = 1
FAMILIES = tuple(f"A{i:02d}" for i in range(1, 16))
SPLITS = ("development", "held_out")
LABEL_STATUSES = ("draft_unreviewed", "human_reviewed")
DEFAULT_MIN_CONVERSATIONS = 100
RUBRIC_VERSION = 1
#: A09's three outcomes must stay distinct before a lock is written (IR-607).
A09_CASES = ("missing_field", "no_match", "outage")
TURN_FIELDS = ("user", "intended_task", "expected_pair", "required_evidence",
               "clarification_necessary", "acceptable_uncertainty")
CONVERSATION_FIELDS = ("id", "family", "split", "topic", "papers",
                       "supported_unambiguous", "turns")


def _norm(text: Any) -> str:
    return " ".join(str(text).lower().split())


def _digest(value: Any) -> str:
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def split_digests(data: Mapping[str, Any]) -> dict[str, str]:
    """SHA-256 of each split's conversations (ids and content), order-independent."""
    out = {}
    for split in SPLITS:
        rows = sorted((c for c in data.get("conversations", ()) if c.get("split") == split),
                      key=lambda c: str(c.get("id")))
        out[split] = _digest(rows)
    return out


def lock_record(data: Mapping[str, Any]) -> dict[str, Any]:
    digests = split_digests(data)
    return {"set_id": data.get("set_id"), "development": digests["development"],
            "held_out": digests["held_out"], "corpus": _digest(data.get("corpus")),
            "rubric_version": data.get("rubric_version", RUBRIC_VERSION),
            "thresholds": dict(TARGETS)}


LOCK_KEYS = ("set_id", "development", "held_out", "corpus", "rubric_version")


def check_lock(data: Mapping[str, Any], lock: Mapping[str, Any]) -> list[str]:
    """Names of the lock entries the current set no longer matches.

    A lock written before IR-607 pinned no corpus or rubric, so it is stale.
    """
    current = lock_record(data)
    return [key for key in LOCK_KEYS if current[key] != lock.get(key)]


def postdates_lock(stamp: Any, lock: Mapping[str, Any]) -> bool:
    """Was output stamped after the lock froze its prompts and rubric?"""
    try:
        froze = datetime.fromisoformat(lock["locked_at"])
        made = datetime.fromisoformat(stamp)
        return froze.tzinfo is not None and made.tzinfo is not None and made >= froze
    except (KeyError, TypeError, ValueError):
        return False


LABEL_CHECKS =("category_names", "exact_counts", "paper_page_facts", "supported_unambiguous")
LABEL_REVIEWED = ("confirmed", "corrected")


def check_label_review(data: Mapping[str, Any], review: Mapping[str, Any]) -> list[str]:
    """Problems that stop a named label review from covering this set version."""
    problems = []
    reviewer = str(review.get("reviewer") or "").strip()
    if not reviewer:
        problems.append("label review needs a named reviewer")
    elif reviewer not in data.get("labelled_by", ()):
        problems.append(f"label reviewer {reviewer!r} is not in the set's labelled_by")
    if review.get("set_id") != data.get("set_id"):
        problems.append("label review is for another set_id")
    if review.get("set_digests") != split_digests(data):
        problems.append("label review digests do not match this set version")
    if _digest(review.get("corpus")) != _digest(data.get("corpus")):
        problems.append("label review was made against another corpus snapshot")
    entries = review.get("conversations") or {}
    for c in data.get("conversations", ()):
        cid = c.get("id")
        entry = entries.get(cid)
        if entry is None:
            problems.append(f"{cid}: not in the label review")
            continue
        if entry.get("status") not in LABEL_REVIEWED:
            problems.append(f"{cid}: label status {entry.get('status')!r}, not reviewed")
            continue
        checks = entry.get("checks") or {}
        for name in LABEL_CHECKS:
            if checks.get(name) not in (True, "not_applicable"):
                problems.append(f"{cid}: {name} not confirmed")
    return problems


def _check_turns(conv: Mapping[str, Any], errors: list[str]) -> None:
    cid = conv.get("id")
    turns = conv.get("turns")
    if not turns:
        errors.append(f"{cid}: no turns")
        return
    for n, turn in enumerate(turns, 1):
        for field in TURN_FIELDS:
            if field not in turn:
                errors.append(f"{cid} turn {n}: missing {field}")


STOPWORDS = frozenset(
    "about after also and are between from into over that their them then these this "
    "through under using with within without".split())


def _words(topic: Any) -> set[str]:
    cleaned = "".join(ch if ch.isalnum() else " " for ch in _norm(topic))
    return {w for w in cleaned.split() if len(w) >= 4 and w not in STOPWORDS}


def _titles(conv: Mapping[str, Any]) -> set[str]:
    """Every paper a conversation touches: its list, pairs and evidence."""
    titles = list(conv.get("papers", ()))
    for turn in conv.get("turns") or ():
        titles += turn.get("expected_pair") or []
        titles += [e["title"] for e in turn.get("required_evidence") or ()
                   if isinstance(e, dict) and e.get("title")]
    return {_norm(t) for t in titles}


def _topic_overlaps(conversations) -> list[dict]:
    topics = {split: {} for split in SPLITS}
    for c in conversations:
        if c.get("split") in SPLITS and c.get("topic"):
            topics[c["split"]].setdefault(_norm(c["topic"]), []).append(c.get("id"))
    out = []
    for dev, dev_ids in topics["development"].items():
        for held, held_ids in topics["held_out"].items():
            shared = _words(dev) & _words(held)
            if shared and dev != held:
                out.append({"development_topic": dev, "held_out_topic": held,
                            "words": sorted(shared), "development": dev_ids,
                            "held_out": held_ids})
    return out


def _leakage(conversations, allowed):
    seen = {split: {"paper": {}, "topic": {}} for split in SPLITS}
    for c in conversations:
        if c.get("split") not in SPLITS:
            continue
        bucket = seen[c["split"]]
        bucket["topic"].setdefault(_norm(c.get("topic", "")), []).append(c.get("id"))
        for title in _titles(c):
            bucket["paper"].setdefault(title, []).append(c.get("id"))
    permitted = {(a.get("kind"), _norm(a.get("value", ""))): a for a in allowed}
    leaks, shared = [], []
    for kind in ("paper", "topic"):
        for value in sorted(set(seen["development"][kind]) & set(seen["held_out"][kind])):
            row = {"kind": kind, "value": value,
                   "development": seen["development"][kind][value],
                   "held_out": seen["held_out"][kind][value]}
            entry = permitted.get((kind, value))
            if entry and str(entry.get("reason", "")).strip():
                shared.append({**row, "reason": entry["reason"]})
            else:
                leaks.append(row)
    return leaks, shared


def validate_set(data: Mapping[str, Any], *, min_conversations: int = DEFAULT_MIN_CONVERSATIONS) -> dict:
    errors: list[str] = []
    conversations = list(data.get("conversations", ()))
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not data.get("set_id"):
        errors.append("set_id is required")
    status = data.get("label_status")
    if status not in LABEL_STATUSES:
        errors.append(f"label_status must be one of {LABEL_STATUSES}")
    if status == "human_reviewed" and not data.get("labelled_by"):
        errors.append("label_status human_reviewed requires labelled_by")
    if not data.get("corpus"):
        errors.append("corpus snapshot reference is required")

    allowed = list(data.get("shared_allowed", ()))
    for entry in allowed:
        if not str(entry.get("reason", "")).strip():
            errors.append(f"shared_allowed {entry.get('value')!r}: a reason is required")

    ids = Counter(c["id"] for c in conversations if c.get("id") not in (None, ""))
    for c in conversations:
        if c.get("id") in (None, ""):
            errors.append(f"conversation without an id (topic {c.get('topic')!r})")
    for cid, n in ids.items():
        if n > 1:
            errors.append(f"duplicate id {cid}")
    counts = {split: {f: 0 for f in FAMILIES} for split in SPLITS}
    for c in conversations:
        for field in CONVERSATION_FIELDS:
            if field not in c:
                errors.append(f"{c.get('id')}: missing {field}")
        if c.get("family") not in FAMILIES:
            errors.append(f"{c.get('id')}: unknown family {c.get('family')}")
        if c.get("split") not in SPLITS:
            errors.append(f"{c.get('id')}: unknown split {c.get('split')!r}")
        if c.get("family") in FAMILIES and c.get("split") in SPLITS:
            counts[c["split"]][c["family"]] += 1
        _check_turns(c, errors)
        if "a09_case" in c and c["a09_case"] not in A09_CASES:
            errors.append(f"{c.get('id')}: a09_case {c['a09_case']!r} is not one of {A09_CASES}")

    a09 = [c for c in conversations if c.get("family") == "A09"]
    absent = [case for case in A09_CASES if case not in {c.get("a09_case") for c in a09}]
    lock_blockers = ([f"A09 lacks distinct {', '.join(absent)} cases"] if a09 and absent else [])
    leaks, shared = _leakage(conversations, allowed)
    for leak in leaks:
        errors.append(f"leakage: {leak['kind']} {leak['value']!r} in both splits")
    gaps = [f for f in FAMILIES
            if not any(counts[s][f] for s in SPLITS)]
    held_gaps = [f for f in FAMILIES if not counts["held_out"][f]]
    if len(conversations) < min_conversations:
        errors.append(f"fewer than {min_conversations} conversations ({len(conversations)})")
    return {
        "set_id": data.get("set_id"), "label_status": status,
        "labelled_by": list(data.get("labelled_by", ())),
        "total": len(conversations), "counts": counts,
        "supported_unambiguous": sum(bool(c.get("supported_unambiguous")) for c in conversations),
        "leakage": leaks, "allowed_shared": shared,
        "coverage_gaps": gaps, "held_out_coverage_gaps": held_gaps,
        "digests": split_digests(data), "errors": errors, "lock_blockers": lock_blockers,
        "warnings": [{"kind": "topic_overlap", **o} for o in _topic_overlaps(conversations)],
        "ready": not errors and not gaps,
        "ok": not errors,
    }
