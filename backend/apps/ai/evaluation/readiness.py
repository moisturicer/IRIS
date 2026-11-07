"""Release-readiness report and manifest over IR-605's campaign evidence (IR-741). Pure.

This extends the IR-609 campaign report; it adds no scorer, no run-file format and no
collection. It reads a campaign report (``campaign_report.build_report``), a frozen baseline
report, IR-608 scenario evidence, a predeclared workload, an authorized latency/cost profile
and load measurements, and answers one question honestly: *does the recorded evidence meet the
selected acceptance profile (ADR-049 §25-§26)?*

The rule that shapes everything below: **missing, inconclusive, fake or incomparable evidence
is never a pass.** Every gate has one of these statuses, and only ``met`` clears it:

``met`` / ``not_met`` (measured and short) / ``inconclusive`` (too little to say) /
``not_measured`` (absent) / ``incomparable`` (cannot be set beside its baseline) /
``contract_only`` (fake providers, or evidence of a kind the claim does not rest on; never
quality or capacity) / ``breached`` (an access or disclosure breach, which no average offsets).

Each IR-608 suite names the kind of evidence its claim needs (``scenarios.SUITES``). Access and
disclosure rules are deterministic code, so a deterministic suite is the right kind for that
gate; a deterministic or fake run is ``contract_only`` for quality, latency and cost.

``evidence_met`` means the recorded evidence meets the profile. It authorizes no release,
spending or deployment: a named person's decision is always a listed human-review gap.
The manifest holds no time of day, so identical inputs give identical bytes, which is what
lets ``assert_ready`` rebuild it from its inputs rather than trust the verdict it states.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from typing import Any, Callable, Mapping, Optional, Sequence

from .campaign_report import CAPABILITY_NOTE, DISABLED, MIN_REPETITIONS, approvals_status
from .conversation_scoring import (DEFAULT_MIN_EXAMPLES, TARGET_LABEL, TARGETS,
                                   ZERO_BREACH_NOTE, _frac)
from .engines import mismatches
from .pilot_report import percentile
from .scenarios import BROWSER_CHECKS, SUITES

SCHEMA_VERSION = "release-readiness-1"
ISSUE = "IR-741"

MET, NOT_MET, INCONCLUSIVE = "met", "not_met", "inconclusive"
NOT_MEASURED, INCOMPARABLE = "not_measured", "incomparable"
CONTRACT_ONLY, BREACHED = "contract_only", "breached"
STATUSES = (MET, NOT_MET, INCONCLUSIVE, NOT_MEASURED, INCOMPARABLE, CONTRACT_ONLY, BREACHED)
READY, BLOCKED = "evidence_met", "blocked"

METRICS = tuple(TARGETS)
#: Families the campaign report itself lists as disabled; named in the gate, never dropped.
EXCLUDED_FAMILIES = {"A15": DISABLED["scenario:A15_public_research"]}
#: Interpretations this report applies that no approved policy states. They are written into
#: every manifest so a reader sees them; nothing here is a confirmed decision.
POLICY_DECISIONS = (
    {"id": "objectives_on_point_estimate", "status": "awaiting_confirmation",
     "confirm_with": "Jive Tyler Revalde",
     "applied": "The 90% and 95% objectives are judged on the observed proportion. The Wilson "
                "95% interval is reported beside it and is not gated.",
     "why": "A 10-case family cannot have a Wilson lower bound at 0.90 (10/10 gives 0.72), so "
            "gating on the lower bound would make the profile unreachable at the required "
            "family size.",
     "if_changed": "Gating on the lower bound would need larger families or a lower target."},
    {"id": "no_success_rate_threshold", "status": "awaiting_confirmation",
     "confirm_with": "Jive Tyler Revalde",
     "applied": "No success-rate threshold is applied to the workload. Successes, failures "
                "and observed rates are reported; only a class whose every sample failed "
                "blocks.",
     "why": "No approved success-rate threshold exists and none is invented here.",
     "if_changed": "An approved threshold would be added to the profile and enforced by the "
                   "workload gate."},
)
RELEASE_DECISION_GAP = ("release_owner_decision: no named person has recorded the release "
                        "decision; this manifest decides nothing")
NOT_AUTHORIZED = ("evidence_met means the recorded evidence meets the selected profile. It "
                  "authorizes no release, spending, deployment or traffic switch; those need "
                  "their own named decisions.")


class ReadinessRefused(ValueError):
    """The inputs cannot be read as what they claim to be: say why."""


def canonical_digest(value: Any) -> str:
    """SHA-256 of the JSON value with sorted keys, so a saved copy has the same digest."""
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _gate(status: str, reasons: Sequence[str] = (), **extra) -> dict:
    return {"status": status, "blocking": status != MET, "reasons": list(reasons), **extra}


def _worst(problems: Sequence[tuple[str, str]]) -> tuple[str, list[str]]:
    """Fold (status, reason) problems into one status; fake evidence is named first."""
    if not problems:
        return MET, []
    order = (BREACHED, CONTRACT_ONLY, NOT_MET, INCOMPARABLE, NOT_MEASURED, INCONCLUSIVE)
    kinds = {k for k, _ in problems}
    status = next(k for k in order if k in kinds)
    return status, [reason for _, reason in problems]


def _fmt(frac: Mapping) -> str:
    if frac["value"] is None:
        return "n/a (0)"
    return (f"{frac['value']:.3f} ({frac['numerator']}/{frac['denominator']}, 95% CI "
            f"{frac['wilson_low']:.2f}-{frac['wilson_high']:.2f})")


def _measured_arm(report: Mapping, label: str) -> tuple[Optional[Mapping], Optional[str]]:
    arm = (report.get("arms") or {}).get(label)
    if arm is None:
        return None, f"the report has no arm {label!r}"
    if arm.get("status") != "measured":
        return None, f"arm {label} is {arm.get('status')}: {arm.get('reason')}"
    return arm, None


# --- comparison -----------------------------------------------------------------------


def _comparison(report: Mapping, label: str) -> dict:
    problems = []
    if report.get("mode") != "architecture":
        problems.append((INCOMPARABLE, f"the gating report is a {report.get('mode')} comparison; "
                         "only an architecture comparison at matched conditions can gate "
                         "readiness. Capability and model results are reported separately."))
    _, missing = _measured_arm(report, label)
    if missing:
        problems.append((NOT_MEASURED, missing))
    if report.get("enablement_blocked") is not False:
        problems += [(NOT_MET, f"the campaign report blocks enablement: {b}")
                     for b in report.get("blocking") or ()] or [
            (NOT_MET, "the campaign report does not state that enablement is unblocked")]
    for run in report.get("excluded_runs") or ():
        problems.append((INCONCLUSIVE, f"run {run.get('run_id')} was excluded from the campaign "
                         f"report: {run.get('reason')}"))
    status, reasons = _worst(problems)
    return _gate(status, reasons, candidate=label, mode=report.get("mode"),
                 comparison=report.get("comparison"))


# --- quality ---------------------------------------------------------------------------


def _metric(frac: Mapping, target: float) -> dict:
    meets = None if frac["value"] is None else frac["value"] >= target
    return {**frac, "target": target, "meets": meets}


def _count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _checked(frac: Any, where: str, problems: list) -> dict:
    """The fraction recomputed from its counts; a stated value that disagrees is not trusted."""
    frac = frac if isinstance(frac, Mapping) else {}
    num, den = frac.get("numerator"), frac.get("denominator")
    if not (_count(num) and _count(den) and num <= den):
        problems.append((NOT_MEASURED, f"{where}: {num}/{den} is not a valid count"))
        return _frac(0, 0)
    out = _frac(num, den)
    stated = frac.get("value")
    agrees = (stated is None if out["value"] is None else
              _number(stated) and abs(stated - out["value"]) < 1e-9)
    if not agrees:
        problems.append((INCOMPARABLE, f"{where}: the stated value {stated!r} is not "
                         f"{num}/{den}; the report's numbers do not agree with its counts"))
    return out


def _quality(report: Mapping, label: str) -> dict:
    arm, missing = _measured_arm(report, label)
    if arm is None:
        return _gate(NOT_MEASURED, [missing], targets=dict(TARGETS), repetitions=[],
                     families={}, missing_families=[], excluded_families={}, label=TARGET_LABEL)
    problems: list[tuple[str, str]] = []
    reps = arm["repetitions"]
    run_ids = [r["run_id"] for r in reps]
    repeated = sorted({i for i in run_ids if run_ids.count(i) > 1})
    if repeated:
        problems.append((INCOMPARABLE, f"repetitions {', '.join(repeated)} are listed more than "
                         "once; one run counts once"))
    fake = [r["run_id"] for r in reps if r.get("providers") != "real"]
    if fake:
        problems.append((CONTRACT_ONLY, f"{', '.join(fake)} used fake providers: a contract "
                         "check, never quality evidence"))
    if len(set(run_ids)) < MIN_REPETITIONS:
        problems.append((INCONCLUSIVE, f"{len(set(run_ids))} repetitions (distinct runs), fewer "
                         f"than the required {MIN_REPETITIONS}"))
    if report.get("min_examples", 0) < DEFAULT_MIN_EXAMPLES:
        problems.append((INCONCLUSIVE, f"family minimum {report.get('min_examples')} is below "
                         f"the scorer's {DEFAULT_MIN_EXAMPLES}; a lowered minimum cannot pass"))

    excluded = dict(EXCLUDED_FAMILIES)
    set_families = report.get("set_families") or ()
    if not set_families:
        problems.append((NOT_MEASURED, "the report does not list the set's families "
                         "(set_families), so no family can be required; a report built "
                         "before IR-741 cannot gate readiness"))
    required = [f for f in set_families if f not in EXCLUDED_FAMILIES]
    cases = arm.get("family_cases") or {}
    unlisted = sorted((set(cases) | set(arm.get("families") or {})) - set(set_families))
    if set_families and unlisted:
        problems.append((INCOMPARABLE, f"families {', '.join(unlisted)} were run but are not in "
                         "the report's set_families"))
    if set_families and not required:
        problems.append((NOT_MEASURED, "set_families names no family that can be required"))
    missing_families = [f for f in required if f not in cases]
    for family in missing_families:
        problems.append((INCONCLUSIVE, f"family {family} of the set was not run"))

    rep_rows = []
    for rep in reps:
        scores = rep["scores"]
        run_id = rep["run_id"]
        overall = {m: _checked(scores["overall"].get(m), f"{run_id} overall {m}", problems)
                   for m in METRICS}
        fams = {}
        for f, entry in scores["families"].items():
            reviewed = entry.get("reviewed")
            if not _count(reviewed):
                problems.append((NOT_MEASURED, f"{run_id}: family {f} reviewed count "
                                 f"{reviewed!r} is not a count"))
                continue
            if reviewed:
                fams[f] = {"reviewed": reviewed, **{
                    m: _metric(_checked(entry.get(m), f"{run_id} family {f} {m}", problems),
                               TARGETS[m]) for m in METRICS}}
        rep_rows.append({"run_id": run_id, "providers": rep.get("providers"),
                         "overall": {m: _metric(overall[m], TARGETS[m]) for m in METRICS},
                         "families": fams})
        for m in METRICS:
            frac = overall[m]
            if frac["denominator"] == 0:
                problems.append((INCONCLUSIVE, f"{run_id}: {m} has no denominator"))
            elif frac["value"] < TARGETS[m]:
                problems.append((NOT_MET, f"{run_id}: overall {m} {_fmt(frac)} is below "
                                 f"{TARGETS[m]:g}"))

    families = {}
    for family in required:
        own: list[tuple[str, str]] = []
        distinct = len(set(cases.get(family, ())))
        ran_ids = {r["run_id"] for r in rep_rows if family in r["families"]}
        ran = [r for r in rep_rows if family in r["families"]]
        if family in cases and distinct < DEFAULT_MIN_EXAMPLES:
            own.append((INCONCLUSIVE, f"family {family} has {distinct} distinct cases, fewer "
                        f"than the required {DEFAULT_MIN_EXAMPLES}"))
        if family in cases and len(ran_ids) < MIN_REPETITIONS:
            own.append((INCONCLUSIVE, f"family {family} was scored in {len(ran_ids)} distinct "
                        f"repetitions, fewer than the required {MIN_REPETITIONS}"))
        for rep in ran:
            entry = rep["families"][family]
            if entry["reviewed"] < DEFAULT_MIN_EXAMPLES:
                own.append((INCONCLUSIVE, f"{rep['run_id']}: family {family} has "
                            f"{entry['reviewed']} reviewed cases, fewer than the required "
                            f"{DEFAULT_MIN_EXAMPLES}"))
            for m in METRICS:
                frac = entry[m]
                if not frac["denominator"]:
                    own.append((INCONCLUSIVE, f"{rep['run_id']}: family {family} {m} has no "
                                "denominator"))
                elif frac["value"] < TARGETS[m]:
                    own.append((NOT_MET, f"{rep['run_id']}: family {family} {m} {_fmt(frac)} "
                                f"is below {TARGETS[m]:g}"))
        status, reasons = _worst(own)
        if family not in cases:
            status, reasons = INCONCLUSIVE, [f"family {family} of the set was not run"]
        families[family] = {"status": status, "distinct_cases": distinct,
                            "repetitions": len(ran_ids), "reasons": reasons}
        problems += own
    status, reasons = _worst(problems)
    return _gate(status, reasons, targets=dict(TARGETS), label=TARGET_LABEL,
                 repetitions=rep_rows, families=families, required_families=required,
                 missing_families=missing_families, excluded_families=excluded)


# --- safety and human review -----------------------------------------------------------


def _safety(report: Mapping, label: str) -> dict:
    arm, missing = _measured_arm(report, label)
    if arm is None:
        return _gate(NOT_MEASURED, [missing], breaches=[])
    breaches = [dict(b) for b in arm["access_breaches"]]
    if breaches:
        return _gate(BREACHED, [f"access breach in {b['conversation']} ({b['run_id']}); no "
                                "average offsets it" for b in breaches], breaches=breaches)
    return _gate(MET, [], breaches=[], note=ZERO_BREACH_NOTE)


def _human_review(report: Mapping, label: str) -> tuple[dict, list[str]]:
    arm, missing = _measured_arm(report, label)
    if arm is None:
        return _gate(NOT_MEASURED, [missing]), [missing]
    gaps = list(report.get("not_counted_reasons") or ())
    if not report.get("counted"):
        gaps.append("the report was not built as a counted report: packets, reviewer kind, "
                    "two reviews per conversation and a locked corpus were not all checked")
    for family, entry in arm["families"].items():
        if entry["status"] == "unreviewed":
            gaps.append(f"family {family}: unreviewed cases {', '.join(entry['not_reviewed'])}")
    gaps += [f"{s}: one review, not two" for s in arm["single_reviewed"]]
    gate = _gate(MET if not gaps else NOT_MET, gaps)
    return gate, gaps


# --- baseline --------------------------------------------------------------------------


def _as_manifest(conditions: Mapping) -> dict:
    models = list(conditions.get("models") or ())
    return {"corpus_snapshot_digest": conditions.get("corpus_snapshot_digest"),
            "model_ids": {m: m for m in models}, "data_policy": conditions.get("data_policy"),
            "limits": conditions.get("limits"), "set_digests": conditions.get("set_digests"),
            "rubric_version": conditions.get("rubric_version"),
            "cache_state": "+".join(conditions.get("cache_states") or ())}


def _pooled(arm: Mapping) -> dict:
    out = {}
    for m in METRICS:
        rows = [r["scores"]["overall"][m] for r in arm["repetitions"]]
        out[m] = _frac(sum(r["numerator"] for r in rows), sum(r["denominator"] for r in rows))
    return out


def _baseline(report: Mapping, label: str, baseline: Optional[Mapping]) -> dict:
    if not baseline:
        return _gate(NOT_MEASURED, ["no frozen baseline was supplied"], metrics=None)
    base = baseline.get("report") or {}
    digest = canonical_digest(base)
    arm_label = baseline.get("arm")
    # The pin is the operator's --baseline-sha256: it proves the file is unchanged, not that
    # the right file was frozen. Recorded so a reader sees where it came from.
    own = dict(baseline_sha256=digest, baseline_arm=arm_label, metrics=None,
               pin_source="operator_argument")
    expected = baseline.get("expected_sha256")
    if not expected:
        return _gate(NOT_MEASURED, ["the baseline is not pinned: expected_sha256 of the frozen "
                                    "baseline report is required"], **own)
    if expected != digest:
        return _gate(INCOMPARABLE, [f"the baseline report's digest {digest[:12]} does not match "
                                    f"the frozen digest {str(expected)[:12]}"], **own)
    if base.get("mode") != "architecture":
        return _gate(INCOMPARABLE, [f"the baseline is a {base.get('mode')} report, not an "
                                    "architecture comparison"], **own)
    barm, missing = _measured_arm(base, arm_label)
    if barm is None:
        return _gate(NOT_MEASURED, [f"baseline: {missing}"], **own)
    if not base.get("counted"):
        return _gate(NOT_MEASURED, ["the baseline report is not a counted report, so its "
                                    "numbers are not review-backed"], **own)
    carm, missing = _measured_arm(report, label)
    if carm is None:
        return _gate(NOT_MEASURED, [missing], **own)
    same_run = {r["run_id"] for r in barm["repetitions"]} & {
        r["run_id"] for r in carm["repetitions"]}
    if (arm_label == label or same_run or
            (barm.get("git_commit"), barm.get("engine_version"))
            == (carm.get("git_commit"), carm.get("engine_version"))):
        return _gate(INCOMPARABLE, ["the baseline is the candidate itself (same arm, runs, or "
                                    "commit and engine); a candidate cannot be its own "
                                    "baseline"], **own)
    if "conditions" not in barm or "conditions" not in carm:
        return _gate(INCOMPARABLE, ["a report that does not record its conditions cannot be "
                                    "matched"], **own)
    weak = []
    for who, conditions in (("baseline", barm["conditions"]), (label, carm["conditions"])):
        weak += [f"{who} records no {k}; two unrecorded conditions are not equal conditions"
                 for k in ("corpus_snapshot_digest", "set_digests", "data_policy", "limits")
                 if not conditions.get(k)]
    fake = [r["run_id"] for r in barm["repetitions"] if r.get("providers") != "real"]
    if fake:
        weak.append(f"baseline repetitions {', '.join(fake)} used fake providers: a contract "
                    "check is not a baseline")
    if len(barm["repetitions"]) < MIN_REPETITIONS:
        weak.append(f"the baseline has {len(barm['repetitions'])} repetitions, fewer than the "
                    f"required {MIN_REPETITIONS}")
    if weak:
        return _gate(INCOMPARABLE, weak, **own)
    problems = mismatches([("baseline", _as_manifest(barm["conditions"])),
                           (label, _as_manifest(carm["conditions"]))], "architecture")
    if problems:
        return _gate(INCOMPARABLE, problems, **own)
    candidate, frozen_base = _pooled(carm), _pooled(barm)
    metrics, problems = {}, []
    for m in METRICS:
        c, b = candidate[m], frozen_base[m]
        regressed = c["value"] is not None and b["value"] is not None and c["value"] < b["value"]
        metrics[m] = {"candidate": c, "baseline": b, "regressed": regressed}
        if c["value"] is None or b["value"] is None:
            problems.append((NOT_MEASURED, f"{m} has no denominator in the candidate or the "
                             "baseline"))
        elif regressed:
            problems.append((NOT_MET, f"{m} {c['numerator']}/{c['denominator']} "
                             f"({c['value']:.3f}) is below the frozen baseline "
                             f"{b['numerator']}/{b['denominator']} ({b['value']:.3f})"))
    status, reasons = _worst(problems)
    return _gate(status, reasons, **{**own, "metrics": metrics})


# --- recorded scenario evidence (IR-608) ------------------------------------------------

#: The accessibility surfaces a browser exercise must have measured and passed.
ACCESSIBILITY_CHECKS = ("keyboard", "accessible_summary", "mobile")


#: What a commit that says nothing looks like (``git describe`` answers this when it cannot).
NO_COMMIT = (None, "", "unknown")


def _dirty(commit: Any) -> bool:
    return str(commit).endswith("-dirty")


def _provenance(row: Mapping, commit: Optional[str], what: str) -> tuple[str, list]:
    """Was this evidence produced at the candidate's commit? Never inferred.

    ``verified`` only when the row records a commit and it equals the candidate's. A row that
    records none is ``unverified``, which blocks; a different commit is ``mismatch``. A dirty
    tree (``<sha>-dirty``) names no reproducible source, so it is never verified, even when
    the candidate is the same dirty tree.
    """
    recorded = row.get("git_commit")
    if recorded in NO_COMMIT:
        return "unverified", [(NOT_MEASURED, f"{what} records no commit, so its provenance is "
                               "unverified; a commit is never inferred for it")]
    if commit in NO_COMMIT:
        return "unverified", [(NOT_MEASURED, f"the candidate's commit is unknown, so the {what} "
                               "cannot be tied to it")]
    if recorded != commit:
        return "mismatch", [(INCOMPARABLE, f"the {what} ran at {recorded}, not at the "
                             f"candidate's {commit}")]
    if _dirty(commit):
        return "unverified", [(NOT_MEASURED, f"the {what} and the candidate were both built "
                               f"from the dirty tree {commit}, which no commit reproduces")]
    return "verified", []


def scenario_rows(run: Optional[Mapping]) -> dict:
    """The IR-608 ``scenarios`` rows of an ``eval_scenarios`` run file.

    The producer records the tested commit once, on the run, not on each suite row. A row
    without a commit of its own takes the run's, marked ``git_commit_source: run_file``, so the
    provenance the producer did record reaches the gate. A run that records none gives its rows
    none; nothing is filled in.
    """
    if not isinstance(run, Mapping):
        return {}
    rows = run.get("scenarios", run) if isinstance(run.get("scenarios"), Mapping) else run
    top = run.get("git_commit") if rows is not run else None
    out = {}
    for name, row in rows.items():
        if isinstance(row, Mapping) and top not in NO_COMMIT and not row.get("git_commit"):
            row = {**row, "git_commit": top, "git_commit_source": "run_file"}
        out[name] = row
    return out


def _suite(row: Optional[Mapping], name: str, commit: Optional[str] = None) -> dict:
    """An IR-608 test suite as evidence: it must have run, not skipped, passed, be the kind of
    suite the claim needs, and carry the candidate's commit."""
    if not row:
        return _gate(NOT_MEASURED, [f"no IR-608 {name} evidence was supplied"])
    kind, _ = SUITES[name]
    if row.get("kind") != kind:
        return _gate(CONTRACT_ONLY, [f"{name} evidence is of kind {row.get('kind')!r}; the "
                                     f"claim needs {kind!r}"], kind=row.get("kind"))
    provenance, problems = _provenance(row, commit, f"{name} evidence")
    if row.get("status") != "measured":
        problems.append((NOT_MEASURED, f"{name} was not measured: {row.get('reason')}"))
    elif not (_count(row.get("tests")) and row["tests"] > 0):
        problems.append((NOT_MEASURED, f"{name} records {row.get('tests')!r} tests, not a "
                         "positive count"))
    if row.get("skipped"):
        problems.append((NOT_MEASURED, f"{row['skipped']} of the {name} tests were skipped"))
    if row.get("errors"):
        problems.append((NOT_MEASURED, f"{row['errors']} of the {name} tests errored"))
    if row.get("failed"):
        problems.append((NOT_MET, f"{row['failed']} failed of {row.get('tests')} {name} tests"))
    elif row.get("passed") is not True and not problems:
        problems.append((NOT_MET, f"{name} did not pass"))
    status, reasons = _worst(problems)
    return _gate(status, reasons, kind=kind, tests=row.get("tests"), provenance=provenance,
                 git_commit=row.get("git_commit"),
                 git_commit_source=row.get("git_commit_source", "row"))


