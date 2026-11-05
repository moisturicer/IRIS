"""IR-741: eval_readiness, the operator surface over the readiness manifest.

Free: no database, no vendor, no network. Synthetic fixtures only, so a ``evidence_met``
manifest here proves the command's plumbing, never that any runtime is ready.
"""

import json

import httpx
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ai.evaluation.readiness import SCHEMA_VERSION, canonical_digest, verify_manifest

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
        call_command("eval_readiness", verify=str(written), assert_ready=True)


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
