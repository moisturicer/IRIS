"""Scoring conversational task success from human reviews (IR-598).

Pure: no database and no vendor. Every metric owns its numerator and
denominator and carries a 95% Wilson interval; nothing is blended into one
score and a family with too few examples is INCONCLUSIVE. Targets are the
owner-review proposals of the evaluation README, never approved gates. Any
access breach blocks enablement whatever else the numbers say.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Mapping, Optional, Sequence

from .capacity import percentile

ARMS = ("current", "fixed_synthesis", "controller")
MODES = ("architecture", "model")
DEFAULT_MIN_EXAMPLES = 10
Z = 1.96

TARGET_LABEL = "proposed owner-review target — not an approved release gate"
TARGETS = {"task_completion": 0.90, "claim_support": 0.95, "citation_support": 0.95}

COMPLETION = ("yes", "partial", "no")
PAIR = ("useful", "weak", "wrong", "na")
PREFERENCES = ("candidate", "baseline", "tie")
CONDITION_KEYS = ("corpus_snapshot_digest", "model_ids", "data_policy", "limits")

ZERO_BREACH_NOTE = ("Zero observed breaches is limited by the suite size and "
                    "does not prove absence of risk.")
FAKE_NOTE = ("fake providers: contract check only, never quality evidence")


class ScoringError(ValueError):
    """The inputs cannot be scored honestly: say why."""


def wilson(successes: int, total: int, z: float = Z) -> tuple[Optional[float], Optional[float]]:
    if not total:
        return (None, None)
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _frac(numerator: int, denominator: int) -> dict:
    low, high = wilson(numerator, denominator)
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None,
            "wilson_low": low, "wilson_high": high}


def _target(frac: Mapping, target: float) -> dict:
    low, high = frac["wilson_low"], frac["wilson_high"]
    if low is None:
        status = "inconclusive"
    elif low >= target:
        status = "met"
    elif high < target:
        status = "not_met"
    else:
        status = "inconclusive"
    return {"target": target, "label": TARGET_LABEL, "status": status, **frac}


def _validate_review(r: Mapping, known: set[str]) -> None:
    if not str(r.get("reviewer") or "").strip():
        raise ScoringError(f"{r.get('conversation')}: a named reviewer is required")
    if r.get("rubric_version") in (None, ""):
        raise ScoringError(f"{r.get('conversation')}: rubric_version is required")
    if r.get("conversation") not in known:
        raise ScoringError(f"{r.get('conversation')}: conversation is not in the set")
    if r.get("task_completion") not in COMPLETION:
        raise ScoringError(f"{r['conversation']}: task_completion must be one of {COMPLETION}")
    if r.get("pair_usefulness") not in PAIR:
        raise ScoringError(f"{r['conversation']}: pair_usefulness must be one of {PAIR}")


def _metrics(reviews: Sequence[Mapping], supported: set[str]) -> dict:
    tasks = [r for r in reviews if r["conversation"] in supported]
    pairs = [r for r in reviews if r["pair_usefulness"] != "na"]
    claims = [c for r in reviews for c in r.get("claims", ())]
    pages = [c for c in claims if c.get("page_correct") is not None]
    return {
        "reviewed": len(reviews),
        "task_completion": _frac(sum(r["task_completion"] == "yes" for r in tasks), len(tasks)),
        "partial": _frac(sum(r["task_completion"] == "partial" for r in tasks), len(tasks)),
        "pair_usefulness": _frac(sum(r["pair_usefulness"] == "useful" for r in pairs), len(pairs)),
        "unnecessary_clarification": _frac(
            sum(bool(r.get("unnecessary_clarification")) for r in reviews), len(reviews)),
        "claim_support": _frac(sum(bool(c.get("supported")) for c in claims), len(claims)),
        "citation_support": _frac(sum(bool(c.get("citation_correct")) for c in claims), len(claims)),
        "page_support": _frac(sum(bool(c["page_correct"]) for c in pages), len(pages)),
        "presentation_leaks": sum(bool(r.get("presentation_leak")) for r in reviews),
        "no_answer": sum(bool(r.get("no_answer")) for r in reviews),
    }


def score_reviews(data: Mapping[str, Any], reviews: Sequence[Mapping], *, arm: str,
                  min_examples: int = DEFAULT_MIN_EXAMPLES) -> dict:
    conversations = {c["id"]: c for c in data["conversations"]}
    supported = {cid for cid, c in conversations.items() if c.get("supported_unambiguous")}
    mine = [r for r in reviews if r.get("arm") == arm]
    seen = set()
    for r in mine:
        _validate_review(r, set(conversations))
        if r["conversation"] in seen:
            raise ScoringError(f"{r['conversation']}: duplicate review for arm {arm}; adjudicate first")
        seen.add(r["conversation"])

    families = {}
    for family in sorted({c["family"] for c in conversations.values()}):
        rows = [r for r in mine if conversations[r["conversation"]]["family"] == family]
        entry = _metrics(rows, supported)
        entry["status"] = "INCONCLUSIVE" if len(rows) < min_examples else "reported"
        families[family] = entry
    overall = _metrics(mine, supported)
    breaches = sorted(r["conversation"] for r in mine if r.get("access_breach"))
    return {
        "arm": arm, "min_examples": min_examples,
        "reviewers": sorted({r["reviewer"] for r in mine}),
        "rubric_versions": sorted({str(r["rubric_version"]) for r in mine}),
        "families": families, "overall": overall,
        "targets": {k: _target(overall[k], t) for k, t in TARGETS.items()},
        "enablement_blocked": bool(breaches),
        "access_breaches": {
            "count": len(breaches), "conversations": breaches, "suite_size": len(mine),
            "note": ZERO_BREACH_NOTE if not breaches else
            "Any access breach blocks enablement regardless of other numbers."},
    }


def check_conditions(runs: Mapping[str, Mapping], *, mode: str) -> None:
    """Refuse a comparison whose arms did not run under equal conditions."""
    if mode not in MODES:
        raise ScoringError(f"mode must be one of {MODES}")
    if len(runs) < 2:
        raise ScoringError("a comparison needs at least two runs")
    arms = [r.get("arm") for r in runs.values()]
    if mode == "architecture":
        if len(set(arms)) != len(arms) or any(a not in ARMS for a in arms):
            raise ScoringError(f"architecture mode needs distinct arms from {ARMS}")
        keys = CONDITION_KEYS
    else:
        if len(set(arms)) != 1:
            raise ScoringError("model comparison needs the same architecture in every run")
        keys = tuple(k for k in CONDITION_KEYS if k != "model_ids")
    manifests = [r.get("manifest", {}) for r in runs.values()]
    for key in keys:
        if any(m.get(key) is None for m in manifests):
            raise ScoringError(f"manifest lacks {key}")
        if any(m[key] != manifests[0][key] for m in manifests):
            raise ScoringError(f"arms differ in {key}; conditions are not equal")


def preference(records: Sequence[Mapping]) -> dict:
    for r in records:
        if r.get("blinded") is not True:
            raise ScoringError(f"{r.get('conversation')}: unblinded preference records are refused")
        if not str(r.get("reviewer") or "").strip():
            raise ScoringError(f"{r.get('conversation')}: a named reviewer is required")
        if r.get("preferred") not in PREFERENCES:
            raise ScoringError(f"{r.get('conversation')}: preferred must be one of {PREFERENCES}")
    tally = Counter(r["preferred"] for r in records)
    wins, losses, ties = tally["candidate"], tally["baseline"], tally["tie"]
    n = wins + losses
    tail = sum(math.comb(n, k) for k in range(min(wins, losses) + 1)) / 2 ** n if n else None
    return {"wins": wins, "losses": losses, "ties": ties, "denominator": len(records),
            "decisive": n, "p_value": min(1.0, 2 * tail) if tail is not None else None,
            "test": "exact two-sided sign test, ties excluded"}


def calibrate_judge(items: Sequence[Mapping], *, adjudication: Optional[Mapping] = None) -> dict:
    if not items:
        raise ScoringError("no judge items")
    for i in items:
        if not str(i.get("human_reviewer") or "").strip():
            raise ScoringError(f"{i.get('item')}: a named human reviewer is required")
    n = len(items)
    agree = sum(i["judge"] == i["human"] for i in items)
    judge, human = Counter(i["judge"] for i in items), Counter(i["human"] for i in items)
    expected = sum(judge[c] / n * human[c] / n for c in set(judge) | set(human))
    kappa = None if expected == 1 else (agree / n - expected) / (1 - expected)
    labels = sorted(set(judge) | set(human))
    confusion = {j: {h: sum(1 for i in items if i["judge"] == j and i["human"] == h)
                     for h in labels} for j in labels}
    reviewers = sorted({i["human_reviewer"] for i in items})
    adjudicated = bool(adjudication and str(adjudication.get("by") or "").strip())
    return {
        "n": n, "agreement": agree / n, "kappa": kappa, "confusion": confusion,
        "human_reviewers": reviewers, "adjudication": dict(adjudication) if adjudication else None,
        "institutional_claim_allowed": len(reviewers) >= 2 and adjudicated,
    }


def _group(rows: Sequence[Mapping]) -> dict:
    latencies = [r["latency_seconds"] for r in rows]
    wins = [r for r in rows if r.get("success")]
    spent = sum(r.get("cost", 0) or 0 for r in rows)
    out = {"n": len(rows), "successes": len(wins),
           "p50": percentile(latencies, 0.5), "p95": percentile(latencies, 0.95),
           "total_cost": spent,
           "cost_per_successful_task": spent / len(wins) if wins else None}
    if not wins:
        out["note"] = "cost per successful task is undefined: no successful tasks"
    return out


def cost_latency(run: Mapping) -> dict:
    """Queue-inclusive latency and cost, cold and warm apart."""
    rows = run.get("conversations", ())
    fake = run.get("providers") != "real"
    reasons = []
    if fake:
        reasons.append("providers were not real")
    if run.get("capacity_fit") is not True:
        reasons.append("the burst did not fit the approved budget")
    return {
        "arm": run.get("arm"),
        "cold": _group([r for r in rows if r.get("cache") == "cold"]),
        "warm": _group([r for r in rows if r.get("cache") == "warm"]),
        "capacity": "unverified" if reasons else "verified",
        "capacity_reason": "; ".join(reasons) or None,
        "evidence": FAKE_NOTE if fake else "real providers",
    }
