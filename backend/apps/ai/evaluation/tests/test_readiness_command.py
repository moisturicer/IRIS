"""IR-741: eval_readiness, the operator surface over the readiness manifest.

Free: no database, no vendor, no network. Synthetic fixtures only, so a ``evidence_met``
manifest here proves the command's plumbing, never that any runtime is ready.
"""

import json
from pathlib import Path

import httpx
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ai.evaluation.readiness import (SCHEMA_VERSION, canonical_digest, validate_measurement,
                                          verify_manifest)

from .readiness_fixtures import (PROFILE, SCENARIOS_PASSED, WORKLOAD, campaign_report,
                                 measurements)
from .test_campaign_report import APPROVED


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        pytest.fail("eval_readiness reached the network")

    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)
    monkeypatch.setattr(httpx.Client, "send", refuse)


def _write(path, value):
    path.write_text(json.dumps(value))
    return str(path)


def _inputs(tmp_path, *, scenarios=SCENARIOS_PASSED, with_measurements=True):
    report = campaign_report()
    baseline = campaign_report()
    opts = dict(report=_write(tmp_path / "report.json", report), candidate="runtime",
                baseline=_write(tmp_path / "baseline.json", baseline), baseline_arm="controller",
                baseline_sha256=canonical_digest(baseline),
                workload=_write(tmp_path / "workload.json", WORKLOAD),
                profile=_write(tmp_path / "profile.json", PROFILE),
                approvals=_write(tmp_path / "approvals.json", APPROVED),
                out=str(tmp_path / "out"))
    if scenarios is not None:
        opts["scenarios"] = _write(tmp_path / "scenarios.json", {"scenarios": scenarios})
    if with_measurements:
        opts["measurements"] = _write(tmp_path / "measurements.json", measurements())
    return opts


def _manifest(tmp_path):
    (written,) = (tmp_path / "out").glob("*.json")
    return json.loads(written.read_text())


def test_build_writes_a_manifest_that_records_every_input_it_read(tmp_path):
    opts = _inputs(tmp_path)
    call_command("eval_readiness", build=True, **opts)
    manifest = _manifest(tmp_path)
    assert manifest["schema_version"] == SCHEMA_VERSION
    quality = manifest["gates"]["quality"]["evidence"]
    assert quality[0]["name"] == "report" and quality[0]["path"].endswith("report.json")
    assert len(quality[0]["sha256"]) == 64
    assert manifest["commit"]  # the file's own provenance, outside the sealed manifest
    assert verify_manifest({k: v for k, v in manifest.items() if k != "commit"}) == []


def test_build_blocks_and_says_why_when_a_worker_and_browser_result_is_omitted(tmp_path, capsys):
    partial = {k: v for k, v in SCENARIOS_PASSED.items() if k == "access_and_recovery"}
    call_command("eval_readiness", build=True, **_inputs(tmp_path, scenarios=partial))
    manifest = _manifest(tmp_path)
    assert manifest["status"] == "blocked"
    assert manifest["gates"]["postgres_workers"]["status"] == "not_measured"
    assert manifest["gates"]["browser_accessibility"]["status"] == "not_measured"
    out = capsys.readouterr().out
    assert "BLOCKED" in out and "postgres_workers" in out and "browser_accessibility" in out


def test_build_without_measurements_is_blocked_not_green(tmp_path):
    call_command("eval_readiness", build=True, **_inputs(tmp_path, with_measurements=False))
    manifest = _manifest(tmp_path)
    assert manifest["status"] == "blocked"
    assert manifest["gates"]["workload"]["status"] == "not_measured"
    assert manifest["gates"]["cost"]["status"] == "not_measured"


def test_a_baseline_that_does_not_match_its_pinned_digest_is_incomparable(tmp_path):
    opts = _inputs(tmp_path)
    opts["baseline_sha256"] = "0" * 64
    call_command("eval_readiness", build=True, **opts)
    assert _manifest(tmp_path)["gates"]["baseline"]["status"] == "incomparable"


