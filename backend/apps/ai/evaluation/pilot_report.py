"""The evidence-decision pilot's report (IR-467, ADR-035 §10, §11).

**Two instruments, two sections, two sets of denominators.** `curated` comes
from `eval_evidence` result files and is the only source of accuracy.
`shadow` comes from IR-466's shadow rows on real traffic and carries no ground
truth, so nothing here computes an accuracy from it. The two are never added,
averaged or put in one table row.

Missing data is reported as missing: a field a run file does not record is
`"not recorded"`, never inferred, and an absent sample plan is `not_declared`.
No time of day enters the output, so the same inputs give the same bytes.

Pure: no database and no file I/O. The command hands it parsed JSON and plain
row dicts.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from typing import Any, Iterable, Mapping, Optional, Sequence

from apps.ai.evidence.model_decision import DECIDED_REASONS
from apps.ai.models.shadow import COMPLETED, FAILED, PENDING, RUNNING, SKIPPED

REPORT_VERSION = 1
NOT_RECORDED = "not recorded"

STAGE_EXPLORATORY = "exploratory"
STAGE_CONFIRMATORY = "confirmatory"
STAGES = (STAGE_EXPLORATORY, STAGE_CONFIRMATORY)

PLAN_NOT_DECLARED = "not_declared"
PLAN_INCOMPLETE = "incomplete"
PLAN_DECLARED = "declared"

#: What a stage's plan must state before its run. The confirmatory run's plan
#: and floor are predefined (IR-467), so a missing key is a missing plan.
REQUIRED_PLAN_KEYS = {
    STAGE_EXPLORATORY: ("declared_at", "purpose"),
    STAGE_CONFIRMATORY: (
        "declared_at",
        "sample_rate",
        "target_decisions",
        "coverage_floor",
        "min_examples_per_category",
    ),
}

#: Rows that never reached a decision and why. Anything else is `other`.
CAPACITY_OUTCOMES = ("shadow_budget_spent",)
BREAKER_OUTCOMES = ("answer_breaker_open", "answer_breaker_failures")

#: Tallies are counts with no row and no timestamp.
TALLY_NO_ROW = ("record_failed", "turn_deleted")
TALLY_EVENT = "enqueue_failed"

#: Tests that assert, rather than observe, the two safety properties.
SAFETY_TESTS = {
    "no reader-visible change": [
        "apps/ai/tests/test_evidence_shadow.py::test_shadow_changes_nothing_a_reader_receives",
        "apps/ai/tests/test_shadow_off_snapshot.py",
        "apps/ai/tests/test_evidence_shadow.py::test_a_failing_enqueue_never_reaches_the_reader",
    ],
    "no shadow-attributable degradation of the answer path": [
        "apps/ai/tests/test_evidence_shadow.py::test_the_reader_path_spends_against_no_bucket",
        "apps/ai/tests/test_evidence_shadow.py::test_shadow_is_skipped_when_the_answer_breaker_is_open",
        "apps/ai/tests/test_evidence_shadow.py::test_shadow_is_skipped_when_its_budget_is_spent",
    ],
}

CANNOT_MEASURE = (
    "Answer quality and claim support. The hypothetical direct answer is "
    "discarded in process by design, so neither is observable. They become "
    "measurable only through a separately approved capture, which is out of "
    "scope.",
    "Reader-visible end-to-end latency for a direct answer. Shadow always "
    "retrieves afterwards, so no request ever takes the shape a production "
    "direct answer would. The latencies below are the decision call's and the "
    "task's, not a reader's.",
    "Page precision. There is no instrument: labels match on record identity "
    "plus normalised quote containment, and the page is reported and never "
    "scored. ADR-028's central objection can be neither confirmed nor "
    "refuted today.",
)

ON_GATES = (
    "Routing thresholds met across repeated runs.",
    "An offline review of hypothetical direct answers passed.",
    "The landscape policy (ADR-035 §9) resolved with an accountable owner "
    "named by a person, never inferred.",
    "The reader-facing 'search the papers instead' override built.",
    "ADR-035 accepted (it is, as of 2026-10-06; that does not make the other "
    "four true).",
)


def percentile(values: Sequence[float], fraction: float) -> Optional[float]:
    """Nearest-rank, so a small sample reports a value it contains."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(math.ceil(fraction * len(ordered)), 1) - 1]