def _browser(row: Optional[Mapping], commit: Optional[str]) -> dict:
    if not row:
        return _gate(NOT_MEASURED, ["no named browser exercise was supplied; jsdom results "
                                    "are not browser evidence"])
    if row.get("kind") != "manual_browser":
        return _gate(CONTRACT_ONLY, [f"browser evidence is of kind {row.get('kind')!r}, not a "
                                     "named manual browser exercise"])
    checks = row.get("checks") or {}
    problems = []
    if not _filled(row.get("operator")):
        problems.append((NOT_MEASURED, "the browser exercise names no operator; it must be a "
                         "named person's"))
    for name in BROWSER_CHECKS:
        check = checks.get(name) or {}
        tag = " (accessibility)" if name in ACCESSIBILITY_CHECKS else ""
        if check.get("status") != "measured":
            problems.append((NOT_MEASURED, f"browser check {name} was not measured{tag}"))
        elif check.get("passed") is not True:
            problems.append((NOT_MET, f"browser check {name} failed{tag}"))
        elif not (check.get("evidence_ref") or check.get("evidence_recorded") is True):
            problems.append((NOT_MEASURED, f"browser check {name} cites no evidence_ref{tag}"))
    provenance, found = _provenance(row, commit, "browser exercise")
    problems += found
    status, reasons = _worst(problems)
    return _gate(status, reasons, kind="manual_browser", operator=row.get("operator"),
                 git_commit=row.get("git_commit"), provenance=provenance)


