"""The audit gate's silent-pass paths, closed (IR-633).

IR-613's post-merge review found ways the gate passed when it should not, or
failed to honour an entry it should have. One test class per path. Nothing
here touches the network: OSV is injected.
"""
from datetime import date
import json
import textwrap

import pytest

from security.audit_gate import (
    AllowlistEntry,
    AllowlistError,
    evaluate,
    findings_from_npm_audit,
    findings_from_pip_audit,
    load_allowlist,
    main,
    osv_record,
)

TODAY = date(2026, 10, 29)


def entry(fid):
    return AllowlistEntry(id=fid, reason="r", owner="o", expires=date(2026, 12, 1))


class TestSkippedDependencies:
    REPORT = {"dependencies": [
        {"name": "localpkg", "skip_reason": "Dependency not found on PyPI and could not be audited"},
        {"name": "django", "version": "5.2.17", "vulns": []},
    ]}

    def test_a_skipped_dependency_blocks(self):
        # pip-audit could not look at it, so nothing says it is safe.
        [finding] = findings_from_pip_audit(self.REPORT, lambda ids: "low")
        assert finding.id == "skipped:localpkg"
        assert finding.severity == "high"
        assert "could not be audited" in finding.package
        assert [f.id for f in evaluate([finding], []).blocking] == ["skipped:localpkg"]

    def test_it_can_be_accepted_by_package_name(self):
        [finding] = findings_from_pip_audit(self.REPORT, lambda ids: None)
        assert evaluate([finding], [entry("skipped:localpkg")]).blocking == []


class TestNpmAliases:
    REPORT = {"vulnerabilities": {"zod": {"via": [
        {"url": "https://github.com/advisories/GHSA-mrhx-c7xc-m3w5", "severity": "high",
         "name": "zod", "range": "<4.6.6"},
    ]}}}

    def test_a_cve_entry_matches_an_npm_finding(self):
        findings = findings_from_npm_audit(self.REPORT, aliases_of=lambda ghsa: ("CVE-2026-1",))
        assert evaluate(findings, [entry("CVE-2026-1")]).blocking == []

    def test_without_aliases_only_the_ghsa_matches(self):
        findings = findings_from_npm_audit(self.REPORT)
        assert len(evaluate(findings, [entry("CVE-2026-1")]).blocking) == 1
        assert evaluate(findings, [entry("GHSA-mrhx-c7xc-m3w5")]).blocking == []


class TestIdMatching:
    def test_ids_match_regardless_of_case(self):
        [finding] = findings_from_npm_audit(TestNpmAliases.REPORT)
        assert evaluate([finding], [entry("ghsa-MRHX-c7xc-m3w5")]).blocking == []

    def test_a_duplicate_id_fails_the_allowlist(self, tmp_path):
        path = tmp_path / "allowlist.yml"
        path.write_text(textwrap.dedent("""
            entries:
              - {id: GHSA-aaaa-bbbb-cccc, reason: r, owner: o, expires: 2026-12-01}
              - {id: ghsa-aaaa-bbbb-cccc, reason: r2, owner: o, expires: 2026-12-01}
        """), encoding="utf-8")
        with pytest.raises(AllowlistError, match="duplicate"):
            load_allowlist(path, TODAY)


class TestOsvFailures:
    @pytest.mark.parametrize("error", [ConnectionResetError("reset"), TimeoutError(), ValueError("bad json")])
    def test_a_failed_lookup_is_unknown_not_a_crash(self, monkeypatch, error):
        def boom(*args, **kwargs):
            raise error
        monkeypatch.setattr("urllib.request.urlopen", boom)
        assert osv_record("GHSA-x") is None

    def test_an_http_protocol_error_is_unknown_too(self, monkeypatch):
        import http.client

        def boom(*args, **kwargs):
            raise http.client.IncompleteRead(b"")
        monkeypatch.setattr("urllib.request.urlopen", boom)
        assert osv_record("GHSA-x") is None


class TestMain:
    """Exit codes, which are what CI acts on."""

    @pytest.fixture
    def files(self, tmp_path):
        allowlist = tmp_path / "allowlist.yml"
        allowlist.write_text("entries: []\n", encoding="utf-8")
        clean_pip = tmp_path / "pip.json"
        clean_pip.write_text(json.dumps({"dependencies": [{"name": "a", "version": "1", "vulns": []}]}),
                             encoding="utf-8")
        bad_npm = tmp_path / "npm.json"
        bad_npm.write_text(json.dumps(TestNpmAliases.REPORT), encoding="utf-8")
        return allowlist, clean_pip, bad_npm

    def osv(self, vid):
        return None

    def test_a_clean_report_passes(self, files):
        allowlist, clean_pip, _ = files
        assert main(["--allowlist", str(allowlist), "--pip-audit", str(clean_pip)], osv=self.osv) == 0

    def test_a_blocking_finding_fails(self, files):
        allowlist, _, bad_npm = files
        assert main(["--allowlist", str(allowlist), "--npm-audit", str(bad_npm)], osv=self.osv) == 1

    def test_no_report_at_all_fails(self, files):
        allowlist, _, _ = files
        with pytest.raises(SystemExit) as exc:
            main(["--allowlist", str(allowlist)], osv=self.osv)
        assert exc.value.code != 0

    def test_an_expired_allowlist_fails(self, files, tmp_path):
        _, clean_pip, _ = files
        expired = tmp_path / "expired.yml"
        expired.write_text("entries:\n  - {id: X-1, reason: r, owner: o, expires: 2020-01-01}\n", encoding="utf-8")
        assert main(["--allowlist", str(expired), "--pip-audit", str(clean_pip)], osv=self.osv) == 1

    def test_a_cve_entry_accepts_an_npm_finding_end_to_end(self, files, tmp_path):
        _, _, bad_npm = files
        allowlist = tmp_path / "cve.yml"
        allowlist.write_text("entries:\n  - {id: CVE-2026-1, reason: r, owner: o, expires: "
                             f"{date.today().isoformat()}}}\n", encoding="utf-8")

        def osv(vid):
            return {"aliases": ["CVE-2026-1"], "database_specific": {"severity": "HIGH"}}

        assert main(["--allowlist", str(allowlist), "--npm-audit", str(bad_npm)], osv=osv) == 0
