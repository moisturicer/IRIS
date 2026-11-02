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

from .pilot_report import percentile

ARMS = ("current", "fixed_synthesis", "controller")
MODES = ("architecture", "model")
DEFAULT_MIN_EXAMPLES = 10
Z = 1.96

TARGET_LABEL = "proposed owner-review target — not an approved release gate"
TARGETS = {"task_completion": 0.90, "claim_support": 0.95, "citation_support": 0.95,
           "page_support": 0.95}

COMPLETION = ("yes", "partial", "no")
PAIR = ("useful", "weak", "wrong", "na")
PREFERENCES = ("candidate", "baseline", "tie")
ROLES = ("independent", "adjudication")
REVIEWED, NOT_REVIEWED = "reviewed", "not_reviewed"
STATUSES = (REVIEWED, NOT_REVIEWED)
#: Judgments a reviewed record must state rather than leave out (IR-607).
EXPLICIT = ("unnecessary_clarification", "access_breach")
CONDITION_KEYS = ("corpus_snapshot_digest", "model_ids", "data_policy", "limits",
                  "set_digests", "rubric_version")
MIN_CAPACITY_BURST = 100

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


def _require_named(record: Mapping, field: str, label: Any, who: str = "reviewer") -> None:
    if not str(record.get(field) or "").strip():
        raise ScoringError(f"{label}: a named {who} is required")


def _validate_review(r: Mapping, known: set[str]) -> None:
    _require_named(r, "reviewer", r.get("conversation"))
    if r.get("reviewer_kind", "human") != "human":
        raise ScoringError(f"{r.get('conversation')}: only a human reviewer may supply a "
                           f"verdict, not {r.get('reviewer_kind')!r}")
    if r.get("rubric_version") in (None, ""):
        raise ScoringError(f"{r.get('conversation')}: rubric_version is required")
    if r.get("conversation") not in known:
        raise ScoringError(f"{r.get('conversation')}: conversation is not in the set")
    if r.get("role", "independent") not in ROLES:
        raise ScoringError(f"{r['conversation']}: role must be one of {ROLES}")
    if r.get("status", REVIEWED) not in STATUSES:
        raise ScoringError(f"{r['conversation']}: status must be one of {STATUSES}")
    if r.get("status", REVIEWED) == NOT_REVIEWED:
        return
    if r.get("task_completion") not in COMPLETION:
        raise ScoringError(f"{r['conversation']}: task_completion must be one of {COMPLETION}")
    if r.get("pair_usefulness") not in PAIR:
        raise ScoringError(f"{r['conversation']}: pair_usefulness must be one of {PAIR}")
    for field in EXPLICIT:
        if not isinstance(r.get(field), bool):
            raise ScoringError(f"{r['conversation']}: {field} must be stated true or false")
    for claim in r.get("claims", ()):
        if not (isinstance(claim.get("supported"), bool)
                and isinstance(claim.get("citation_correct"), bool)
                and claim.get("page_correct") in (True, False, None)):
            raise ScoringError(f"{r['conversation']}: each claim states supported and "
                               "citation_correct, and page_correct or null")


def _verdict(r: Mapping) -> tuple:
    claims = tuple((bool(c.get("supported")), bool(c.get("citation_correct")),
                    c.get("page_correct")) for c in r.get("claims", ()))
    return (r["task_completion"], r["pair_usefulness"], claims,
            *(bool(r.get(f)) for f in (*EXPLICIT, "presentation_leak", "no_answer")))