# --- the declared workload, the authorized profile and live collection -------------------

MEASUREMENT_SCHEMA = "workload-measurement-1"
CLASSES = ("ordinary", "deep", "ingestion")
#: Only these classes are answered questions; ingestion is load, reported apart.
TASK_CLASSES = ("ordinary", "deep")
REAL_ENVIRONMENT = {"database": "postgresql", "workers": "independent_processes"}
WORKLOAD_FIELDS = ("declared_at", "declared_by", "cache_state", "corpus_snapshot_digest",
                   "model_ids", "data_policy")
PROFILE_AUTHORIZATION = ("authorized_by", "reference", "date")
PROFILE_LIMITS = {"latency": ("ordinary_p95_ms", "deep_p95_ms"),
                  "cost": ("cost_per_successful_task_usd",),
                  "resources": ("memory_mb", "connections", "lock_wait_ms")}
#: ADR-049 §12: deadlines, token/cost/attempt/concurrency caps. None has a default or an
#: approved value; an operator states each (the names follow the runtime's RUNS_* settings).
CAP_KEYS = ("deadline_seconds", "deep_deadline_seconds", "max_attempts", "max_input_tokens",
            "max_output_tokens", "max_cost_usd", "max_queued", "deep_concurrency",
            "worker_concurrency", "campaign_cost_usd")