def _rate(numerator: int, denominator: int) -> Optional[float]:
    return round(numerator / denominator, 4) if denominator else None


def _latency(values: Sequence[float]) -> dict[str, Any]:
    return {
        "n": len(values),
        "mean": round(sum(values) / len(values)) if values else None,
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "max": max(values) if values else None,
    }


# -- curated ---------------------------------------------------------------


class ReportInputError(ValueError):
    """An input that cannot be read as what it claims to be."""


def check_curated_file(data: Mapping[str, Any], source: str) -> None:
    if not isinstance(data, Mapping) or data.get("instrument") != "curated":
        raise ReportInputError(
            f"{source} is not an eval_evidence result file (instrument != 'curated')"
        )
    for key in ("detector", "provenance", "question_set", "coverage"):
        if key not in data:
            raise ReportInputError(f"{source} has no '{key}' section")


def _lane(lane: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "judged": lane["judged"],
        "correct": lane["correct"],
        "over_fires": len(lane["over_fires"]),
        "misses": len(lane["misses"]),
        "undetermined": len(lane.get("undetermined", [])),
        "over_fire_ids": list(lane["over_fires"]),
        "miss_ids": list(lane["misses"]),
        "per_rule": [
            {
                "code": rule["code"],
                "fired": rule["fired"],
                "over_fires": len(rule["over_fires"]),
                "over_fire_ids": list(rule["over_fires"]),
                "silent_on_required": len(rule["silent_on_required"]),
            }
            for rule in lane["rules"]
        ],
    }


def _category(category: Mapping[str, Any]) -> dict[str, Any]:
    inconclusive = category["judged"] < category["min_examples"]
    return {
        "kind": category["kind"],
        "judged": category["judged"],
        "correct": category["correct"],
        "min_examples": category["min_examples"],
        "status": "inconclusive" if inconclusive else "conclusive",
        # A figure from too few examples is withheld, not reported low.
        "accuracy": (
            None
            if inconclusive
            else _rate(category["correct"], category["judged"])
        ),
    }


def _model(model: Optional[Mapping[str, Any]]) -> Optional[dict[str, Any]]:
    if not model:
        return None
    questions = model["questions"]
    return {
        "models": list(model.get("models", [])),
        "questions": questions,
        "fallbacks": model["fallbacks"],
        "failure_rate": _rate(model["fallbacks"], questions),
        "model_alone": _route_tally(model["model_alone"]),
        "model_alone_decided_only": model["model_alone_decided_only"],
        "union": _route_tally(model["union"]),
        "detector_model_agreement": model["agreement_with_detector"],
        "reasons": {k: v for k, v in model["reasons"].items() if v},
        "anomalies": model.get("anomalies", {}),
        "decision_latency_ms": model["latency_ms"],
        "tokens": model["tokens"],
    }


def _route_tally(tally: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "judged": tally["judged"],
        "correct": tally["correct"],
        "accuracy": tally["accuracy"],
        "over_searches": len(tally["over_searches"]),
        "missed_searches": len(tally["missed_searches"]),
        "missed_search_ids": list(tally["missed_searches"]),
    }


def summarize_curated_run(data: Mapping[str, Any], source: str) -> dict[str, Any]:
    """One result file, reduced to the figures the report states."""
    check_curated_file(data, source)
    provenance = data["provenance"]
    detector = data["detector"]
    categories = [_category(c) for c in detector["categories"]]
    lanes = {lane["lane"]: _lane(lane) for lane in detector["lanes"]}
    model = _model(data.get("model"))
    return {
        "source": source,
        "provenance": {
            "git_commit": provenance.get("git_commit", NOT_RECORDED),
            "question_set": data["question_set"].get("name", NOT_RECORDED),
            "question_set_sha256": provenance.get("question_set_sha256", NOT_RECORDED),
            "rule_set_digest": data.get("rule_set_digest", NOT_RECORDED),
            "AI_EVIDENCE_DECISION": provenance.get("AI_EVIDENCE_DECISION", NOT_RECORDED),
            "model_decision_run": bool(provenance.get("model_decision")),
            "models": model["models"] if model else [],
            "prompt_digest": provenance.get("prompt_digest", NOT_RECORDED),
            "generation": provenance.get("generation", NOT_RECORDED),
            "scoring": data.get("scoring", NOT_RECORDED),
            # Detector-only: no retrieval runs, so there is no configuration.
            "retrieval_configuration": "not applicable (no retrieval runs)",
        },
        "coverage": data["coverage"],
        "lanes": lanes,
        "categories": categories,
        "inconclusive_categories": [
            c["kind"] for c in categories if c["status"] == "inconclusive"
        ],
        "conclusive_categories": sum(
            1 for c in categories if c["status"] == "conclusive"
        ),
        "institutional": detector.get("institutional"),
        "model": model,
    }


