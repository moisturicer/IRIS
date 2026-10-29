"""The dependency-audit gate (IR-613).

Run from the repo root: ``python -m pytest security/tests -q``. Nothing here
touches the network — the severity lookup is injected.
"""
from datetime import date
import textwrap

import pytest

from security.audit_gate import (
    AllowlistError,
    Finding,
    evaluate,
    findings_from_npm_audit,
    findings_from_pip_audit,
    load_allowlist,
)

TODAY = date(2026, 10, 29)


def write(tmp_path, text):
    path = tmp_path / "allowlist.yml"
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


# --- allowlist ---------------------------------------------------------------

def test_an_empty_allowlist_is_valid(tmp_path):
    assert load_allowlist(write(tmp_path, "entries: []\n"), TODAY) == []


def test_a_current_entry_loads(tmp_path):
    entries = load_allowlist(write(tmp_path, """
        entries:
          - id: GHSA-aaaa-bbbb-cccc
            reason: Dev-server only; not shipped.
            owner: Lee Jasmin Adolfo
            expires: 2026-12-01
    """), TODAY)
    assert [e.id for e in entries] == ["GHSA-aaaa-bbbb-cccc"]


def test_an_expired_entry_fails(tmp_path):
    path = write(tmp_path, """
        entries:
          - id: GHSA-aaaa-bbbb-cccc
            reason: r
            owner: o
            expires: 2026-10-28
    """)
    with pytest.raises(AllowlistError, match="GHSA-aaaa-bbbb-cccc.*expired"):
        load_allowlist(path, TODAY)


def test_an_entry_expiring_today_is_still_valid(tmp_path):
    path = write(tmp_path, """
        entries:
          - {id: X-1, reason: r, owner: o, expires: 2026-10-29}
    """)
    assert len(load_allowlist(path, TODAY)) == 1


@pytest.mark.parametrize("missing", ["id", "reason", "owner", "expires"])
def test_an_entry_missing_a_field_fails(tmp_path, missing):
    fields = {"id": "X-1", "reason": "r", "owner": "o", "expires": "2026-12-01"}
    del fields[missing]
    body = "".join(f"    {k}: {v}\n" for k, v in fields.items())
    path = write(tmp_path, "entries:\n  -\n" + body)
    with pytest.raises(AllowlistError, match=missing):
        load_allowlist(path, TODAY)


def test_a_blank_reason_fails(tmp_path):
    path = write(tmp_path, """
        entries:
          - {id: X-1, reason: "  ", owner: o, expires: 2026-12-01}
    """)
    with pytest.raises(AllowlistError, match="reason"):
        load_allowlist(path, TODAY)


def test_an_expiry_more_than_90_days_out_fails(tmp_path):
    # Otherwise "expires: 2099-01-01" is a permanent exception with a date on it.
    path = write(tmp_path, """
        entries:
          - {id: X-1, reason: r, owner: o, expires: 2027-01-28}
    """)
    with pytest.raises(AllowlistError, match="90 days"):
        load_allowlist(path, TODAY)


def test_an_expiry_exactly_90_days_out_is_valid(tmp_path):
    path = write(tmp_path, """
        entries:
          - {id: X-1, reason: r, owner: o, expires: 2027-01-27}
    """)
    assert len(load_allowlist(path, TODAY)) == 1


def test_an_unparseable_expiry_fails(tmp_path):
    path = write(tmp_path, """
        entries:
          - {id: X-1, reason: r, owner: o, expires: soon}
    """)
    with pytest.raises(AllowlistError, match="expires"):
        load_allowlist(path, TODAY)


# --- parsing -----------------------------------------------------------------

PIP_AUDIT = {
    "dependencies": [
        {"name": "django", "version": "5.1.15", "vulns": [
            {"id": "PYSEC-1", "aliases": ["GHSA-dj-1", "CVE-1"], "fix_versions": ["5.2.17"]},
        ]},
        {"name": "clean", "version": "1.0", "vulns": []},
    ]
}


def test_pip_audit_findings_carry_their_aliases_and_looked_up_severity():
    seen = []

    def severity_of(ids):
        seen.append(ids)
        return "high"

    [finding] = findings_from_pip_audit(PIP_AUDIT, severity_of)
    assert finding.id == "PYSEC-1"
    assert finding.package == "django 5.1.15"
    assert set(finding.ids) == {"PYSEC-1", "GHSA-dj-1", "CVE-1"}
    assert finding.severity == "high"
    assert seen == [("PYSEC-1", "GHSA-dj-1", "CVE-1")]


def test_a_pip_audit_finding_with_unknown_severity_counts_as_high():
    # Fail closed: a lookup that cannot say how bad it is must not pass.
    [finding] = findings_from_pip_audit(PIP_AUDIT, lambda ids: None)
    assert finding.severity == "high"


NPM_AUDIT = {
    "vulnerabilities": {
        "vite": {
            "severity": "high",
            "via": [
                {"source": 1, "url": "https://github.com/advisories/GHSA-vi-1", "severity": "high",
                 "name": "vite", "range": "<6.4.4"},
                {"source": 2, "url": "https://github.com/advisories/GHSA-vi-2", "severity": "moderate",
                 "name": "vite", "range": "<6"},
                "esbuild",
            ],
        },
        "vitest": {
            "severity": "critical",
            # The same advisory reached through two packages is one finding.
            "via": [{"source": 1, "url": "https://github.com/advisories/GHSA-vi-1", "severity": "high",
                     "name": "vite", "range": "<6.4.4"}],
        },
    }
}


def test_npm_audit_findings_are_one_per_advisory_at_its_own_severity():
    findings = findings_from_npm_audit(NPM_AUDIT)
    by_id = {f.id: f for f in findings}
    assert set(by_id) == {"GHSA-vi-1", "GHSA-vi-2"}
    assert by_id["GHSA-vi-1"].severity == "high"
    assert by_id["GHSA-vi-2"].severity == "moderate"
    assert by_id["GHSA-vi-1"].package == "vite <6.4.4"


# --- the decision ------------------------------------------------------------

def finding(fid, severity, *aliases):
    return Finding(id=fid, ids=(fid, *aliases), package="pkg 1.0", severity=severity)


def entry(fid):
    from security.audit_gate import AllowlistEntry
    return AllowlistEntry(id=fid, reason="r", owner="o", expires=date(2026, 12, 1))


def test_high_and_critical_findings_block():
    result = evaluate([finding("A", "high"), finding("B", "critical")], [])
    assert [f.id for f in result.blocking] == ["A", "B"]


def test_moderate_and_low_findings_are_reported_but_do_not_block():
    result = evaluate([finding("A", "moderate"), finding("B", "low")], [])
    assert result.blocking == []
    assert [f.id for f in result.reported] == ["A", "B"]


def test_an_allowlisted_finding_does_not_block_and_matches_by_alias():
    result = evaluate([finding("PYSEC-1", "high", "CVE-1")], [entry("CVE-1")])
    assert result.blocking == []
    assert [f.id for f in result.allowed] == ["PYSEC-1"]


def test_an_allowlist_entry_matching_nothing_is_reported_as_unused():
    result = evaluate([], [entry("GHSA-gone")])
    assert [e.id for e in result.unused] == ["GHSA-gone"]