#: No success-rate threshold has been approved, so none is applied; the observed rate is
#: reported for a reader to judge. Only a class in which every sample failed blocks.
SUCCESS_RATE_POLICY = ("no success-rate threshold is approved, so none is enforced: observed "
                       "rates are reported and only a class whose every sample failed blocks")


def _positive(value: Any) -> bool:
    """A finite positive number: an infinite cap is no cap."""
    return _number(value) and value > 0


def _filled(value: Any) -> bool:
    return bool(str(value or "").strip())


def _declaration_missing(workload: Optional[Mapping], profile: Optional[Mapping]) -> list[str]:
    missing: list[str] = []
    if not workload:
        missing.append("workload")
    else:
        missing += [f"workload.{k}" for k in WORKLOAD_FIELDS if not workload.get(k)]
        if not _positive(workload.get("concurrency")):
            missing.append("workload.concurrency")
        mix = workload.get("mix")
        if not isinstance(mix, Mapping):
            missing.append("workload.mix")
        else:
            missing += [f"workload.mix.{c}" for c in CLASSES if not _positive(mix.get(c))]
    if not profile:
        missing.append("profile")
    else:
        missing += [f"profile.{k}" for k in PROFILE_AUTHORIZATION if not _filled(profile.get(k))]
        for section, keys in PROFILE_LIMITS.items():
            own = profile.get(section) if isinstance(profile.get(section), Mapping) else {}
            missing += [f"profile.{section}.{k}" for k in keys if not _positive(own.get(k))]
        caps = profile.get("caps") if isinstance(profile.get("caps"), Mapping) else {}
        missing += [f"profile.caps.{k}" for k in CAP_KEYS if not _positive(caps.get(k))]
    return missing