def summarize_curated(runs: Sequence[tuple[str, Mapping[str, Any]]]) -> dict[str, Any]:
    """Every run on its own. Runs are listed, never pooled: the `on` gate asks
    for repeated runs, and pooling would hide the variance it is asking about."""
    summaries = [summarize_curated_run(data, source) for source, data in runs]
    model_runs = [s for s in summaries if s["model"]]
    by_set = Counter(s["provenance"]["question_set_sha256"] for s in model_runs)
    return {
        "instrument": "curated",
        "has_ground_truth": True,
        "denominators": (
            "Each lane's denominator is the annotated questions carrying that "
            "lane's text (the Resolved lane only those with a Resolved "
            "question). Each category's is its own annotated questions. The "
            "model section's is every annotated question put to the model."
        ),
        "runs": summaries,
        "model_runs": len(model_runs),
        "max_model_runs_on_one_question_set": max(by_set.values(), default=0),
    }


# -- shadow ----------------------------------------------------------------


def summarize_shadow(
    rows: Iterable[Mapping[str, Any]],
    tallies: Optional[Mapping[str, int]] = None,
) -> dict[str, Any]:
    """Operational figures from shadow rows. Accuracy is not computed.

    `tallies` is the unwindowed `ShadowEvidenceTally`, or ``None`` when the
    caller windowed the rows and so cannot attribute the tallies to them.

    Eligible = rows + tallied sampled questions that never got a row
    (`record_failed`, `turn_deleted`). `enqueue_failed` is an event on a row
    that already exists as pending, so it is shown and not added.

    Missing = eligible - completed, broken out; `reclaimed`, `fenced` and
    `mismatched` are overlays on rows and are not subtracted.
    """
    rows = list(rows)
    status = Counter(row["status"] for row in rows)
    completed = [row for row in rows if row["status"] == COMPLETED]
    skipped = [row for row in rows if row["status"] == SKIPPED]
    failed = [row for row in rows if row["status"] == FAILED]
    unfinished = [row for row in rows if row["status"] in (PENDING, RUNNING)]

    tally_known = tallies is not None
    no_row = {code: (tallies or {}).get(code, 0) for code in TALLY_NO_ROW}
    eligible = len(rows) + sum(no_row.values())

    skip_outcomes = Counter(row["outcome"] or "unspecified" for row in skipped)
    fail_outcomes = Counter(row["outcome"] or "unspecified" for row in failed)
    capacity = sum(skip_outcomes[o] for o in CAPACITY_OUTCOMES)
    breaker = sum(skip_outcomes[o] for o in BREAKER_OUTCOMES)

    decided = [
        row
        for row in completed
        if (row.get("decision") or {}).get("reason") in DECIDED_REASONS
    ]
    fell_back = [
        row
        for row in completed
        if row.get("decision") and row["decision"].get("reason") not in DECIDED_REASONS
    ]
    provider_reasons = Counter(row["decision"]["reason"] for row in fell_back)

    parity = Counter(
        "matched" if row["parity_matched"] else "mismatched"
        for row in completed
        if row.get("parity_matched") is not None
    )
    decision_ms = [
        row["decision"]["latency_ms"]
        for row in completed
        if row.get("decision") and row["decision"].get("latency_ms") is not None
    ]
    task_ms = [
        (row["finished_at"] - row["created_at"]).total_seconds() * 1000
        for row in completed
        if row.get("finished_at") and row.get("created_at")
    ]
    in_tokens = [
        row["decision"]["input_tokens"]
        for row in completed
        if row.get("decision") and row["decision"].get("input_tokens") is not None
    ]
    out_tokens = [
        row["decision"]["output_tokens"]
        for row in completed
        if row.get("decision") and row["decision"].get("output_tokens") is not None
    ]

    # Descriptive only: two machine verdicts side by side, neither a label.
    cells = Counter()
    for row in decided:
        detector = bool((row.get("detector") or {}).get("evidence_required", True))
        model = row["decision"]["route"] == "evidence"
        cells[(detector, model)] += 1

    by_day = Counter(row["created_at"].date().isoformat() for row in rows)
    reasons = Counter(
        code for row in rows for code in (row.get("detector") or {}).get("codes", [])
    )
    manifests = Counter(
        json.dumps(
            {
                "rule_set_digest": (row.get("manifest") or {}).get("rule_set_digest", NOT_RECORDED),
                "prompt_digest": (row.get("manifest") or {}).get("prompt_digest", NOT_RECORDED),
                "model": ((row.get("manifest") or {}).get("generation") or {}).get(
                    "model", NOT_RECORDED
                ),
            },
            sort_keys=True,
        )
        for row in rows
    )

    return {
        "instrument": "shadow",
        "available": True,
        "has_ground_truth": False,
        "accuracy": (
            "not computed: real traffic carries no labels (ADR-035 §10). Any "
            "accuracy figure drawn from this section is a category error."
        ),
        "denominators": (
            "Coverage is over eligible questions. Latency is over completed "
            "rows that recorded it. Parity is over completed rows. "
            "Detector/model cells are over rows where the model ruled."
        ),
        "eligible": eligible,
        "tallies_attributed": tally_known,
        "coverage": {
            "completed_rows": len(completed),
            "missing": eligible - len(completed),
            "missing_breakdown": {
                "skipped": len(skipped),
                "failed": len(failed),
                "unfinished": len(unfinished),
                "no_row_record_failed": no_row["record_failed"],
                "no_row_turn_deleted": no_row["turn_deleted"],
            },
            "reclaimed_rows": sum(1 for row in rows if row["reclaims"]),
            "reclaims": sum(row["reclaims"] for row in rows),
            "fenced_out_completions": sum(row["fenced_out_completions"] for row in rows),
            "mismatched": parity["mismatched"],
            "parity_checked": sum(parity.values()),
            "enqueue_failed_events": (tallies or {}).get(TALLY_EVENT, 0),
        },
        "status": dict(sorted(status.items())),
        "skips": {
            "by_outcome": dict(sorted(skip_outcomes.items())),
            "breaker": breaker,
            "capacity": capacity,
        },
        "failures": {
            "rows_failed": dict(sorted(fail_outcomes.items())),
            "model_fell_back_to_evidence": len(fell_back),
            "by_reason": dict(sorted(provider_reasons.items())),
        },
        "latency_ms": {
            "decision_call": _latency(decision_ms),
            "task_created_to_finished": _latency(task_ms),
        },
        "tokens": {
            "rows_reporting_input": len(in_tokens),
            "input_total": sum(in_tokens),
            "rows_reporting_output": len(out_tokens),
            "output_total": sum(out_tokens),
        },
        "detector_model_cells": {
            "n": len(decided),
            "both_evidence": cells[(True, True)],
            "both_direct": cells[(False, False)],
            "detector_only_evidence": cells[(True, False)],
            "model_only_evidence": cells[(False, True)],
        },
        "volume_by_day": dict(sorted(by_day.items())),
        "detector_codes_fired": dict(sorted(reasons.items())),
        "configurations": [
            {**json.loads(key), "rows": n} for key, n in sorted(manifests.items())
        ],
        "single_configuration": len(manifests) <= 1,
    }


