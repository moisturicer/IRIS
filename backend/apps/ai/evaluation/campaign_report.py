"""Comparable evaluation campaigns and their report (IR-609). Pure: no DB, no vendor.

A campaign is ``{label: [run, ...]}``, one list of repetitions per arm or model.
"""

from __future__ import annotations

from collections import Counter
from typing import Mapping, Optional, Sequence

from apps.ai.controller.versions import CONTROLLER_ENGINE, LEGACY_ENGINE
from apps.ai.public import PUBLIC_PROTOCOL

from .conversation_scoring import (ARMS, CONDITION_KEYS, DEFAULT_MIN_EXAMPLES, MODES,
                                   TARGET_LABEL, TARGETS, ZERO_BREACH_NOTE, ScoringError,
                                   diagnostic_stages, score_reviews)
from .conversations import check_lock, postdates_lock, split_digests
from .pilot_report import percentile

MIN_REPETITIONS = 3
REQUIRED_MANIFEST = ("run_id", "timestamp_utc", "git_commit", "engine_version",
                     "protocol_version", "cache_state", *CONDITION_KEYS)
ARM_ENGINES = {"controller": CONTROLLER_ENGINE, "current": LEGACY_ENGINE,
               "fixed_synthesis": LEGACY_ENGINE}
#: Arms with no engine of their own in this codebase must name a pinned release.
NEEDS_REF = ("fixed_synthesis",)
APPROVALS = ("funding", "provider_data_policy", "dataset_transmission")
PROXY_NOTE = ("Results describe the evaluation corpus named here; a proxy corpus result is "
              "not CIT-U research and is never reported as a finding about it.")
NOT_AUTHORIZED = ("This report authorizes no spending, deployment or release; those need "
                  "their own named decisions.")
HEADLINE = ("task_completion", "claim_support", "citation_support", "page_support")
SCENARIOS = ("access_and_recovery", "durability", "browser")
#: ADR-042 keeps optional public research off until its own approval.
DISABLED = {"scenario:A15_public_research":
            "public research stays disabled pending its own approval (ADR-042)"}
EXAMPLES = 3


class CampaignRefused(ValueError):
    """The campaign cannot be run or reported honestly: say why."""


def _runs(campaign: Mapping[str, Sequence[Mapping]]):
    return [(label, r) for label, runs in campaign.items() for r in runs]


def _require_current_lock(data: Mapping, lock: Optional[Mapping]) -> None:
    if not lock:
        raise CampaignRefused("no lock: a campaign needs a locked set")
    stale = check_lock(data, lock)
    if stale:
        raise CampaignRefused(f"the set no longer matches its lock: {', '.join(stale)}")


def _check_manifests(campaign) -> None:
    seen_runs, seen_conversations = set(), set()
    for label, run in _runs(campaign):
        manifest = run.get("manifest") or {}
        missing = [k for k in REQUIRED_MANIFEST if manifest.get(k) in (None, "", {})]
        if missing:
            raise CampaignRefused(f"{label}: manifest of {run.get('run_id')} lacks "
                                  f"{', '.join(missing)}")
        if run.get("run_id") in seen_runs:
            raise CampaignRefused(f"{label}: run_id {run.get('run_id')} appears twice")
        seen_runs.add(run.get("run_id"))
        cases = [row.get("id") for row in run.get("conversations", ())]
        doubled = sorted({c for c in cases if cases.count(c) > 1})
        if doubled:
            raise CampaignRefused(f"{run['run_id']}: cases {', '.join(doubled)} were run twice")
        for row in run.get("conversations", ()):
            cid = row.get("conversation_id")
            if cid is None:
                continue
            if cid in seen_conversations:
                raise CampaignRefused(f"{run['run_id']}: saved Conversation {cid} is reused; "
                                      "every case needs a fresh one")
            seen_conversations.add(cid)


def _check_conditions(data: Mapping, campaign, mode: str) -> None:
    keys = CONDITION_KEYS if mode == "architecture" else tuple(
        k for k in CONDITION_KEYS if k != "model_ids")
    runs = _runs(campaign)
    first = runs[0][1]["manifest"]
    for label, run in runs:
        manifest = run["manifest"]
        for key in keys:
            if manifest[key] != first[key]:
                raise CampaignRefused(f"{label}: {key} differs from {runs[0][0]}; "
                                      "conditions are not equal")
    if first["set_digests"] != split_digests(data):
        raise CampaignRefused("run set_digests do not match the locked set")