def test_build_needs_a_report_and_names_a_half_given_baseline(tmp_path):
    with pytest.raises(CommandError, match="--report"):
        call_command("eval_readiness", build=True, out=str(tmp_path))
    opts = _inputs(tmp_path)
    del opts["baseline_arm"]
    with pytest.raises(CommandError, match="--baseline-arm"):
        call_command("eval_readiness", build=True, **opts)


def test_exactly_one_mode_is_required(tmp_path):
    with pytest.raises(CommandError, match="exactly one"):
        call_command("eval_readiness", out=str(tmp_path))
    with pytest.raises(CommandError, match="exactly one"):
        call_command("eval_readiness", build=True, preflight=True, out=str(tmp_path))


def test_verify_accepts_a_sound_manifest_and_assert_ready_refuses_a_blocked_one(tmp_path):
    call_command("eval_readiness", build=True,
                 **_inputs(tmp_path, scenarios={}, with_measurements=False))
    (written,) = (tmp_path / "out").glob("*.json")
    call_command("eval_readiness", verify=str(written))
    with pytest.raises(CommandError, match="blocked"):
        call_command("eval_readiness", verify=str(written), assert_ready=True,
                     expect_commit="rt1")


def test_verify_catches_a_manifest_edited_to_say_ready(tmp_path):
    call_command("eval_readiness", build=True,
                 **_inputs(tmp_path, scenarios={}, with_measurements=False))
    (written,) = (tmp_path / "out").glob("*.json")
    edited = json.loads(written.read_text())
    edited["status"] = "evidence_met"
    path = _write(tmp_path / "edited.json", edited)
    with pytest.raises(CommandError, match="digest"):
        call_command("eval_readiness", verify=path)


def test_preflight_names_every_missing_declaration_cap_and_approval(tmp_path, capsys):
    thin = {**PROFILE, "caps": {k: v for k, v in PROFILE["caps"].items()
                                if k != "campaign_cost_usd"}}
    with pytest.raises(CommandError, match="not allowed"):
        call_command("eval_readiness", preflight=True,
                     workload=_write(tmp_path / "w.json", WORKLOAD),
                     profile=_write(tmp_path / "p.json", thin))
    out = capsys.readouterr().out
    assert "profile.caps.campaign_cost_usd" in out and "approvals." in out


def test_preflight_allows_only_a_complete_declaration(tmp_path, capsys):
    call_command("eval_readiness", preflight=True,
                 workload=_write(tmp_path / "w.json", WORKLOAD),
                 profile=_write(tmp_path / "p.json", PROFILE),
                 approvals=_write(tmp_path / "a.json", APPROVED))
    assert "allowed" in capsys.readouterr().out


def test_a_wrong_mode_capability_report_is_refused_not_blended_in(tmp_path):
    opts = _inputs(tmp_path)
    opts["capability"] = _write(tmp_path / "cap.json", campaign_report())  # architecture mode
    with pytest.raises(CommandError, match="capability"):
        call_command("eval_readiness", build=True, **opts)


def test_check_files_catches_an_input_changed_after_the_manifest_was_built(tmp_path):
    opts = _inputs(tmp_path)
    call_command("eval_readiness", build=True, **opts)
    (written,) = (tmp_path / "out").glob("*.json")
    call_command("eval_readiness", verify=str(written), check_files=True)
    (tmp_path / "scenarios.json").write_text(json.dumps({"scenarios": {}}))
    with pytest.raises(CommandError, match="scenarios.*changed"):
        call_command("eval_readiness", verify=str(written), check_files=True)


def test_assert_ready_re_hashes_inputs_so_a_hand_made_manifest_cannot_pass(tmp_path):
    call_command("eval_readiness", build=True, **_inputs(tmp_path))
    (written,) = (tmp_path / "out").glob("*.json")
    m = json.loads(written.read_text())
    assert m["status"] == "evidence_met"  # the synthetic fixture: plumbing only
    (tmp_path / "report.json").unlink()
    # The rebuild reads every input, so a missing one is named as unreadable.
    with pytest.raises(CommandError, match="report.*cannot be read"):
        call_command("eval_readiness", verify=str(written), assert_ready=True,
                     expect_commit="rt1")