def collection_preflight(workload: Optional[Mapping], profile: Optional[Mapping],
                         approvals: Optional[Mapping]) -> dict:
    """May paid collection begin? Every missing declaration, cap or approval is named.

    Nothing here supplies a default or approves anything: it only reports what a person has
    not yet declared, authorized or approved.
    """
    unrecorded = _declaration_missing(workload, profile)
    unrecorded += [f"approvals.{k}" for k in approvals_status(approvals)["unrecorded"]]
    return {"allowed": not unrecorded, "unrecorded": unrecorded}


def _authorization(workload, profile, approvals) -> dict:
    pre = collection_preflight(workload, profile, approvals)
    if pre["allowed"]:
        return _gate(MET, [], approvals=approvals_status(approvals))
    return _gate(NOT_MEASURED, [f"live collection is not authorized; {m} is not recorded"
                                for m in pre["unrecorded"]],
                 approvals=approvals_status(approvals))


def _when(text: Any) -> Optional[datetime]:
    """A timezone-aware instant, or None: a naive time cannot be ordered against one."""
    try:
        value = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return value if value.tzinfo is not None else None


def _p95(values: Sequence[float]) -> Optional[float]:
    return percentile(list(values), 0.95)


SAMPLE_NUMBERS = ("queue_ms", "total_ms", "tool_ms", "model_ms")
RESOURCE_FIELDS = ("peak_memory_mb", "peak_connections", "lock_waits", "max_lock_wait_ms")


def _number(value: Any) -> bool:
    """A finite non-negative number; NaN, infinity and booleans are not measurements."""
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= 0)


def validate_measurement(measurement: Any, *, limit: int = 20) -> list[str]:
    """Structural defects of a ``workload-measurement-1`` file; empty when it is well formed.

    This is the contract a producer (IR-755) writes to. It checks shape only: whether the
    numbers are good enough is the ``workload`` and ``cost`` gates' business, and a well-formed
    file is neither evidence nor a pass. At most ``limit`` problems are listed.
    """
    if not isinstance(measurement, Mapping):
        return ["the measurement is not a JSON object"]
    out: list[str] = []

    def bad(message):
        out.append(message)

    if measurement.get("schema_version") != MEASUREMENT_SCHEMA:
        bad(f"schema_version must be {MEASUREMENT_SCHEMA!r}")
    if not _filled(measurement.get("run_id")):
        bad("run_id must be a non-empty string")
    if not _filled(measurement.get("git_commit")):
        bad("git_commit must name the commit the measured runtime was built from")
    if measurement.get("providers") not in ("real", "fake"):
        bad("providers must be 'real' or 'fake'")
    env = measurement.get("environment")
    if not isinstance(env, Mapping) or not _filled(env.get("database")) \
            or not _filled(env.get("workers")):
        bad("environment must name database and workers")
    if _when(measurement.get("started_at")) is None:
        bad("started_at must be a timezone-aware ISO 8601 time")
    if not _positive(measurement.get("concurrency")):
        bad("concurrency must be a positive number")
    digest = measurement.get("workload_sha256")
    if not (isinstance(digest, str) and len(digest) == 64
            and all(c in "0123456789abcdef" for c in digest)):
        bad("workload_sha256 must be the 64-hex canonical digest of the declared workload")
    res = measurement.get("resources")
    if not isinstance(res, Mapping):
        bad("resources must be an object")
    else:
        bad_res = [f for f in RESOURCE_FIELDS if not _number(res.get(f))]
        if bad_res:
            bad(f"resources.{', resources.'.join(bad_res)} must be non-negative numbers")
    samples = measurement.get("samples")
    if not isinstance(samples, list):
        bad("samples must be a list")
        samples = []
    for i, s in enumerate(samples):
        if not isinstance(s, Mapping):
            bad(f"samples[{i}] is not an object")
            continue
        cls = s.get("class")
        if cls not in CLASSES:
            bad(f"samples[{i}].class must be one of {', '.join(CLASSES)}")
        if not _filled(s.get("outcome")):
            bad(f"samples[{i}]'s outcome must be a non-empty string")
        if not isinstance(s.get("usage_reported"), bool):
            bad(f"samples[{i}].usage_reported must be true or false")
        cost = s.get("cost_usd")
        if cost is not None and not _number(cost):
            bad(f"samples[{i}].cost_usd must be a non-negative number or null")
        for f in SAMPLE_NUMBERS:
            required = cls in TASK_CLASSES and f in ("queue_ms", "total_ms")
            if f in s and s[f] is None and not required:
                continue
            if (required or f in s) and not _number(s.get(f)):
                bad(f"samples[{i}].{f} must be a non-negative number")
        if _number(s.get("queue_ms")) and _number(s.get("total_ms")) \
                and s["total_ms"] < s["queue_ms"]:
            bad(f"samples[{i}].total_ms must include queue_ms (total_ms >= queue_ms)")
        if len(out) >= limit:
            out.append("... further problems not listed")
            break
    return out[:limit + 1]


def _prerequisites(workload, profile, measurement) -> list[tuple[str, str]]:
    out = []
    pre = _declaration_missing(workload, profile)
    if pre:
        out.append((NOT_MEASURED, "the declared workload or authorized profile is incomplete "
                    f"({', '.join(pre)}); a measurement cannot be judged against nothing"))
    if not measurement:
        out.append((NOT_MEASURED, "no workload measurement was supplied"))
    elif measurement.get("schema_version") != MEASUREMENT_SCHEMA:
        out.append((NOT_MEASURED, f"measurement schema {measurement.get('schema_version')!r} "
                    f"is not {MEASUREMENT_SCHEMA!r}"))
    else:
        defects = validate_measurement(measurement)
        if defects:
            out.append((NOT_MEASURED, "the measurement is not a well-formed "
                        f"{MEASUREMENT_SCHEMA}: {'; '.join(defects)}"))
    return out


def _real(measurement: Mapping) -> list[tuple[str, str]]:
    out = []
    if measurement.get("providers") != "real":
        out.append((CONTRACT_ONLY, f"providers were {measurement.get('providers')!r}: a "
                    "contract check, never measured capacity or cost"))
    if measurement.get("environment") != REAL_ENVIRONMENT:
        out.append((CONTRACT_ONLY, f"environment {measurement.get('environment')!r} is not "
                    "real PostgreSQL with independent worker processes"))
    return out