def _check_arms(campaign, mode: str) -> None:
    for label, run in _runs(campaign):
        if run["manifest"]["protocol_version"] != PUBLIC_PROTOCOL:
            raise CampaignRefused(f"{label}: runs must use the authenticated {PUBLIC_PROTOCOL} "
                                  "reader protocol")
        arm = run.get("arm")
        if arm not in ARMS:
            raise CampaignRefused(f"{label}: unknown arm {arm!r}")
        if run["manifest"]["engine_version"] != ARM_ENGINES[arm]:
            raise CampaignRefused(f"{label}: arm {arm} ran engine "
                                  f"{run['manifest']['engine_version']}, not {ARM_ENGINES[arm]}")
        if arm in NEEDS_REF and not str(run["manifest"].get("implementation_ref") or "").strip():
            raise CampaignRefused(f"{label}: {arm} has no engine of its own here; its manifest "
                                  "needs the implementation_ref of a pinned release")
    if mode == "model":
        if len({run.get("arm") for _, run in _runs(campaign)}) != 1:
            raise CampaignRefused("a model comparison holds the architecture fixed; "
                                  "compare architectures separately")
        models = [str(runs[0]["manifest"]["model_ids"]) for runs in campaign.values()]
        if len(set(models)) != len(models):
            raise CampaignRefused("a model comparison needs different model_ids per label")
        return
    identities = {}
    for label, runs in campaign.items():
        if any(run.get("arm") != label for run in runs):
            raise CampaignRefused(f"{label}: every run under an arm label must be that arm")
        pinned = {(r["manifest"]["engine_version"], r["manifest"]["git_commit"],
                   r["manifest"].get("implementation_ref")) for r in runs}
        if len(pinned) != 1:
            raise CampaignRefused(f"{label}: repetitions ran different implementations")
        identities[label] = pinned.pop()
    if len(set(identities.values())) != len(identities):
        raise CampaignRefused("each arm needs a distinct pinned implementation "
                              "(engine, commit, release); two arms ran the same code")


def preflight(data: Mapping, lock: Optional[Mapping], campaign: Mapping[str, Sequence[Mapping]],
              *, mode: str, counted: bool) -> list[str]:
    """Refuse an incomparable campaign; return why a comparable one is not counted."""
    if mode not in MODES:
        raise CampaignRefused(f"mode must be one of {MODES}")
    if not campaign or not any(campaign.values()):
        raise CampaignRefused("no runs")
    _require_current_lock(data, lock)
    _check_manifests(campaign)
    _check_arms(campaign, mode)
    _check_conditions(data, campaign, mode)
    reasons = []
    if data.get("label_status") != "human_reviewed":
        reasons.append("labels are draft_unreviewed")
    for label, runs in campaign.items():
        if len(runs) < MIN_REPETITIONS:
            reasons.append(f"{label}: {len(runs)} repetitions, fewer than {MIN_REPETITIONS}")
        if any(r.get("providers") != "real" for r in runs):
            reasons.append(f"{label}: fake providers are a contract check")
    if counted and reasons:
        raise CampaignRefused("not a counted campaign: " + "; ".join(reasons))
    return reasons



def approvals_status(approvals: Optional[Mapping]) -> dict:
    """Each approval needs a reference and a named approver; nothing here grants one."""
    out, missing = {}, []
    for key in APPROVALS:
        entry = (approvals or {}).get(key) or {}
        recorded = all(str(entry.get(f) or "").strip() for f in ("reference", "approved_by"))
        out[key] = {"recorded": recorded, "reference": entry.get("reference"),
                    "approved_by": entry.get("approved_by"), "date": entry.get("date")}
        if not recorded:
            missing.append(key)
    return {**out, "complete": not missing, "unrecorded": missing}


def require_paid_held_out(approvals: Optional[Mapping]) -> None:
    missing = approvals_status(approvals)["unrecorded"]
    if missing:
        raise CampaignRefused("a paid held-out campaign needs recorded approvals; missing: "
                              + ", ".join(missing))


