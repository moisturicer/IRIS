"""The pilot report keeps its two instruments apart (IR-467, ADR-035 §10).

Pure tests first: metric definitions, separate denominators, missing data and
byte-for-byte reproducibility need no database. The command's own tests are
`db_required` and skip cleanly with no Postgres reachable.
"""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.ai.evaluation import load_question_set
from apps.ai.evaluation.evidence import run_curated
from apps.ai.evaluation.pilot_report import (
    NOT_RECORDED,
    SAFETY_TESTS,
    ReportInputError,
    assess_confirmatory,
    assess_plan,
    build_report,
    render_markdown,
    summarize_curated_run,
    summarize_shadow,
    to_json,
)
from apps.ai.evidence import active_rule_set
from apps.ai.evidence.detector import EvidenceDetector
from apps.ai.evidence.model_decision import ModelEvidenceDecision
from apps.ai.management.commands.report_evidence_pilot import ROW_FIELDS
from apps.ai.providers.fakes import ScriptedToolCallingLLM

T0 = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)

QUOTE = "the document stopped moving and nobody noticed that it had"


def _question(qid, text, needs, kind, **extra):
    return {
        "id": qid,
        "question": text,
        "kind": kind,
        "evidence_required": "corpus" if needs else "none",
        "expected_outcome": "answer",
        "expected": [{"record": "A", "quote": QUOTE}] if needs else [],
        **extra,
    }


def _route(request):
    if "paper" in request.user:
        return ScriptedToolCallingLLM.calling()
    return ScriptedToolCallingLLM.answering("hypothetical")