def _same_conditions(workload: Mapping, arm: Optional[Mapping]) -> list[tuple[str, str]]:
    """Was the workload declared under the conditions the candidate's campaign ran under?"""
    if arm is None:
        return [(NOT_MEASURED, "no measured candidate arm to tie the workload to")]
    c = arm.get("conditions") or {}
    differ = []
    if workload.get("corpus_snapshot_digest") != c.get("corpus_snapshot_digest"):
        differ.append("corpus")
    models = workload.get("model_ids")
    if sorted(set((models or {}).values()) if isinstance(models, Mapping) else ()) \
            != sorted(c.get("models") or ()):
        differ.append("models")
    if workload.get("data_policy") != c.get("data_policy"):
        differ.append("data policy")
    if [workload.get("cache_state")] != list(c.get("cache_states") or ()):
        differ.append("cache state")
    return [(INCOMPARABLE, f"the workload's {', '.join(differ)} differ from the conditions the "
             "candidate's campaign ran under")] if differ else []


def _measurement_problems(report, label, workload, profile, measurement):
    """Every reason the measurement cannot be judged as this candidate's; ``ok`` is whether
    it is well formed enough to read its numbers at all."""
    problems = _prerequisites(workload, profile, measurement)
    if problems:
        return problems, False
    problems = _real(measurement)
    if measurement["workload_sha256"] != canonical_digest(workload):
        problems.append((INCOMPARABLE, "the measurement is of a workload other than the "
                         "declared one (digest differs)"))
    arm, _ = _measured_arm(report, label)
    problems += _same_conditions(workload, arm)
    _, found = _provenance(measurement, (arm or {}).get("git_commit"), "workload measurement")
    problems += found
    return problems, True


def _workload(report, label, workload, profile, measurement) -> dict:
    problems, ok = _measurement_problems(report, label, workload, profile, measurement)
    if not ok:
        return _gate(*_worst(problems), classes={}, resources=None)
    # validate_measurement has already required a start time, a positive concurrency and a
    # queue-inclusive total on every task sample.
    declared = _when(workload["declared_at"])
    if declared is None:
        problems.append((NOT_MEASURED, "the workload's declared_at is not a timezone-aware "
                         "time"))
    elif _when(measurement["started_at"]) < declared:
        problems.append((NOT_MET, "the measurement started before the workload was declared; "
                         "a workload is declared before collection, not after"))
    if measurement["concurrency"] < workload["concurrency"]:
        problems.append((INCOMPARABLE, f"the measurement ran at concurrency "
                         f"{measurement['concurrency']}, below the declared "
                         f"{workload['concurrency']}"))
    samples = measurement["samples"]
    classes = {}
    for cls in CLASSES:
        own = [s for s in samples if s["class"] == cls]
        declared_n = workload["mix"][cls]
        if len(own) < declared_n:
            problems.append((INCONCLUSIVE, f"class {cls} has {len(own)} samples, fewer than the "
                             f"declared {declared_n}"))
        successes = sum(s["outcome"] == "success" for s in own)
        row = {"n": len(own), "declared": declared_n, "successes": successes,
               "failures": len(own) - successes,
               "observed_success_rate": successes / len(own) if own else None}
        if own and row["failures"] == len(own):
            problems.append((NOT_MET, f"every {cls} sample failed"
                             + ("; a latency figure over failures alone says nothing about "
                                "answered tasks" if cls in TASK_CLASSES else "")))
        if cls in TASK_CLASSES:
            untimed = [s for s in own if not (_number(s.get("tool_ms"))
                                              and _number(s.get("model_ms")))]
            if untimed:
                problems.append((NOT_MEASURED, f"{len(untimed)} {cls} samples record no tool or "
                                 "model time; both are required measures"))
            cap = profile["latency"][f"{cls}_p95_ms"]
            timed = [s for s in own if s not in untimed]
            row.update(
                total_p95_ms=_p95([s["total_ms"] for s in own]),
                queue_p95_ms=_p95([s["queue_ms"] for s in own]),
                tool_p95_ms=_p95([s["tool_ms"] for s in timed]),
                model_p95_ms=_p95([s["model_ms"] for s in timed]), cap_p95_ms=cap)
            if own and row["total_p95_ms"] > cap:
                problems.append((NOT_MET, f"{cls} queue-inclusive p95 {row['total_p95_ms']} ms "
                                 f"exceeds the authorized {cap} ms"))
        classes[cls] = row
    res = measurement["resources"]
    limits = profile["resources"]
    for field, cap_key, word in (("peak_memory_mb", "memory_mb", "memory"),
                                 ("peak_connections", "connections", "connections"),
                                 ("max_lock_wait_ms", "lock_wait_ms", "lock wait")):
        if res[field] > limits[cap_key]:
            problems.append((NOT_MET, f"peak {word} {res[field]} exceeds the authorized "
                             f"{limits[cap_key]}"))
    status, reasons = _worst(problems)
    return _gate(status, reasons, run_id=measurement.get("run_id"), classes=classes,
                 success_rate_policy=SUCCESS_RATE_POLICY,
                 resources={k: res.get(k) for k in RESOURCE_FIELDS},
                 environment=measurement.get("environment"))


def _campaign_cost(arm: Mapping, cap: float, problems: list) -> dict:
    out = {}
    unknown = arm["spend"].get("unknown_cache")
    if unknown != 0:
        problems.append((INCONCLUSIVE, f"{unknown} campaign rows record no cold or warm cache "
                         "state, so their spend is in neither group and is not bounded"))
    for cache in ("cold", "warm"):
        g = arm["spend"][cache]
        if not g["conversations"]:
            continue
        conservative = g["reported_usd"] + g["unreported_reserved_usd"]
        won = g["successes"]
        out[cache] = {"conversations": g["conversations"], "cost_status": g["cost_status"],
                      "conservative_usd": conservative, "successes": won,
                      "conservative_per_success": conservative / won if won else None,
                      "turns_missing_usage": g["turns_missing_usage"],
                      "attempts_missing_cost": g["attempts_missing_cost"]}
        if g["cost_status"] != "complete":
            problems.append((INCONCLUSIVE, f"campaign {cache} spend has "
                             f"{g['turns_missing_usage']} turns with missing usage and "
                             f"{g['attempts_missing_cost']} attempts with no cost; the figure "
                             "is an upper bound, not a measurement"))
        if won and conservative / won > cap:
            problems.append((NOT_MET, f"campaign {cache} conservative cost per success "
                             f"${conservative / won:.4f} exceeds the authorized ${cap:g}"))
    if not out:
        problems.append((NOT_MEASURED, "the campaign records no cold or warm spend to judge"))
    return out