def require_frozen_for_held_out(data: Mapping, lock: Optional[Mapping]) -> None:
    """Held-out cases open only once the set, rubric and thresholds are frozen."""
    _require_current_lock(data, lock)
    if not lock.get("locked_at"):
        raise CampaignRefused("the lock has no locked_at: held-out cases stay closed")
    if lock.get("thresholds") != TARGETS:
        raise CampaignRefused("the lock does not freeze the scorer's thresholds; relock "
                              "before opening held-out cases")


def _attempts(row: Mapping):
    return [a for t in row.get("turns", ()) for a in t.get("physical_attempts", ())]


def _turns_missing_usage(rows) -> int:
    return sum(t.get("usage_status") != "reported" for r in rows for t in r.get("turns", ()))


def _uncosted(rows) -> int:
    return sum(a.get("cost_usd") is None for r in rows for a in _attempts(r))


def _cost_group(rows: Sequence[tuple[str, Mapping]], successes) -> dict:
    latencies = [r["latency_ms"] for _, r in rows if r.get("latency_ms") is not None]
    operations: dict[str, dict] = {}
    models = set()
    for _, r in rows:
        for a in _attempts(r):
            op = operations.setdefault(a.get("operation", "unknown"), {
                "attempts": 0, "reported_usd": 0, "unreported_reserved_usd": 0})
            op["attempts"] += 1
            if a.get("cost_usd") is not None:
                op["reported_usd" if a.get("usage_reported")
                   else "unreported_reserved_usd"] += a["cost_usd"]
            if a.get("model"):
                models.add(a["model"])
    missing = _turns_missing_usage([r for _, r in rows])
    uncosted = _uncosted([r for _, r in rows])
    reported = sum(op["reported_usd"] for op in operations.values())
    won = None if successes is None else sum((run_id, r.get("id")) in successes
                                             for run_id, r in rows)
    out = {"conversations": len(rows), "no_latency_recorded": len(rows) - len(latencies),
           "p50_ms": percentile(latencies, 0.5), "p95_ms": percentile(latencies, 0.95),
           "operations": operations, "models": sorted(models), "reported_usd": reported,
           "unreported_reserved_usd": sum(op["unreported_reserved_usd"]
                                          for op in operations.values()),
           "turns_missing_usage": missing, "attempts_missing_cost": uncosted,
           "cost_status": "incomplete" if missing or uncosted else "complete",
           "successes": won, "cost_per_successful_task": None}
    if missing or uncosted:
        out["note"] = (f"{missing} turns have missing usage and {uncosted} attempts no cost; "
                       "spend is not complete and is never imputed as zero")
    elif not won:
        out["note"] = "cost per successful task is undefined: no successful tasks"
    else:
        out["cost_per_successful_task"] = reported / won
    return out


def spend(runs: Sequence[Mapping], successes=None) -> dict:
    """Latency and physical spend, cold and warm apart. ``successes``: {(run_id, case)}."""
    rows = [(run.get("run_id"), r) for run in runs for r in run.get("conversations", ())]
    bases = []
    for run in runs:
        basis = run.get("manifest", {}).get("pricing_per_million_tokens_usd") or {}
        if basis not in bases:
            bases.append(basis)
    return {
        "cold": _cost_group([x for x in rows if x[1].get("cache") == "cold"], successes),
        "warm": _cost_group([x for x in rows if x[1].get("cache") == "warm"], successes),
        "unknown_cache": sum(x[1].get("cache") not in ("cold", "warm") for x in rows),
        "price_basis": {"per_million_tokens_usd": bases, "consistent": len(bases) <= 1,
                        "attempt_basis": sorted({
            a.get("price_basis") for _, r in rows for a in _attempts(r)
            if a.get("price_basis")})},
    }


