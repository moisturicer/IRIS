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
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1
FAMILIES = tuple(f"A{i:02d}" for i in range(1, 16))
SPLITS = ("development", "held_out")
LABEL_STATUSES = ("draft_unreviewed", "human_reviewed")
DEFAULT_MIN_CONVERSATIONS = 100
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


def lock_record(data: Mapping[str, Any]) -> dict[str, str]:
    digests = split_digests(data)
    return {"set_id": data.get("set_id"), "development": digests["development"],
            "held_out": digests["held_out"]}


def check_lock(data: Mapping[str, Any], lock: Mapping[str, Any]) -> list[str]:
    """Names of the lock entries the current set no longer matches."""
    current = lock_record(data)
    return [key for key in ("set_id", "development", "held_out")
            if current[key] != lock.get(key)]


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


def _leakage(conversations, allowed):
    seen = {split: {"paper": {}, "topic": {}} for split in SPLITS}
    for c in conversations:
        if c.get("split") not in SPLITS:
            continue
        bucket = seen[c["split"]]
        bucket["topic"].setdefault(_norm(c.get("topic", "")), []).append(c["id"])
        for title in c.get("papers", ()):
            bucket["paper"].setdefault(_norm(title), []).append(c["id"])
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

    ids = Counter(c.get("id") for c in conversations)
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
        "digests": split_digests(data), "errors": errors,
        "ready": not errors and not gaps,
        "ok": not errors,
    }