def _cost(report: Mapping, label: str, workload, profile, measurement) -> dict:
    cap = ((profile or {}).get("cost") or {}).get("cost_per_successful_task_usd")
    if not measurement:
        return _gate(NOT_MEASURED, ["no workload measurement was supplied"],
                     cost_per_successful_task=None)
    if not _positive(cap):
        return _gate(NOT_MEASURED, ["no authorized cost-per-successful-task cap in the profile"],
                     cost_per_successful_task=None)
    problems, ok = _measurement_problems(report, label, workload, profile, measurement)
    if not ok:
        return _gate(*_worst(problems), cost_per_successful_task=None)
    tasks = [s for s in measurement["samples"] if s["class"] in TASK_CLASSES]
    ingestion = [s for s in measurement["samples"] if s["class"] == "ingestion"]
    total, unknown, unbounded = 0.0, 0, 0
    for s in tasks:
        if s.get("cost_usd") is None:
            unbounded += 1
            continue
        total += s["cost_usd"]
        unknown += s["usage_reported"] is not True
    successes = sum(s["outcome"] == "success" for s in tasks)
    if unbounded:
        problems.append((NOT_MEASURED, f"{unbounded} samples have no usage and no reservation, "
                         "so cost cannot be bounded"))
    if unknown:
        problems.append((INCONCLUSIVE, f"{unknown} samples have unknown usage, counted at their "
                         "reservation; the total is an upper bound"))
    uncosted_ingestion = sum(s.get("cost_usd") is None for s in ingestion)
    if uncosted_ingestion:
        problems.append((NOT_MEASURED, f"{uncosted_ingestion} ingestion samples record no cost; "
                         "ingestion spend is reported, so it must be bounded"))
    per_success = None
    if not successes:
        problems.append((INCONCLUSIVE, "no successful tasks: cost per successful task is "
                         "undefined"))
    elif not unbounded:
        per_success = total / successes
        if per_success > cap:
            problems.append((NOT_MET, f"cost per successful task ${per_success:.4f} (failures "
                             f"and unknown usage included) exceeds the authorized ${cap:g}"))
    arm, _ = _measured_arm(report, label)
    campaign = {}
    if arm is not None:
        if any(r.get("providers") != "real" for r in arm["repetitions"]):
            problems.append((CONTRACT_ONLY, "the campaign ran with fake providers: its spend "
                             "is not measured"))
        campaign = _campaign_cost(arm, cap, problems)
    status, reasons = _worst(problems)
    return _gate(status, reasons, total_usd=total, successes=successes,
                 failures=len(tasks) - successes, unknown_usage_samples=unknown,
                 unbounded_samples=unbounded, cost_per_successful_task=per_success,
                 cap_per_successful_task_usd=cap, campaign=campaign,
                 ingestion_usd=(None if uncosted_ingestion
                                else sum(s["cost_usd"] for s in ingestion)))


# --- separate capability and model results ---------------------------------------------


def _separate(report: Optional[Mapping], mode: str) -> Optional[dict]:
    if report is None:
        return None
    if report.get("mode") != mode:
        raise ReadinessRefused(f"the {mode} result must be a {mode}-mode campaign report, not "
                               f"{report.get('mode')!r}")
    labels = {}
    for label, arm in report["arms"].items():
        if arm.get("status") != "measured":
            labels[label] = {"status": arm.get("status"), "reason": arm.get("reason")}
            continue
        labels[label] = {"status": "measured", "engine_version": arm["engine_version"],
                         "git_commit": arm["git_commit"], "allowance": arm["allowance"],
                         "conditions": arm.get("conditions"),
                         "repetitions": len(arm["repetitions"]), "aggregate": _pooled(arm),
                         "access_breaches": len(arm["access_breaches"])}
    note = (CAPABILITY_NOTE if mode == "capability" else
            "Models are compared under one architecture; a model gain is never credited to "
            "the architecture.")
    return {"mode": mode, "comparison": report.get("comparison"), "labels": labels,
            "credited_to_architecture": False, "gates_affected": False, "note": note}


# --- manifest --------------------------------------------------------------------------

#: Which inputs each gate rests on; a gate cannot be met without a recorded reference to them.
GATE_SOURCES = {
    "comparison": ("report",), "quality": ("report",), "safety": ("report",),
    "human_review": ("report",), "baseline": ("baseline",),
    "access_disclosure": ("scenarios",), "postgres_workers": ("scenarios",),
    "browser_accessibility": ("scenarios",),
    "authorization": ("workload", "profile", "approvals"),
    "workload": ("workload", "profile", "measurements"),
    "cost": ("measurements", "profile", "report"),
}


def _attach_references(gates: dict, references: Optional[Mapping]) -> None:
    refs = references or {}
    for name, g in gates.items():
        sources = GATE_SOURCES.get(name, ())
        g["evidence"] = [{"name": s, "path": refs[s]["path"], "sha256": refs[s]["sha256"]}
                         for s in sources
                         if refs.get(s, {}).get("path") and refs.get(s, {}).get("sha256")]
        missing = [s for s in sources if s not in {e["name"] for e in g["evidence"]}]
        if missing and g["status"] == MET:
            g.update(status=NOT_MEASURED, blocking=True,
                     reasons=[f"no evidence reference recorded for {', '.join(missing)}"])


def _blocking(gates: Mapping[str, Mapping]) -> list[str]:
    out = []
    for name, g in gates.items():
        if g["status"] != MET:
            out += [f"{name} [{g['status']}]: {r}" for r in g["reasons"]] or [
                f"{name} [{g['status']}]"]
    return out


def build_readiness(report: Mapping, *, candidate: str = "runtime",
                    baseline: Optional[Mapping] = None, scenarios: Optional[Mapping] = None,
                    workload: Optional[Mapping] = None, profile: Optional[Mapping] = None,
                    measurements: Optional[Mapping] = None, approvals: Optional[Mapping] = None,
                    references: Optional[Mapping] = None, capability: Optional[Mapping] = None,
                    model: Optional[Mapping] = None) -> dict:
    """The readiness manifest for ``candidate`` in an architecture campaign ``report``."""
    review_gate, gaps = _human_review(report, candidate)
    arm = (report.get("arms") or {}).get(candidate) or {}
    scenarios = scenarios or {}
    gates = {
        "comparison": _comparison(report, candidate),
        "quality": _quality(report, candidate),
        "safety": _safety(report, candidate),
        "human_review": review_gate,
        "baseline": _baseline(report, candidate, baseline),
        "access_disclosure": _suite(scenarios.get("access_and_recovery"),
                                    "access_and_recovery", arm.get("git_commit")),
        "postgres_workers": _suite(scenarios.get("durability"), "durability",
                                   arm.get("git_commit")),
        "browser_accessibility": _browser(scenarios.get("browser"), arm.get("git_commit")),
        "authorization": _authorization(workload, profile, approvals),
        "workload": _workload(report, candidate, workload, profile, measurements),
        "cost": _cost(report, candidate, workload, profile, measurements),
    }
    separate = {"capability": _separate(capability, "capability"),
                "model": _separate(model, "model")}
    _attach_references(gates, references)
    blocking = _blocking(gates)
    manifest = {
        "schema_version": SCHEMA_VERSION, "issue": ISSUE, "set_id": report.get("set_id"),
        "candidate": {"label": candidate, "engine_version": arm.get("engine_version"),
                      "git_commit": arm.get("git_commit"), "identity": arm.get("identity"),
                      "allowance": arm.get("allowance")},
        "corpus": report.get("corpus"),
        "live_collection": collection_preflight(workload, profile, approvals),
        "status": BLOCKED if blocking else READY, "blocking": blocking, "gates": gates,
        "human_review_gaps": [*gaps, RELEASE_DECISION_GAP],
        "inputs": {k: dict(v) for k, v in sorted((references or {}).items())},
        "build": {"candidate": candidate, "baseline_arm": (baseline or {}).get("arm"),
                  "baseline_sha256": (baseline or {}).get("expected_sha256")},
        "policy_decisions": [dict(d) for d in POLICY_DECISIONS],
        "separate_results": {k: v for k, v in separate.items() if v is not None},
        "notes": [NOT_AUTHORIZED, TARGET_LABEL],
    }
    manifest["manifest_sha256"] = canonical_digest(manifest)
    return manifest