def smoke_summary(run: Mapping, *, case_cost_usd: float, campaign_cost_usd: float,
                  planned_cases: int) -> dict:
    """A small development run measured before caps are proposed for a campaign.

    ``planned_cases`` counts every case execution: cases x arms x repetitions.
    """
    rows = run.get("conversations", ())
    if any(r.get("split") != "development" for r in rows):
        raise CampaignRefused("a smoke runs development cases only")
    outcomes = Counter(t.get("outcome") for r in rows for t in r.get("turns", ()))
    costs = [sum(a.get("cost_usd") or 0 for a in _attempts(r)) for r in rows]
    peak = max(costs, default=0)
    missing = _turns_missing_usage(rows)
    uncosted = _uncosted(rows)
    latencies = [r["latency_ms"] for r in rows if r.get("latency_ms") is not None]
    out = {
        "run_id": run.get("run_id"), "providers": run.get("providers"),
        "conversations": len(rows),
        "complete": sum(r.get("status") == "complete" for r in rows),
        "outcomes": dict(outcomes),
        "p50_ms": percentile(latencies, 0.5), "p95_ms": percentile(latencies, 0.95),
        "spend": spend([run]), "turns_missing_usage": missing,
        "attempts_missing_cost": uncosted,
        "max_conversation_cost_usd": peak,
        "operations_in_cap": sorted({a.get("operation") for r in rows for a in _attempts(r)}),
        "case_cost_usd": case_cost_usd, "campaign_cost_usd": campaign_cost_usd,
        "planned_cases": planned_cases,
        "case_cap_covers_observed": peak <= case_cost_usd,
        "projected_campaign_cost_usd": peak * planned_cases,
        "campaign_cap_covers_projection": peak * planned_cases <= campaign_cost_usd,
        "cap_note": ("caps cover every physical attempt the smoke executed (retries, "
                     "fallbacks, embedding, reranking, Jev) at reservation cost when usage "
                     "was not reported; an operation that did not run is not in the cap"),
    }
    reasons = []
    if run.get("providers") != "real":
        reasons.append("fake providers: setup check only, spend not measured")
    if missing or uncosted:
        reasons.append(f"{missing} turns have missing usage, {uncosted} attempts no cost")
    if not out["complete"]:
        reasons.append("no conversation completed")
    if not out["case_cap_covers_observed"]:
        reasons.append("the per-case cap is below the dearest observed conversation")
    if not out["campaign_cap_covers_projection"]:
        reasons.append("the campaign cap is below the projected campaign")
    out.update(ready=not reasons, not_ready_reasons=reasons)
    return out


def _resolved(audit: Mapping) -> Optional[Mapping]:
    """The verdict the scorer used for one conversation, read from its audit."""
    records = audit["records"]
    if audit["resolution"] == "adjudicated":
        return next(r for r in records if r.get("role") == "adjudication")
    if audit["resolution"] in ("agreed", "single"):
        return next(r for r in records if r.get("role", "independent") == "independent"
                    and r.get("status", "reviewed") == "reviewed")
    return None


def _reviews_for(run: Mapping, label: str, reviews: Sequence[Mapping], *, repeated: bool,
                 mode: str) -> list[dict]:
    mine = []
    for r in reviews:
        if mode == "architecture" and r.get("arm") != run.get("arm"):
            continue
        if "run_id" not in r:
            if repeated or mode == "model":
                raise CampaignRefused(f"{r.get('conversation')}: with repetitions every review "
                                      "must name the run_id it judged")
        elif r["run_id"] != run.get("run_id"):
            continue
        mine.append({**r, "arm": label})
    return mine


def _examples(run: Mapping, verdicts: Mapping[str, Mapping], data: Mapping) -> dict:
    questions = {c["id"]: c["turns"][0]["user"] for c in data["conversations"]}
    wins, losses = [], []
    for row in run.get("conversations", ()):
        v = verdicts.get(row.get("id"))
        if v is None:
            continue
        entry = {"run_id": run.get("run_id"), "conversation": row.get("id"),
                 "family": row.get("family"), "question": questions.get(row.get("id")),
                 "run_status": row.get("status"),
                 "stages": [(t.get("diagnostics") or {}).get("stage", "not_traced")
                            for t in row.get("turns", ())],
                 "verdict": v["task_completion"], "access_breach": bool(v.get("access_breach"))}
        if v["task_completion"] == "yes" and not v.get("access_breach"):
            wins.append(entry)
        else:
            losses.append(entry)
    return {"successes": wins, "failures": losses}


def _interleave(lists):
    """One from each repetition in turn, so no repetition supplies every example."""
    out = []
    for i in range(max((len(x) for x in lists), default=0)):
        out += [x[i] for x in lists if i < len(x)]
    return out


