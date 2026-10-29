"""bandit and semgrep through the same gate (IR-614).

A SAST finding is named ``<tool>:<rule>:<path>``, so an allowlist entry
accepts one rule in one file -- never a rule everywhere -- and survives the
code above it moving. Nothing here runs either tool: reports are fixtures in
the shape each tool writes with ``-f json`` / ``--json``.
"""
from datetime import date
import json

import pytest

from security.audit_gate import (
    AllowlistEntry,
    evaluate,
    findings_from_bandit,
    findings_from_semgrep,
    main,
)


def entry(fid):
    return AllowlistEntry(id=fid, reason="r", owner="o", expires=date(2026, 12, 1))


def bandit_result(test_id="B602", severity="HIGH", filename="backend/core/utils.py", line=10):
    return {
        "test_id": test_id, "test_name": "subprocess_popen_with_shell_equals_true",
        "issue_severity": severity, "issue_confidence": "HIGH",
        "filename": filename, "line_number": line, "issue_text": "shell=True",
    }


class TestBandit:
    def test_a_high_finding_blocks_under_a_rule_and_file_id(self):
        [finding] = findings_from_bandit({"errors": [], "results": [bandit_result()]})
        assert finding.id == "bandit:B602:backend/core/utils.py"
        assert finding.severity == "high"
        assert [f.id for f in evaluate([finding], []).blocking] == [finding.id]

    def test_a_file_bandit_could_not_parse_blocks(self):
        # Unscanned is not "nothing found" (IR-633's rule, carried over).
        report = {"errors": [{"filename": "backend/x.py", "reason": "syntax error while parsing AST"}],
                  "results": []}
        [finding] = findings_from_bandit(report)
        assert finding.id == "bandit:error:backend/x.py"
        assert finding.severity == "high"


def semgrep_result(check_id="python.django.security.injection.sql.sql-injection-using-raw",
                   severity="ERROR", path="backend/apps/records/views.py"):
    return {"check_id": check_id, "path": path, "start": {"line": 12},
            "extra": {"severity": severity, "message": "raw SQL"}}


class TestSemgrep:
    def test_an_error_finding_blocks_under_a_rule_and_file_id(self):
        [finding] = findings_from_semgrep({"errors": [], "results": [semgrep_result()]})
        assert finding.id == ("semgrep:python.django.security.injection.sql."
                              "sql-injection-using-raw:backend/apps/records/views.py")
        assert finding.severity == "high"

    def test_a_warning_is_reported_but_does_not_block(self):
        findings = findings_from_semgrep({"errors": [], "results": [semgrep_result(severity="WARNING")]})
        result = evaluate(findings, [])
        assert result.blocking == [] and len(result.reported) == 1

    def test_a_scan_error_blocks_but_a_warning_level_one_is_only_reported(self):
        # A rule that timed out on one file is a warning; a file semgrep could
        # not read at all is an error, and an unscanned file is not safe.
        report = {"results": [], "errors": [
            {"level": "error", "type": "Fatal error", "path": "backend/a.py", "message": "m"},
            {"level": "warn", "type": "Timeout", "path": "backend/b.py", "message": "m"},
        ]}
        result = evaluate(findings_from_semgrep(report), [])
        assert [f.id for f in result.blocking] == ["semgrep:error:backend/a.py"]
        assert [f.id for f in result.reported] == ["semgrep:warn:backend/b.py"]

    def test_an_entry_accepts_that_rule_in_that_file_only(self):
        here, there = semgrep_result(), semgrep_result(path="backend/apps/reviews/views.py")
        findings = findings_from_semgrep({"errors": [], "results": [here, there]})
        result = evaluate(findings, [entry(findings[0].id)])
        assert [f.id for f in result.blocking] == [findings[1].id]


class TestMain:
    """The CLI CI calls. OSV is never needed for SAST, so it is made to fail."""

    @staticmethod
    def run(tmp_path, allowlist="entries: []\n", **reports):
        (tmp_path / "allow.yml").write_text(allowlist, encoding="utf-8")
        argv = ["--allowlist", str(tmp_path / "allow.yml")]
        for tool, report in reports.items():
            path = tmp_path / f"{tool}.json"
            path.write_text(report if isinstance(report, str) else json.dumps(report), encoding="utf-8")
            argv += [f"--{tool}", str(path)]
        return main(argv, osv=lambda vid: pytest.fail("SAST must not call OSV"))

    def test_a_high_bandit_finding_fails_the_job(self, tmp_path, capsys):
        assert self.run(tmp_path, bandit={"errors": [], "results": [bandit_result()]}) == 1
        assert "BLOCK   high     bandit:B602:backend/core/utils.py" in capsys.readouterr().out

    def test_clean_reports_pass(self, tmp_path):
        clean = {"errors": [], "results": [bandit_result(severity="MEDIUM")]}
        assert self.run(tmp_path, bandit=clean, semgrep={"errors": [], "results": []}) == 0

    def test_an_allowlisted_finding_passes(self, tmp_path):
        allow = ("entries:\n  - {id: 'bandit:B602:backend/core/utils.py', reason: r, owner: o,"
                 f" expires: {date.today().isoformat()}}}\n")
        assert self.run(tmp_path, allow, bandit={"errors": [], "results": [bandit_result()]}) == 0

    @pytest.mark.parametrize("garbled", ["", "{}", '{"errors": []}', "not json"])
    def test_a_garbled_report_fails_rather_than_passing(self, tmp_path, capsys, garbled):
        # A tool that crashed writes nothing usable; that is not "nothing found".
        assert self.run(tmp_path, semgrep=garbled) == 1
        assert "FAIL semgrep" in capsys.readouterr().out