# --- what cutover preflight (IR-742) reads ---------------------------------------------

GATES = tuple(GATE_SOURCES)
#: Keys outside the sealed manifest: the digest itself, and the commit ``write_run`` stamps on
#: the file it writes (provenance of the file, not part of what the digest covers).
UNSEALED = ("manifest_sha256", "commit")


def verify_manifest(manifest: Mapping) -> list[str]:
    """Why this manifest cannot be trusted as written; empty when it is internally sound.

    Sound is not ready: a blocked manifest is sound. The digest catches an edit; the
    consistency checks catch an edit that was resealed.
    """
    if not isinstance(manifest, Mapping):
        return ["the manifest is not a JSON object"]
    problems = []
    if manifest.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"unknown schema_version {manifest.get('schema_version')!r}; this "
                        f"reader understands {SCHEMA_VERSION!r}")
    body = {k: v for k, v in manifest.items() if k not in UNSEALED}
    if manifest.get("manifest_sha256") != canonical_digest(body):
        problems.append("the manifest digest (manifest_sha256) does not match the manifest: it "
                        "was edited after it was written")
    gates = manifest.get("gates")
    if not isinstance(gates, Mapping):
        return problems + ["the manifest has no gates object"]
    missing = [g for g in GATES if g not in gates]
    if missing:
        problems.append(f"gates missing from the manifest: {', '.join(missing)}")
    unmet = []
    for name in GATES:
        g = gates.get(name)
        if g is None:
            continue
        if not isinstance(g, Mapping):
            problems.append(f"gate {name} is not an object")
            continue
        if g.get("status") not in STATUSES:
            problems.append(f"gate {name} has unknown status {g.get('status')!r}")
        if g.get("status") != MET:
            unmet.append(name)
            continue
        if g.get("blocking"):
            problems.append(f"gate {name} is met but marked blocking")
        inputs = manifest.get("inputs") or {}
        named, foreign = set(), set()
        for e in g.get("evidence") or ():
            ref = inputs.get(e.get("name")) or {}
            if not (e.get("path") and e.get("sha256")):
                continue
            if (ref.get("path"), ref.get("sha256")) != (e.get("path"), e.get("sha256")):
                foreign.add(e.get("name"))
                problems.append(f"gate {name} cites {e.get('name')} evidence that the manifest's "
                                "inputs do not record")
                continue
            named.add(e.get("name"))
        lacking = [s for s in GATE_SOURCES.get(name, ()) if s not in named | foreign]
        if lacking:
            problems.append(f"gate {name} is met with no evidence reference for "
                            f"{', '.join(lacking)}")
    status = manifest.get("status")
    if status not in (READY, BLOCKED):
        problems.append(f"unknown status {status!r}")
    elif status == READY and unmet:
        problems.append(f"status is {READY} but gates are not met: {', '.join(unmet)}")
    elif status == BLOCKED and not unmet and not missing:
        problems.append(f"status is {BLOCKED} but every gate is met")
    if status == READY and not (manifest.get("live_collection") or {}).get("allowed"):
        problems.append(f"status is {READY} but live collection is not authorized")
    return problems


#: Reads one recorded input: its path in, (SHA-256 of the file, parsed JSON) out.
Reader = Callable[[str], tuple]


def build_arguments(loaded: Mapping[str, Any], build: Mapping) -> dict:
    """``build_readiness`` keywords from input files as loaded, keyed as ``inputs`` names them.

    The command builds through this and ``assert_ready`` rebuilds through it, so a manifest
    and its recomputation cannot read the same files differently.
    """
    baseline = None
    if loaded.get("baseline") is not None:
        baseline = {"report": loaded["baseline"], "arm": build.get("baseline_arm"),
                    "expected_sha256": build.get("baseline_sha256")}
    scenarios = loaded.get("scenarios")
    return {"report": loaded.get("report"), "candidate": build.get("candidate"),
            "baseline": baseline,
            "scenarios": scenario_rows(scenarios) if scenarios is not None else None,
            **{k: loaded.get(k) for k in ("workload", "profile", "measurements", "approvals",
                                          "capability", "model")}}


def rebuild_problems(manifest: Mapping, read: Reader) -> list[str]:
    """Rebuild the manifest from the files it names; it must come out byte-identical.

    This is what makes the verdict machine-checkable: a manifest edited and resealed, or one
    whose inputs were swapped or removed, does not rebuild to itself.
    """
    inputs = manifest.get("inputs") or {}
    build = manifest.get("build") or {}
    if "report" not in inputs or not build.get("candidate"):
        return ["the manifest records no report input or build arguments, so its verdict "
                "cannot be recomputed"]
    loaded, problems = {}, []
    for name, ref in inputs.items():
        try:
            digest, value = read(str(ref.get("path", "")))
        except (OSError, ValueError) as exc:
            problems.append(f"input {name} ({ref.get('path')}) cannot be read to recompute the "
                            f"verdict: {exc}")
            continue
        if digest != ref.get("sha256"):
            problems.append(f"input {name} ({ref.get('path')}) has changed since the manifest "
                            "was built")
        loaded[name] = value
    if problems:
        return problems
    try:
        again = build_readiness(**build_arguments(loaded, build), references=inputs)
    except (ReadinessRefused, AttributeError, KeyError, TypeError) as exc:
        return [f"the manifest cannot be rebuilt from its inputs: {exc}"]
    if again["manifest_sha256"] != manifest.get("manifest_sha256"):
        return ["the manifest's verdict does not follow from its inputs: rebuilding it from the "
                "files it names gives a different manifest"]
    return []


def assert_ready(manifest: Mapping, *, expect_commit: str, read: Reader) -> None:
    """Refuse unless the manifest is sound, rebuilds from its inputs, is ready and is for
    ``expect_commit``, a clean commit."""
    problems = verify_manifest(manifest)
    if manifest.get("status") != READY:
        blocked = [f"{n} [{g.get('status')}]" for n, g in (manifest.get("gates") or {}).items()
                   if isinstance(g, Mapping) and g.get("status") != MET]
        problems.append("readiness is blocked by gates: " + ", ".join(blocked or ["unknown"]))
    got = (manifest.get("candidate") or {}).get("git_commit")
    if expect_commit in NO_COMMIT or _dirty(expect_commit):
        problems.append(f"the expected commit {expect_commit!r} is not a clean commit")
    elif got != expect_commit:
        problems.append(f"the evidence is for commit {got!r}, not {expect_commit!r}")
    if not problems:
        problems = rebuild_problems(manifest, read)
    if problems:
        raise ReadinessRefused("; ".join(problems))