def _arm(label: str, runs: Sequence[Mapping], data: Mapping, reviews, *, mode: str,
         min_examples: int) -> dict:
    families = {c["id"]: c["family"] for c in data["conversations"]}
    repetitions, successes, breaches = [], set(), []
    examples = {"successes": [], "failures": []}
    singles = []
    family_rows: dict[str, list] = {}
    unreviewed: dict[str, set] = {}
    for run in runs:
        mine = _reviews_for(run, label, reviews, repeated=len(runs) > 1, mode=mode)
        scored = score_reviews(data, mine, arm=label, min_examples=min_examples,
                               rubric_version=run["manifest"]["rubric_version"])
        verdicts = {cid: v for cid, a in scored["review_audit"].items()
                    if (v := _resolved(a)) is not None}
        for row in run.get("conversations", ()):
            cid = row.get("id")
            if cid not in verdicts:
                unreviewed.setdefault(families.get(cid, row.get("family")), set()).add(cid)
            elif (verdicts[cid]["task_completion"] == "yes"
                  and not verdicts[cid].get("access_breach")):
                successes.add((run.get("run_id"), cid))
        breaches += [{"run_id": run.get("run_id"), "conversation": c}
                     for c in scored["access_breaches"]["conversations"]]
        ran = {families.get(r.get("id")) for r in run.get("conversations", ())}
        for family, entry in scored["families"].items():
            if family in ran:
                family_rows.setdefault(family, []).append(entry)
        found = _examples(run, verdicts, data)
        for kind in examples:
            examples[kind].append(found[kind])
        singles += [f"{run.get('run_id')}/{cid}" for cid, a in scored["review_audit"].items()
                    if a["resolution"] == "single"]
        repetitions.append({"run_id": run.get("run_id"), "providers": run.get("providers"),
                            "scores": scored, "diagnostics": diagnostic_stages(run)})
    summary = {}
    for metric in HEADLINE:
        fracs = [r["scores"]["overall"][metric] for r in repetitions]
        values = [f["value"] for f in fracs if f["value"] is not None]
        summary[metric] = {"per_repetition": fracs, "min": min(values, default=None),
                           "max": max(values, default=None)}
    family_report = {}
    for family, rows in sorted(family_rows.items()):
        status = ("unreviewed" if unreviewed.get(family) else
                  "INCONCLUSIVE" if any(r["status"] == "INCONCLUSIVE" for r in rows)
                  else "reported")
        family_report[family] = {"status": status, "per_repetition": rows,
                                 "not_reviewed": sorted(unreviewed.get(family, ()))}
    return {"status": "measured", "architecture": runs[0].get("arm"),
            "git_commit": runs[0]["manifest"]["git_commit"],
            "engine_version": runs[0]["manifest"]["engine_version"],
            "repetitions": repetitions, "summary": summary, "families": family_report,
            "access_breaches": breaches, "spend": spend(runs, successes),
            "single_reviewed": singles,
            "examples": {k: _interleave(v)[:EXAMPLES] for k, v in examples.items()}}


def _scenarios(scenarios: Optional[Mapping]) -> dict:
    rows = {}
    for name in SCENARIOS:
        got = (scenarios or {}).get(name) or {}
        status = got.get("status", "not_measured")
        rows[name] = {"status": status,
                      "passed": status == "measured" and got.get("passed") is True,
                      "kind": got.get("kind"),
                      "reason": got.get("reason") or (None if got else
                                                      "no IR-608 evidence supplied")}
    return rows


def _check_held_out(data, lock, campaign, approvals) -> None:
    held = [r for _, r in _runs(campaign)
            if any(row.get("split") == "held_out" for row in r.get("conversations", ()))]
    if not held:
        return
    require_frozen_for_held_out(data, lock)
    for run in held:
        if not postdates_lock(run["manifest"]["timestamp_utc"], lock):
            raise CampaignRefused(f"{run['run_id']}: held-out output must postdate the lock "
                                  f"frozen at {lock['locked_at']}")
        if run.get("providers") == "real":
            require_paid_held_out(approvals)