@pytest.fixture
def curated_file(tmp_path):
    """A real `eval_evidence` result dict, produced by the real code."""
    path = tmp_path / "q.json"
    path.write_text(
        json.dumps(
            {
                "name": "t",
                "tier": "proxy",
                "questions": [
                    _question("q1", "what did the paper find?", True, "mechanism"),
                    _question("q2", "what is a median?", False, "general"),
                    _question("q3", "which paper is that?", True, "mechanism",
                              resolved_question="which paper is that paper?"),
                ],
            }
        ),
        encoding="utf-8",
    )
    with override_settings(AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",)):
        decider = ModelEvidenceDecision(ScriptedToolCallingLLM(_route))
        report = run_curated(
            EvidenceDetector(active_rule_set()),
            load_question_set(str(path)),
            min_examples=2,
            decider=decider,
            provenance={"git_commit": "abc", "question_set_sha256": "s", "model_decision": True},
        )
    return json.loads(json.dumps(report.as_dict()))


def _row(status="completed", **over):
    row = {
        "status": status,
        "outcome": "",
        "created_at": T0,
        "finished_at": T0 + timedelta(seconds=2),
        "reclaims": 0,
        "fenced_out_completions": 0,
        "parity_matched": True,
        "decision": {
            "route": "evidence",
            "reason": "search_requested",
            "latency_ms": 500,
            "input_tokens": 100,
            "output_tokens": 10,
        },
        "detector": {"evidence_required": True, "codes": ["document_reference"]},
        "manifest": {"rule_set_digest": "r", "prompt_digest": "p", "generation": {"model": "m"}},
    }
    if status != "completed":
        row.update(decision=None, parity_matched=None, finished_at=None)
    row.update(over)
    return row


def _build(curated=(), rows=(), tallies=None, plan=None, stage="exploratory", **kw):
    return build_report(
        curated_runs=curated,
        shadow_rows=rows,
        shadow_tallies=tallies,
        plan=plan,
        stage=stage,
        window={"since": None, "until": None},
        **kw,
    )


# -- metric definitions ----------------------------------------------------


def test_coverage_is_broken_out_and_never_a_single_percentage():
    rows = [
        _row(),
        _row(),
        _row("skipped", outcome="answer_breaker_open"),
        _row("skipped", outcome="shadow_budget_spent"),
        _row("failed", outcome="retries_exhausted"),
        _row("pending"),
        _row("running"),
    ]
    shadow = summarize_shadow(rows, {"record_failed": 2, "turn_deleted": 1})
    cov = shadow["coverage"]

    assert shadow["eligible"] == 10
    assert cov["completed_rows"] == 2
    assert cov["missing"] == 8
    assert cov["missing_breakdown"] == {
        "skipped": 2,
        "failed": 1,
        "unfinished": 2,
        "no_row_record_failed": 2,
        "no_row_turn_deleted": 1,
    }
    assert sum(cov["missing_breakdown"].values()) == cov["missing"]
    assert shadow["skips"]["breaker"] == 1
    assert shadow["skips"]["capacity"] == 1
    assert "coverage_rate" not in cov and "coverage_percent" not in cov


def test_reclaimed_fenced_and_mismatched_are_overlays_not_subtractions():
    rows = [
        _row(reclaims=1, fenced_out_completions=1),
        _row(parity_matched=False),
        _row(),
    ]
    shadow = summarize_shadow(rows, {"enqueue_failed": 4})
    cov = shadow["coverage"]

    assert cov["reclaimed_rows"] == 1 and cov["reclaims"] == 1
    assert cov["fenced_out_completions"] == 1
    assert cov["mismatched"] == 1 and cov["parity_checked"] == 3
    assert cov["missing"] == 0
    # An event on a row that already exists as pending; adding it would double count.
    assert cov["enqueue_failed_events"] == 4
    assert shadow["eligible"] == 3


def test_latency_and_tokens_use_only_the_rows_that_recorded_them():
    rows = [
        _row(),
        _row(decision={"route": "evidence", "reason": "search_requested", "latency_ms": 1500,
                       "input_tokens": None, "output_tokens": None}),
        _row("skipped", outcome="answer_breaker_open"),
    ]
    shadow = summarize_shadow(rows, {})

    assert shadow["latency_ms"]["decision_call"]["n"] == 2
    assert shadow["latency_ms"]["decision_call"]["p95"] == 1500
    assert shadow["latency_ms"]["task_created_to_finished"]["n"] == 2
    assert shadow["tokens"] == {
        "rows_reporting_input": 1,
        "input_total": 100,
        "rows_reporting_output": 1,
        "output_total": 10,
    }


def test_provider_failures_are_the_models_fallbacks_and_the_failed_rows():
    rows = [
        _row(decision={"route": "evidence", "reason": "rate_limited", "latency_ms": 9}),
        _row(decision={"route": "evidence", "reason": "timeout", "latency_ms": 9}),
        _row("failed", outcome="retries_exhausted"),
    ]
    failures = summarize_shadow(rows, {})["failures"]

    assert failures["model_fell_back_to_evidence"] == 2
    assert failures["by_reason"] == {"rate_limited": 1, "timeout": 1}
    assert failures["rows_failed"] == {"retries_exhausted": 1}


def test_a_fallback_is_not_counted_as_the_model_ruling():
    rows = [
        _row(decision={"route": "evidence", "reason": "timeout", "latency_ms": 9}),
        _row(decision={"route": "direct", "reason": "answered_directly", "latency_ms": 9},
             detector={"evidence_required": False, "codes": []}),
    ]
    cells = summarize_shadow(rows, {})["detector_model_cells"]

    assert cells["n"] == 1 and cells["both_direct"] == 1


# -- separate denominators and no accuracy from shadow ---------------------


def test_the_shadow_section_computes_no_accuracy_and_says_why():
    shadow = summarize_shadow([_row()], {})

    assert shadow["has_ground_truth"] is False
    assert isinstance(shadow["accuracy"], str) and "category error" in shadow["accuracy"]
    flat = json.dumps({k: v for k, v in shadow.items() if k != "accuracy"})
    assert "accuracy" not in flat and "precision" not in flat and "recall" not in flat


def test_curated_lanes_keep_their_own_denominators(curated_file):
    run = summarize_curated_run(curated_file, "f.json")

    assert run["lanes"]["raw"]["judged"] == 3
    assert run["lanes"]["resolved"]["judged"] == 1
    assert run["lanes"]["combined"]["judged"] == 3
    assert {r["code"] for r in run["lanes"]["resolved"]["per_rule"]} == {
        r["code"] for r in run["lanes"]["raw"]["per_rule"]
    }


def test_curated_and_shadow_are_separate_top_level_sections(curated_file):
    report = _build([("f.json", curated_file)], [_row()], {})

    assert report["curated"]["has_ground_truth"] is True
    assert report["shadow"]["has_ground_truth"] is False
    assert set(report["curated"]).isdisjoint({"coverage", "eligible"})
    text = render_markdown(report)
    assert text.index("## 1. Curated") < text.index("## 2. Real-traffic") < text.index("## 3.")
    assert "no accuracy is computed from this section" in text


def test_the_model_section_reports_failure_rate_and_union(curated_file):
    model = summarize_curated_run(curated_file, "f.json")["model"]

    assert model["questions"] == 3
    assert model["failure_rate"] == 0.0
    assert model["union"]["judged"] == 3
    assert model["detector_model_agreement"]["agreement"] is not None


def test_under_represented_categories_are_inconclusive_with_the_figure_withheld(curated_file):
    for category in curated_file["detector"]["categories"]:
        category["min_examples"] = 5
    run = summarize_curated_run(curated_file, "f.json")

    mech = next(c for c in run["categories"] if c["kind"] == "mechanism")
    assert mech["status"] == "inconclusive" and mech["accuracy"] is None
    assert "mechanism" in run["inconclusive_categories"]
    assert "INCONCLUSIVE" in render_markdown(_build([("f.json", curated_file)]))


# -- missing data ----------------------------------------------------------


def test_absent_plan_and_provenance_are_reported_as_absent_not_inferred(curated_file):
    curated_file["provenance"].pop("git_commit")
    report = _build([("f.json", curated_file)])

    run = report["curated"]["runs"][0]
    assert run["provenance"]["git_commit"] == NOT_RECORDED
    assert run["provenance"]["prompt_digest"] == NOT_RECORDED
    for stage in ("exploratory", "confirmatory"):
        assert report["sample_plan"]["stages"][stage] == {"status": "not_declared"}
    assert report["sample_plan"]["confirmatory_assessment"] is None


def test_an_incomplete_plan_names_what_it_lacks_and_defaults_nothing():
    plan = {"stages": {"confirmatory": {"declared_at": "2026-10-09T00:00:00+00:00",
                                        "sample_rate": 0.1}}}
    stage = assess_plan(plan)["confirmatory"]

    assert stage["status"] == "incomplete"
    assert set(stage["missing"]) == {"target_decisions", "coverage_floor",
                                     "min_examples_per_category"}
    assert "coverage_floor" not in stage["plan"]


def test_a_report_with_no_model_run_says_the_model_is_unmeasured(curated_file):
    curated_file["model"] = None
    report = _build([("f.json", curated_file)])

    assert report["curated"]["runs"][0]["model"] is None
    assert any("unmeasured" in line for line in report["recommendation"])


def test_unreadable_shadow_rows_are_not_reported_as_zero_traffic():
    report = _build(rows=None, shadow_unavailable="database not readable")
    text = render_markdown(report)

    assert report["shadow"]["available"] is False
    assert report["shadow"]["eligible"] is None
    assert "not a finding of zero traffic" in text
    assert "could not be read" in " ".join(report["recommendation"])


def test_no_rows_is_a_finding_distinct_from_unavailable():
    report = _build(rows=[], tallies={})

    assert report["shadow"]["available"] is True and report["shadow"]["eligible"] == 0
    assert "No shadow rows in the reported window" in render_markdown(report)


def test_a_windowed_run_does_not_attribute_the_untimestamped_tallies():
    shadow = summarize_shadow([_row()], None)

    assert shadow["tallies_attributed"] is False
    assert "omission, not by measurement" in render_markdown(_build(rows=[_row()], tallies=None))


def test_a_file_that_is_not_a_curated_result_is_refused():
    with pytest.raises(ReportInputError):
        summarize_curated_run({"instrument": "retrieval"}, "x.json")


def test_mixed_configurations_are_flagged_not_pooled():
    rows = [_row(), _row(manifest={"rule_set_digest": "r2", "prompt_digest": "p",
                                   "generation": {"model": "m"}})]
    shadow = summarize_shadow(rows, {})

    assert shadow["single_configuration"] is False and len(shadow["configurations"]) == 2


# -- the confirmatory plan -------------------------------------------------


def test_the_coverage_floor_and_target_are_judged_against_the_declared_plan():
    stage = {"plan": {"coverage_floor": 0.8, "target_decisions": 3}}
    met = summarize_shadow([_row(), _row(), _row(), _row("skipped", outcome="x")], {})
    short = summarize_shadow([_row(), _row("skipped", outcome="x")], {})

    assert assess_confirmatory(stage, met, 0)["floor"] == "not met"  # 3/4 < 0.8
    assert assess_confirmatory(stage, met, 0)["target"] == "met"
    assert assess_confirmatory(stage, short, 2)["target"] == "not met"
    assert assess_confirmatory(stage, short, 2)["rows_before_declaration_excluded"] == 2


# -- reproducible, and honest in what it recommends ------------------------


def test_the_same_inputs_give_the_same_bytes_whatever_the_row_order(curated_file):
    rows = [_row(), _row("skipped", outcome="answer_breaker_open"), _row(reclaims=1)]
    one = _build([("f.json", curated_file)], rows, {"record_failed": 1})
    two = _build([("f.json", curated_file)], list(reversed(rows)), {"record_failed": 1})

    assert to_json(one) == to_json(two)
    assert render_markdown(one) == render_markdown(two)
    assert not re.search(r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+", to_json(one))


def test_the_report_never_authorizes_on_and_states_what_it_cannot_measure(curated_file):
    report = _build([("f.json", curated_file)], [_row()], {})
    text = render_markdown(report)

    assert "not authorization" in text and "satisfies none of them" in text
    for phrase in ("Answer quality and claim support", "Reader-visible end-to-end latency",
                   "Page precision"):
        assert phrase in text
    assert "no demonstrated statistical basis" in text
    assert len(report["on_gates"]) == 5


def test_the_safety_tests_the_report_cites_exist():
    root = Path(__file__).resolve().parents[3]
    for tests in SAFETY_TESTS.values():
        for node in tests:
            path, _, name = node.partition("::")
            source = (root / path).read_text(encoding="utf-8")
            assert not name or re.search(rf"^def {name}\b", source, re.M), node


def test_the_command_reads_no_question_text_and_no_turn_identifier():
    assert "turn" not in ROW_FIELDS and "turn_id" not in ROW_FIELDS
    assert not {"question", "resolved_question", "answer", "reasoning"} & set(ROW_FIELDS)


# -- the command -----------------------------------------------------------


@pytest.mark.db_required
@pytest.mark.django_db
def test_the_confirmatory_stage_refuses_without_a_declared_plan(tmp_path):
    with pytest.raises(CommandError, match="confirmatory sample plan is not declared"):
        call_command("report_evidence_pilot", "--stage", "confirmatory",
                     "--out", str(tmp_path), "--no-write")


@pytest.mark.db_required
@pytest.mark.django_db
def test_the_command_writes_json_and_markdown_with_no_database_rows(tmp_path, curated_file):
    curated = tmp_path / "20261001-000000-evidence-x.json"
    curated.write_text(json.dumps(curated_file), encoding="utf-8")

    call_command("report_evidence_pilot", "--curated", str(curated),
                 "--out", str(tmp_path), "--stamp", "S")

    data = json.loads((tmp_path / "S-evidence-pilot-exploratory.json").read_text(encoding="utf-8"))
    assert data["shadow"]["available"] is True and data["shadow"]["eligible"] == 0
    assert (tmp_path / "S-evidence-pilot-exploratory.md").exists()