def unavailable_shadow(reason: str) -> dict[str, Any]:
    """The shadow section when the rows could not be read. Distinct from an
    empty one: zero rows is a finding, an unreachable database is not."""
    return {
        "instrument": "shadow",
        "available": False,
        "has_ground_truth": False,
        "reason": reason,
        "eligible": None,
    }


# -- the plan --------------------------------------------------------------


def assess_plan(plan: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    """Each stage `not_declared`, `incomplete` (naming what is missing) or
    `declared`. Nothing is defaulted: a number the person did not write is not
    in the plan."""
    stages: dict[str, Any] = {}
    for stage in STAGES:
        declared = ((plan or {}).get("stages") or {}).get(stage)
        if not declared:
            stages[stage] = {"status": PLAN_NOT_DECLARED}
            continue
        missing = [k for k in REQUIRED_PLAN_KEYS[stage] if declared.get(k) in (None, "")]
        stages[stage] = {
            "status": PLAN_INCOMPLETE if missing else PLAN_DECLARED,
            "missing": missing,
            "plan": dict(declared),
        }
    return stages


def assess_confirmatory(
    plan_stage: Mapping[str, Any], shadow: Mapping[str, Any], excluded_early: int
) -> dict[str, Any]:
    """The confirmatory plan's targets against what the window produced."""
    plan = plan_stage.get("plan") or {}
    floor = plan.get("coverage_floor")
    target = plan.get("target_decisions")
    if not shadow.get("available"):
        return {"floor": "not assessable", "target": "not assessable"}
    eligible = shadow["eligible"]
    completed = shadow["coverage"]["completed_rows"]
    return {
        "rows_before_declaration_excluded": excluded_early,
        "coverage_floor": floor,
        "completed_over_eligible": _rate(completed, eligible),
        "floor": (
            "not assessable"
            if floor is None or not eligible
            else ("met" if completed / eligible >= floor else "not met")
        ),
        "target_decisions": target,
        "target": (
            "not assessable"
            if target is None
            else ("met" if completed >= target else "not met")
        ),
    }


# -- the report ------------------------------------------------------------


def recommend(report: Mapping[str, Any]) -> list[str]:
    """A recommendation computed from what is present, so an absent
    measurement cannot read as a good one. It never authorizes `on`."""
    lines: list[str] = []
    curated, shadow = report["curated"], report["shadow"]
    plan = report["sample_plan"]

    if not curated["runs"]:
        lines.append("No curated result file was supplied: there is no accuracy to report.")
    elif not curated["model_runs"]:
        lines.append(
            "No curated run included the model (--model-decision), so the "
            "model's route accuracy and detector/model agreement are unmeasured."
        )
    elif curated["max_model_runs_on_one_question_set"] < 2:
        lines.append(
            "One model run per question set. Decisions flip between runs "
            "(ADR-035 §Context), so one run is not a measurement; the gate "
            "asks for repeated runs."
        )
    rules = {json.dumps(r["provenance"]["scoring"], sort_keys=True) for r in curated["runs"]}
    if len(rules) > 1:
        lines.append(
            "Curated runs were scored under different rules (a file without a "
            "`scoring` record predates the rule that a vague question may be "
            "searched without penalty), so their over-fire and over-search "
            "counts are not comparable: "
            + "; ".join(
                f"{r['source']}: {json.dumps(r['provenance']['scoring'], sort_keys=True)}"
                for r in curated["runs"]
            )
        )
    inconclusive = {
        c for run in curated["runs"] for c in run["inconclusive_categories"]
    }
    if inconclusive:
        lines.append(
            f"{len(inconclusive)} categor{'y is' if len(inconclusive) == 1 else 'ies are'} "
            "inconclusive: label more questions before any per-category claim."
        )
    for run in curated["runs"]:
        union = (run["model"] or {}).get("union")
        if union and union["missed_searches"]:
            lines.append(
                f"{run['source']}: the union missed {union['missed_searches']} "
                f"question(s) needing the corpus ({', '.join(union['missed_search_ids'])}). "
                "That is the expensive direction (ADR-035 §3)."
            )

    if not shadow["available"]:
        lines.append(
            f"The shadow rows could not be read ({shadow['reason']}): the "
            "operational side is unmeasured, which is not the same as zero traffic."
        )
    elif not shadow["eligible"]:
        lines.append(
            "No shadow rows: the operational side of the pilot has not run on "
            "any traffic, so coverage, latency and contention are unmeasured. "
            "ADR-035 §11 keeps shadow off real reader questions until the "
            "vendor-retention check is recorded."
        )
    elif not shadow["single_configuration"]:
        lines.append(
            "Shadow rows span more than one rule-set, prompt or model "
            "configuration; do not read them as one population."
        )
    if shadow["available"] and shadow["eligible"] and shadow["coverage"]["mismatched"]:
        lines.append(
            f"{shadow['coverage']['mismatched']} completed row(s) differed from "
            "their request's manifest (parity mismatch); read the figures with that."
        )

    for stage in STAGES:
        if plan["stages"][stage]["status"] != PLAN_DECLARED:
            lines.append(
                f"The {stage} sample plan is {plan['stages'][stage]['status'].replace('_', ' ')}"
                + (
                    f" (missing: {', '.join(plan['stages'][stage]['missing'])})"
                    if plan["stages"][stage].get("missing")
                    else ""
                )
                + "."
            )

    lines.append(
        "Recommendation: do not move toward production `on` on this evidence. "
        "The pilot is evidence for that decision, not authorization to make "
        "it, and none of the other gates below is satisfied by it."
        if lines
        else "Recommendation: the measurements above are complete for the "
        "declared plan; they inform the `on` decision and do not make it."
    )
    return lines


def build_report(
    *,
    curated_runs: Sequence[tuple[str, Mapping[str, Any]]],
    shadow_rows: Optional[Iterable[Mapping[str, Any]]],
    shadow_tallies: Optional[Mapping[str, int]],
    plan: Optional[Mapping[str, Any]],
    stage: str,
    window: Mapping[str, Any],
    excluded_early: int = 0,
    shadow_unavailable: Optional[str] = None,
) -> dict[str, Any]:
    if stage not in STAGES:
        raise ReportInputError(f"stage must be one of {STAGES}, not {stage!r}")
    plan_stages = assess_plan(plan)
    shadow = (
        unavailable_shadow(shadow_unavailable)
        if shadow_unavailable
        else summarize_shadow(shadow_rows or (), shadow_tallies)
    )
    sample_plan = {
        "stages": plan_stages,
        "stage_reported": stage,
        "window": dict(window),
        "confirmatory_assessment": (
            assess_confirmatory(plan_stages[STAGE_CONFIRMATORY], shadow, excluded_early)
            if stage == STAGE_CONFIRMATORY
            and plan_stages[STAGE_CONFIRMATORY]["status"] == PLAN_DECLARED
            else None
        ),
        "note": (
            "The figure of 200 decisions that circulated during design is an "
            "exploratory planning estimate with no demonstrated statistical "
            "basis. It certifies nothing and is not used here."
        ),
    }
    report: dict[str, Any] = {
        "report": "evidence-decision-pilot",
        "version": REPORT_VERSION,
        "ticket": "IR-467",
        "curated": summarize_curated(curated_runs),
        "shadow": shadow,
        "sample_plan": sample_plan,
        "cannot_measure": list(CANNOT_MEASURE),
        "safety_properties_asserted_by_test": SAFETY_TESTS,
        "on_gates": list(ON_GATES),
    }
    report["recommendation"] = recommend(report)
    return report


def to_json(report: Mapping[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


# -- markdown --------------------------------------------------------------


def _fmt(value: Any) -> str:
    return "n/a" if value is None else str(value)


def render_markdown(report: Mapping[str, Any]) -> str:
    out: list[str] = [
        "# Evidence-decision pilot report (IR-467)",
        "",
        "Two instruments, reported separately and never blended (ADR-035 §10). "
        "The pilot is complete when it has produced a trustworthy measurement, "
        "whatever that measurement says.",
        "",
        "## 1. Curated evaluation (has ground truth)",
        "",
        report["curated"]["denominators"],
        "",
    ]
    curated = report["curated"]
    if not curated["runs"]:
        out += ["**No curated result file supplied.**", ""]
    for run in curated["runs"]:
        prov = run["provenance"]
        out += [
            f"### Run `{run['source']}`",
            "",
            f"- commit `{prov['git_commit']}`; question set `{prov['question_set']}` "
            f"(sha256 `{prov['question_set_sha256']}`)",
            f"- rule-set digest `{prov['rule_set_digest']}`; "
            f"`AI_EVIDENCE_DECISION={prov['AI_EVIDENCE_DECISION']}`",
            f"- model run: {prov['model_decision_run']}"
            + (f"; model(s) {', '.join(prov['models'])}" if prov["models"] else ""),
            f"- prompt digest: {prov['prompt_digest']}; generation: {prov['generation']}",
            f"- scoring: {prov['scoring']}",
            f"- retrieval configuration: {prov['retrieval_configuration']}",
            f"- coverage: {run['coverage']['annotated']} of "
            f"{run['coverage']['questions_in_set']} questions annotated, "
            f"{run['coverage']['with_resolved_question']} with a Resolved form",
            "",
            "Detector, per lane (own denominators):",
            "",
            "| lane | judged | correct | over-fires | misses |",
            "|---|---|---|---|---|",
        ]
        for name, lane in run["lanes"].items():
            out.append(
                f"| {name} | {lane['judged']} | {lane['correct']} | "
                f"{lane['over_fires']} | {lane['misses']} |"
            )
        out += ["", "Per rule, raw and Resolved lanes separately (silent-on-required is not a detector miss):", ""]
        out += [
            "| lane | rule | fired | over-fires | silent on required |",
            "|---|---|---|---|---|",
        ]
        for name in ("raw", "resolved"):
            lane = run["lanes"].get(name)
            if not lane:
                continue
            for rule in lane["per_rule"]:
                out.append(
                    f"| {name} | {rule['code']} | {rule['fired']} | "
                    f"{rule['over_fires']} | {rule['silent_on_required']} |"
                )
        out += [
            "",
            "Categories (combined lane; fewer examples than the minimum is "
            "inconclusive and its accuracy is withheld):",
            "",
            "| category | judged | correct | status | accuracy |",
            "|---|---|---|---|---|",
        ]
        for c in run["categories"]:
            out.append(
                f"| {c['kind']} | {c['judged']} | {c['correct']} | "
                f"{c['status'].upper()} (min {c['min_examples']}) | {_fmt(c['accuracy'])} |"
            )
        out.append("")
        inst = run["institutional"]
        if inst:
            out.append(
                f"Institutional questions: {inst['judged']} judged, "
                f"{len(inst['incorrect'])} incorrect."
            )
            out.append("")
        model = run["model"]
        if not model:
            out += ["Model decision: **not run** in this file.", ""]
        else:
            out += [
                f"Model decision ({', '.join(model['models']) or NOT_RECORDED}): "
                f"{model['questions']} calls, {model['fallbacks']} fell back to "
                f"evidence (failure rate {_fmt(model['failure_rate'])}).",
                "",
                "| view | judged | correct | over-searches | missed searches |",
                "|---|---|---|---|---|",
                f"| model alone | {model['model_alone']['judged']} | "
                f"{model['model_alone']['correct']} | {model['model_alone']['over_searches']} | "
                f"{model['model_alone']['missed_searches']} |",
                f"| union (detector OR model) | {model['union']['judged']} | "
                f"{model['union']['correct']} | {model['union']['over_searches']} | "
                f"{model['union']['missed_searches']} |",
                "",
                f"Model alone over calls where it ruled: "
                f"{model['model_alone_decided_only']['correct']}/"
                f"{model['model_alone_decided_only']['judged']}.",
                f"Detector/model agreement: {model['detector_model_agreement']}.",
                f"Reason codes: {model['reasons']}. Decision latency: {model['decision_latency_ms']}.",
                "",
            ]
    if curated["runs"]:
        out += [
            f"Model runs: {curated['model_runs']}; most on one question set: "
            f"{curated['max_model_runs_on_one_question_set']}. Runs are listed "
            "separately and never pooled.",
            "",
        ]

    shadow = report["shadow"]
    cov = shadow.get("coverage")
    out += [
        "## 2. Real-traffic shadow operations (NO ground truth)",
        "",
        "**Real traffic carries no labels: no accuracy is computed from this "
        "section, and any accuracy figure drawn from it is a category error "
        "(ADR-035 §10).**",
        "",
        shadow.get("denominators", ""),
        "",
    ]
    if not shadow["available"]:
        out += [
            f"**Shadow rows unavailable: {shadow['reason']}.** Nothing is "
            "reported, and this is not a finding of zero traffic.",
            "",
        ]
    elif not shadow["eligible"]:
        out += ["**No shadow rows in the reported window.**", ""]
    else:
        miss = cov["missing_breakdown"]
        out += [
            "| measure | count |",
            "|---|---|",
            f"| eligible | {shadow['eligible']} |",
            f"| completed | {cov['completed_rows']} |",
            f"| missing (total) | {cov['missing']} |",
            f"| - skipped | {miss['skipped']} |",
            f"| - failed | {miss['failed']} |",
            f"| - unfinished (pending/running) | {miss['unfinished']} |",
            f"| - no row: record failed | {miss['no_row_record_failed']} |",
            f"| - no row: turn deleted | {miss['no_row_turn_deleted']} |",
            f"| reclaimed rows (overlay) | {cov['reclaimed_rows']} ({cov['reclaims']} reclaims) |",
            f"| fenced-out completions (overlay) | {cov['fenced_out_completions']} |",
            f"| mismatched (of {cov['parity_checked']} parity-checked) | {cov['mismatched']} |",
            f"| enqueue failed (event on a pending row) | {cov['enqueue_failed_events']} |",
            "",
        ]
        if not shadow["tallies_attributed"]:
            out += [
                "Tallies carry no timestamp and could not be attributed to this "
                "window, so no-row counts are 0 here by omission, not by measurement.",
                "",
            ]
        out += [
            f"Skips by outcome: {shadow['skips']['by_outcome']} "
            f"(breaker {shadow['skips']['breaker']}, capacity {shadow['skips']['capacity']}).",
            f"Failed rows: {shadow['failures']['rows_failed']}; model fell back "
            f"to evidence on {shadow['failures']['model_fell_back_to_evidence']} "
            f"completed row(s): {shadow['failures']['by_reason']}.",
            f"Decision-call latency (ms): {shadow['latency_ms']['decision_call']}.",
            f"Task latency created-to-finished (ms, includes queue wait): "
            f"{shadow['latency_ms']['task_created_to_finished']}.",
            f"Tokens: {shadow['tokens']}.",
            f"Detector vs model, where the model ruled (descriptive, neither is a label): "
            f"{shadow['detector_model_cells']}.",
            f"Volume by day: {shadow['volume_by_day']}.",
            f"Detector reason codes fired: {shadow['detector_codes_fired']}.",
            f"Configurations: {shadow['configurations']}"
            + ("" if shadow["single_configuration"] else " (MORE THAN ONE)")
            + ".",
            "",
        ]

    plan = report["sample_plan"]
    out += ["## 3. Sample plan", ""]
    for stage in STAGES:
        entry = plan["stages"][stage]
        line = f"- **{stage}**: {entry['status'].replace('_', ' ')}"
        if entry.get("missing"):
            line += f" (missing {', '.join(entry['missing'])})"
        if entry.get("plan"):
            line += f"; plan {json.dumps(entry['plan'], sort_keys=True)}"
        out.append(line)
    out += [f"- reported stage: {plan['stage_reported']}; window {plan['window']}"]
    if plan["confirmatory_assessment"]:
        out.append(f"- confirmatory assessment: {plan['confirmatory_assessment']}")
    out += [f"- {plan['note']}", ""]

    out += ["## 4. What this report cannot measure", ""]
    out += [f"- {item}" for item in report["cannot_measure"]]
    out += ["", "## 5. Safety properties asserted by test, not observed", ""]
    for prop, tests in report["safety_properties_asserted_by_test"].items():
        out.append(f"- {prop}: " + "; ".join(f"`{t}`" for t in tests))
    out += ["", "## 6. Recommendation", ""]
    out += [f"- {line}" for line in report["recommendation"]]
    out += [
        "",
        "Production `on` requires all of the following. The pilot informs "
        "them and satisfies none of them:",
        "",
    ]
    out += [f"{i}. {gate}" for i, gate in enumerate(report["on_gates"], 1)]
    out.append("")
    return "\n".join(out)