def _resolve(cid: str, rows: Sequence[Mapping]) -> tuple[Optional[Mapping], dict]:
    """One verdict per conversation; every original record stays in the audit."""
    independent = [r for r in rows if r.get("role", "independent") == "independent"]
    verdicts = [r for r in rows if r.get("role") == "adjudication"]
    names = [r["reviewer"] for r in independent]
    if len(set(names)) != len(names):
        raise ScoringError(f"{cid}: one person filed two independent reviews")
    if len(verdicts) > 1:
        raise ScoringError(f"{cid}: more than one adjudicated verdict")
    audit = {"reviewers": names, "adjudicated_by": None, "records": [dict(r) for r in rows]}
    done = [r for r in independent if r.get("status", REVIEWED) == REVIEWED]
    if verdicts:
        if len(done) < 2:
            raise ScoringError(f"{cid}: an adjudication needs two independent reviews")
        if verdicts[0].get("status", REVIEWED) != REVIEWED:
            raise ScoringError(f"{cid}: the adjudication is not finished")
        if verdicts[0]["reviewer"] in names:
            raise ScoringError(f"{cid}: the adjudicator must not be one of the two reviewers")
        audit.update(resolution="adjudicated", adjudicated_by=verdicts[0]["reviewer"])
        return verdicts[0], audit
    if not done:
        audit["resolution"] = NOT_REVIEWED
        return None, audit
    if len({_verdict(r) for r in done}) > 1:
        raise ScoringError(f"{cid}: independent reviews disagree; adjudicate first")
    audit["resolution"] = "agreed" if len(done) > 1 else "single"
    return done[0], audit


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
                  min_examples: int = DEFAULT_MIN_EXAMPLES,
                  rubric_version: Any = None) -> dict:
    conversations = {c["id"]: c for c in data["conversations"]}
    supported = {cid for cid, c in conversations.items() if c.get("supported_unambiguous")}
    records = [r for r in reviews if r.get("arm") == arm]
    grouped: dict[str, list] = {}
    for r in records:
        _validate_review(r, set(conversations))
        if rubric_version is not None and r["rubric_version"] != rubric_version:
            raise ScoringError(f"{r['conversation']}: rubric_version {r['rubric_version']} "
                               f"differs from the run manifest's {rubric_version}")
        grouped.setdefault(r["conversation"], []).append(r)
    mine, audit = [], {}
    for cid, rows in grouped.items():
        chosen, audit[cid] = _resolve(cid, rows)
        if chosen is not None:
            mine.append(chosen)

    families = {}
    for family in sorted({c["family"] for c in conversations.values()}):
        rows = [r for r in mine if conversations[r["conversation"]]["family"] == family]
        entry = _metrics(rows, supported)
        entry["status"] = "INCONCLUSIVE" if len(rows) < min_examples else "reported"
        families[family] = entry
    overall = _metrics(mine, supported)
    splits = {}
    for split in ("development", "held_out"):
        rows = [r for r in mine if conversations[r["conversation"]].get("split") == split]
        splits[split] = _metrics(rows, supported)
        splits[split]["targets"] = {k: _target(splits[split][k], t) for k, t in TARGETS.items()}
    breaches = sorted(r["conversation"] for r in mine if r.get("access_breach"))
    return {
        "arm": arm, "min_examples": min_examples,
        "reviewers": sorted({r["reviewer"] for r in records}),
        "review_audit": audit,
        "not_reviewed": sorted(c for c, a in audit.items() if a["resolution"] == NOT_REVIEWED),
        "double_reviewed": sum(a["resolution"] in ("agreed", "adjudicated")
                               for a in audit.values()),
        "rubric_versions": sorted({str(r["rubric_version"]) for r in mine}),
        "families": families, "overall": overall, "splits": splits,
        "targets": {k: _target(overall[k], t) for k, t in TARGETS.items()},
        "enablement_blocked": bool(breaches),
        "access_breaches": {
            "count": len(breaches), "conversations": breaches, "suite_size": len(mine),
            "note": ZERO_BREACH_NOTE if not breaches else
            "Any access breach blocks enablement regardless of other numbers."},
    }


DIAGNOSTIC_NOTE = ("private diagnostic stage from the run file; it explains where a turn "
                   "ended and never overrides a human verdict")


def diagnostic_stages(run: Mapping) -> dict:
    """Per-turn research stages, counted apart from every human judgment."""
    stages: Counter = Counter()
    by_family: dict[str, Counter] = {}
    for row in run.get("conversations", ()):
        for turn in row.get("turns", ()):
            stage = (turn.get("diagnostics") or {}).get("stage", "not_traced")
            stages[stage] += 1
            by_family.setdefault(row.get("family"), Counter())[stage] += 1
    return {"stages": dict(stages), "by_family": {f: dict(c) for f, c in by_family.items()},
            "note": DIAGNOSTIC_NOTE}