def _check_approved_caps(campaign, approvals) -> None:
    """Runs may not exceed the case cap recorded with the funding approval."""
    cap = ((approvals or {}).get("funding") or {}).get("case_cost_usd")
    if cap is None:
        return
    for label, run in _runs(campaign):
        used = (run["manifest"].get("limits") or {}).get("case_cost_usd")
        if used is None or used > cap:
            raise CampaignRefused(f"{label}: {run['run_id']} case cap {used} is not within the "
                                  f"approved {cap}")


def build_report(data: Mapping, lock: Optional[Mapping],
                 campaign: Mapping[str, Sequence[Mapping]], reviews: Sequence[Mapping], *,
                 mode: str, approvals: Optional[Mapping], scenarios: Optional[Mapping],
                 min_examples: int = DEFAULT_MIN_EXAMPLES, counted: bool = False,
                 excluded: Sequence[Mapping] = ()) -> dict:
    """The campaign report: separate dimensions, explicit gaps, blocking safety."""
    if counted and min_examples < DEFAULT_MIN_EXAMPLES:
        raise CampaignRefused(f"a counted report keeps the scorer's family minimum of "
                              f"{DEFAULT_MIN_EXAMPLES}; {min_examples} would lower it")
    reasons = preflight(data, lock, campaign, mode=mode, counted=counted)
    _check_held_out(data, lock, campaign, approvals)
    _check_approved_caps(campaign, approvals)
    if counted:
        unstated = sorted({str(r.get("conversation")) for r in reviews
                           if "reviewer_kind" not in r})
        if unstated:
            raise CampaignRefused(f"not a counted campaign: reviewer_kind is not stated for "
                                  f"{', '.join(unstated[:5])}")
    arms = {}
    try:
        for label, runs in campaign.items():
            arms[label] = _arm(label, runs, data, reviews, mode=mode, min_examples=min_examples)
    except ScoringError as exc:
        raise CampaignRefused(str(exc)) from None
    if counted:
        singles = [s for arm in arms.values() for s in arm["single_reviewed"]]
        if singles:
            raise CampaignRefused(f"not a counted campaign: {len(singles)} conversations have "
                                  f"one review, not two ({', '.join(singles[:5])})")
    unmeasured = []
    if mode == "architecture":
        for arm in ARMS:
            if arm not in arms:
                arms[arm] = {"status": "not_measured",
                             "reason": "no run of a real pinned implementation was supplied"}
                unmeasured.append({"name": f"arm:{arm}", "reason": arms[arm]["reason"]})
    scenario_rows = _scenarios(scenarios)
    unmeasured += [{"name": f"scenario:{name}", "reason": row["reason"]}
                   for name, row in scenario_rows.items() if row["status"] != "measured"]
    unmeasured += [{"name": name, "reason": reason} for name, reason in DISABLED.items()]
    blocking = []
    for label, arm in arms.items():
        if arm["status"] != "measured":
            continue
        blocking += [f"{label}: access breach in {b['conversation']} ({b['run_id']})"
                     for b in arm["access_breaches"]]
        blocking += [f"{label}: family {family} is unreviewed "
                     f"({', '.join(entry['not_reviewed'])})"
                     for family, entry in arm["families"].items()
                     if entry["status"] == "unreviewed"]
    for name, row in scenario_rows.items():
        if row["status"] != "measured":
            blocking.append(f"scenario {name} was not measured")
        elif not row["passed"]:
            blocking.append(f"scenario {name} failed")
    corpus = data.get("corpus") or {}
    return {
        "issue": "IR-609", "set_id": data.get("set_id"), "mode": mode,
        "comparison": ("architecture: arms share corpus, models, data policy and budget"
                       if mode == "architecture" else
                       "model: one architecture, models vary; never credited to an architecture"),
        "counted": counted and not reasons, "not_counted_reasons": reasons,
        "label_status": data.get("label_status"), "min_examples": min_examples,
        "corpus": {"snapshot_id": corpus.get("snapshot_id"),
                   "paper_set_sha256": corpus.get("paper_set_sha256"), "claim": PROXY_NOTE},
        "approvals": approvals_status(approvals), "arms": arms, "scenarios": scenario_rows,
        "unmeasured": unmeasured, "excluded_runs": [dict(e) for e in excluded],
        "enablement_blocked": bool(blocking), "blocking": blocking,
        "notes": [NOT_AUTHORIZED, ZERO_BREACH_NOTE, TARGET_LABEL],
    }