def test_malformed_inputs_are_command_errors_not_tracebacks(tmp_path):
    (tmp_path / "list.json").write_text("[]")
    with pytest.raises(CommandError, match="JSON object"):
        call_command("eval_readiness", preflight=True, workload=str(tmp_path / "list.json"))
    opts = _inputs(tmp_path)
    opts["scenarios"] = str(tmp_path / "list.json")
    with pytest.raises(CommandError, match="--scenarios"):
        call_command("eval_readiness", build=True, **opts)


def test_validate_measurement_accepts_a_well_formed_file_and_says_it_is_not_evidence(
        tmp_path, capsys):
    call_command("eval_readiness", validate_measurement=_write(tmp_path / "m.json",
                                                              measurements()))
    assert "not evidence" in capsys.readouterr().out


def test_validate_measurement_names_each_defect(tmp_path, capsys):
    bad = measurements(concurrency=0, providers="mock")
    with pytest.raises(CommandError, match="2 defect"):
        call_command("eval_readiness", validate_measurement=_write(tmp_path / "m.json", bad))
    out = capsys.readouterr().out
    assert "DEFECT concurrency" in out and "DEFECT providers" in out


def test_the_committed_example_measurement_satisfies_the_contract_and_is_marked_fake():
    path = (Path(__file__).resolve().parents[5] / "docs" / "evaluation" / "general-tools"
            / "workload-measurement.example.json")
    if not path.exists():
        pytest.skip("docs/ is not part of this checkout (backend-only image)")
    example = json.loads(path.read_text(encoding="utf-8"))
    assert example["providers"] == "fake" and example["run_id"].startswith("EXAMPLE-ONLY")
    assert validate_measurement(example) == []


def test_an_eval_scenarios_run_file_carries_its_commit_into_the_gates(tmp_path):
    rows = {k: {x: y for x, y in v.items() if x != "git_commit"}
            for k, v in SCENARIOS_PASSED.items() if k != "browser"}
    run = {"schema_version": 1, "issue": "IR-608", "git_commit": "rt1", "providers": "fake",
           "scenarios": {**rows, "browser": SCENARIOS_PASSED["browser"]}}
    opts = _inputs(tmp_path)
    opts["scenarios"] = _write(tmp_path / "scenarios.json", run)
    call_command("eval_readiness", build=True, **opts)
    manifest = _manifest(tmp_path)
    assert manifest["gates"]["postgres_workers"]["status"] == "met"
    assert manifest["gates"]["postgres_workers"]["git_commit_source"] == "run_file"
    run["git_commit"] = "unknown"
    opts["scenarios"] = _write(tmp_path / "scenarios.json", run)
    next((tmp_path / "out").glob("*.json")).unlink()
    call_command("eval_readiness", build=True, **opts)
    assert _manifest(tmp_path)["gates"]["postgres_workers"]["provenance"] == "unverified"


def test_build_prints_the_policy_decisions_it_applies(tmp_path, capsys):
    call_command("eval_readiness", build=True, **_inputs(tmp_path))
    out = capsys.readouterr().out
    for decision in ("objectives_on_point_estimate", "minimum_success_rate",
                     "commit_from_run_file"):
        assert f"DECISION {decision} (confirmed, Jive Tyler Revalde, 2026-11-07)" in out


def test_assert_ready_needs_a_commit_and_refuses_a_resealed_verdict(tmp_path):
    call_command("eval_readiness", build=True, **_inputs(tmp_path))
    (written,) = (tmp_path / "out").glob("*.json")
    with pytest.raises(CommandError, match="needs --expect-commit"):
        call_command("eval_readiness", verify=str(written), assert_ready=True)
    call_command("eval_readiness", verify=str(written), assert_ready=True, expect_commit="rt1")
    m = json.loads(written.read_text())
    m["gates"]["cost"]["total_usd"] = 0.0
    body = {k: v for k, v in m.items() if k not in ("manifest_sha256", "commit")}
    m["manifest_sha256"] = canonical_digest(body)
    path = _write(tmp_path / "resealed.json", m)
    call_command("eval_readiness", verify=path)                 # internally consistent
    with pytest.raises(CommandError, match="does not follow from its inputs"):
        call_command("eval_readiness", verify=path, assert_ready=True, expect_commit="rt1")