def check_evidence(reviews: Sequence[Mapping], bundles: Sequence[Mapping],
                   runs: Mapping[str, Mapping]) -> None:
    """Refuse a review citing a record outside the packet its reviewer was given."""
    allowed = {}
    for bundle in bundles:
        for packet in bundle.get("packets", ()):
            allowed[(bundle.get("arm"), bundle.get("reviewer"), packet.get("conversation"))] = (
                bundle.get("run_id"), set(packet.get("authorized_record_ids", ())))
    for r in reviews:
        if r.get("arm") not in runs or r.get("status", REVIEWED) == NOT_REVIEWED:
            continue
        key = (r["arm"], r.get("reviewer"), r.get("conversation"))
        if key not in allowed:
            raise ScoringError(f"{r.get('conversation')}: no review packet was issued to "
                               f"{r.get('reviewer')!r} for arm {r['arm']}")
        run_id, ids = allowed[key]
        if run_id != runs[r["arm"]].get("run_id"):
            raise ScoringError(f"{r['conversation']}: {r['reviewer']}'s packet is for another run")
        used = {c["record_id"] for c in r.get("claims", ()) if c.get("record_id") is not None}
        used |= set(r.get("evidence_record_ids", ()))
        if used - ids:
            raise ScoringError(f"{r['conversation']}: {r['reviewer']} cites records "
                               f"{sorted(used - ids)} not authorized in their packet")


def check_conditions(runs: Mapping[str, Mapping], *, mode: str,
                     set_digests: Optional[Mapping[str, str]] = None) -> None:
    """Refuse a run set whose manifests are incomplete or conditions unequal."""
    if mode not in MODES:
        raise ScoringError(f"mode must be one of {MODES}")
    if not runs:
        raise ScoringError("no runs")
    arms = [r.get("arm") for r in runs.values()]
    if mode == "architecture":
        if len(set(arms)) != len(arms) or any(a not in ARMS for a in arms):
            raise ScoringError(f"architecture mode needs distinct arms from {ARMS}")
        for label, run in runs.items():
            if label != run.get("arm"):
                raise ScoringError(f"run label {label!r} must equal its arm {run.get('arm')!r}")
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
    if mode == "architecture" and any(not m.get("model_ids") for m in manifests):
        raise ScoringError("manifest lacks model_ids")
    if set_digests is not None and manifests[0]["set_digests"] != dict(set_digests):
        raise ScoringError("manifest set_digests do not match the locked set")


def preference(records: Sequence[Mapping]) -> dict:
    for r in records:
        if r.get("blinded") is not True:
            raise ScoringError(f"{r.get('conversation')}: unblinded preference records are refused")
        _require_named(r, "reviewer", r.get("conversation"))
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
        _require_named(i, "human_reviewer", i.get("item"), "human reviewer")
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
    latencies = [r["latency_ms"] for r in rows if r.get("latency_ms") is not None]
    wins = [r for r in rows if r.get("success")]
    spent = sum(r.get("cost", 0) or 0 for r in rows)
    out = {"n": len(rows), "successes": len(wins),
           "no_latency_recorded": len(rows) - len(latencies),
           "p50": percentile(latencies, 0.5), "p95": percentile(latencies, 0.95),
           "total_cost": spent,
           "cost_per_successful_task": spent / len(wins) if wins else None}
    if not wins:
        out["note"] = "cost per successful task is undefined: no successful tasks"
    return out


def cost_latency(run: Mapping) -> dict:
    """Queue-inclusive latency (ms) and cost, cold and warm apart."""
    rows = run.get("conversations", ())
    fake = run.get("providers") != "real"
    cold_distinct = len({r.get("id") for r in rows if r.get("cache") == "cold"})
    reasons = []
    if fake:
        reasons.append("providers were not real")
    if run.get("capacity_fit") is not True:
        reasons.append("the burst did not fit the approved budget")
    if cold_distinct < MIN_CAPACITY_BURST:
        reasons.append(f"{cold_distinct} distinct cold conversations, fewer than "
                       f"{MIN_CAPACITY_BURST}")
    if not str(run.get("manifest", {}).get("campaign_approval_id") or "").strip():
        reasons.append("no campaign approval id in the manifest")
    return {
        "arm": run.get("arm"),
        "cold": _group([r for r in rows if r.get("cache") == "cold"]),
        "warm": _group([r for r in rows if r.get("cache") == "warm"]),
        "capacity": "unverified" if reasons else "verified",
        "capacity_reason": "; ".join(reasons) or None,
        "evidence": FAKE_NOTE if fake else "real providers",
    }