def _frac(frac: Mapping) -> str:
    if frac["value"] is None:
        return "n/a (0)"
    return (f"{frac['value']:.3f} ({frac['numerator']}/{frac['denominator']}, "
            f"95% CI {frac['wilson_low']:.2f}-{frac['wilson_high']:.2f})")


def _usd(value) -> str:
    return "n/a" if value is None else f"${value:.4f}"


def _arm_markdown(label: str, arm: Mapping) -> list[str]:
    lines = [f"## {label}", ""]
    if arm["status"] != "measured":
        return lines + [f"not_measured: {arm['reason']}", ""]
    runs = arm["repetitions"]
    lines += [f"{arm['engine_version']} @ {arm['git_commit']}, {len(runs)} repetitions", "",
              "| Metric | " + " | ".join(r["run_id"] for r in runs) + " |",
              "|---|" + "---|" * len(runs)]
    lines += [f"| {metric} | " + " | ".join(_frac(f) for f in row["per_repetition"]) + " |"
              for metric, row in arm["summary"].items()]
    lines += ["", "| Family | Status | Completion per repetition |", "|---|---|---|"]
    lines += [f"| {family} | {entry['status']} | " + ", ".join(
        f"{r['task_completion']['numerator']}/{r['task_completion']['denominator']}"
        for r in entry["per_repetition"]) + " |" for family, entry in arm["families"].items()]
    lines += ["", f"Access breaches: {len(arm['access_breaches'])}" + "".join(
        f"; {b['conversation']} ({b['run_id']})" for b in arm["access_breaches"]), ""]
    for cache in ("cold", "warm"):
        g = arm["spend"][cache]
        lines.append(f"- {cache}: n={g['conversations']} p50={g['p50_ms']}ms "
                     f"p95={g['p95_ms']}ms, reported {_usd(g['reported_usd'])}, "
                     f"unreported reserved {_usd(g['unreported_reserved_usd'])}, "
                     f"missing usage {g['turns_missing_usage']} turns, "
                     f"cost/success {_usd(g['cost_per_successful_task'])}")
    stages: Counter = Counter()
    for rep in runs:
        stages.update(rep["diagnostics"]["stages"])
    lines.append("- diagnostic stages (never a verdict): "
                 + (", ".join(f"{k}={v}" for k, v in sorted(stages.items())) or "none"))
    for kind, word in (("successes", "success"), ("failures", "failure")):
        lines += [f"- {word}: {e['conversation']} ({e['family']}, {e['run_id']}) verdict "
                  f"{e['verdict']}, stages {', '.join(e['stages'])}"
                  for e in arm["examples"][kind]]
    return lines + [""]


def render_markdown(report: Mapping) -> str:
    lines = [f"# Ask IRIS evaluation campaign: {report['set_id']}", ""]
    if report["enablement_blocked"]:
        lines += ["**ENABLEMENT BLOCKED**", ""] + [f"- {b}" for b in report["blocking"]] + [""]
    approvals = ", ".join(
        f"{k} " + (f"recorded ({v['reference']})" if v["recorded"] else "MISSING")
        for k, v in report["approvals"].items() if isinstance(v, dict))
    lines += [f"- Comparison: {report['comparison']}",
              f"- Counted: {report['counted']}"]
    lines += [f"  - not counted: {r}" for r in report["not_counted_reasons"]]
    lines += [f"- Labels: {report['label_status']}; family minimum {report['min_examples']}",
              f"- Corpus: {report['corpus']['snapshot_id']}. {report['corpus']['claim']}",
              f"- Approvals: {approvals}", ""]
    for label, arm in report["arms"].items():
        lines += _arm_markdown(label, arm)
    lines += ["## Not measured", ""] + [f"- not_measured {u['name']}: {u['reason']}"
                                          for u in report["unmeasured"]]
    lines += ["", "## Excluded runs", ""] + ([f"- {e['run_id']}: {e['reason']}"
                                             for e in report["excluded_runs"]] or ["- none"])
    lines += ["", "## Notes", ""] + [f"- {n}" for n in report["notes"]]
    return "\n".join(lines) + "\n"
