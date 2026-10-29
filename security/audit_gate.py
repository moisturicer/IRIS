"""The dependency-audit gate (IR-613).

CI runs ``pip-audit`` and ``npm audit`` with JSON output, then hands both files
to this script. It fails the job when:

- a **high or critical** finding is not in ``security/allowlist.yml``, or
- any allowlist entry is malformed or **past its expiry date**.

Moderate and low findings are printed but never fail the job.

Why a script and not the tools' own flags: ``npm audit --audit-level=high``
has no allowlist at all, and ``pip-audit`` reports no severity — its
``--ignore-vuln`` ignores an id forever, with no reason, owner or expiry. One
exception file with expiry for both, and later for bandit/semgrep (IR-614), is
the point of the ticket.

pip-audit severity comes from OSV (``api.osv.dev``). A finding whose severity
cannot be determined counts as **high**: an outage at OSV must fail the gate,
not quietly pass it.

Usage (repo root)::

    python -m security.audit_gate --allowlist security/allowlist.yml \\
        --pip-audit pip-audit.json --npm-audit npm-audit.json
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable, Sequence

import yaml

BLOCKING = frozenset({"high", "critical"})
REQUIRED_FIELDS = ("id", "reason", "owner", "expires")
# A far-off expiry is a permanent exception with a date on it.
MAX_EXPIRY = timedelta(days=90)


class AllowlistError(Exception):
    """The allowlist is malformed or holds an expired entry."""


@dataclass(frozen=True)
class AllowlistEntry:
    id: str
    reason: str
    owner: str
    expires: date


@dataclass(frozen=True)
class Finding:
    id: str
    ids: tuple[str, ...]  # the id plus every alias (CVE, GHSA, PYSEC)
    package: str
    severity: str  # low | moderate | high | critical


@dataclass
class Result:
    blocking: list[Finding] = field(default_factory=list)
    allowed: list[Finding] = field(default_factory=list)
    reported: list[Finding] = field(default_factory=list)
    unused: list[AllowlistEntry] = field(default_factory=list)


# --- allowlist ---------------------------------------------------------------

def load_allowlist(path: Path, today: date) -> list[AllowlistEntry]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    raw = data.get("entries") or []
    if not isinstance(raw, list):
        raise AllowlistError("`entries` must be a list")
    entries, problems = [], []
    for n, item in enumerate(raw, 1):
        label = (item or {}).get("id") or f"entry {n}"
        missing = [f for f in REQUIRED_FIELDS if not str((item or {}).get(f) or "").strip()]
        if missing:
            problems.append(f"{label}: missing {', '.join(missing)}")
            continue
        expires = item["expires"]
        if not isinstance(expires, date):
            try:
                expires = date.fromisoformat(str(expires))
            except ValueError:
                problems.append(f"{label}: expires must be YYYY-MM-DD, got {expires!r}")
                continue
        if expires < today:
            problems.append(f"{label}: expired on {expires.isoformat()} (owner: {item['owner']})")
            continue
        if expires > today + MAX_EXPIRY:
            problems.append(f"{label}: expires {expires.isoformat()}, more than "
                            f"{MAX_EXPIRY.days} days out")
            continue
        entries.append(AllowlistEntry(str(item["id"]), str(item["reason"]), str(item["owner"]), expires))
    if problems:
        raise AllowlistError("; ".join(problems))
    return entries


# --- parsing -----------------------------------------------------------------

def findings_from_pip_audit(
    report: dict, severity_of: Callable[[tuple[str, ...]], str | None]
) -> list[Finding]:
    findings = []
    for dep in report.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            ids = (vuln["id"], *vuln.get("aliases", []))
            findings.append(Finding(
                id=vuln["id"],
                ids=ids,
                package=f"{dep['name']} {dep['version']}",
                severity=severity_of(ids) or "high",
            ))
    return findings


def findings_from_npm_audit(report: dict) -> list[Finding]:
    by_id: dict[str, Finding] = {}
    for vuln in report.get("vulnerabilities", {}).values():
        for via in vuln.get("via", []):
            if not isinstance(via, dict):
                continue  # a package name: the advisory itself is listed under it
            ghsa = via["url"].rstrip("/").rsplit("/", 1)[-1]
            by_id.setdefault(ghsa, Finding(
                id=ghsa,
                ids=(ghsa,),
                package=f"{via['name']} {via['range']}",
                severity=via["severity"],
            ))
    return list(by_id.values())


def osv_severity(ids: Sequence[str]) -> str | None:
    """The GitHub-reviewed severity for any of ``ids``, from OSV, or None."""
    for vid in ids:
        try:
            with urllib.request.urlopen(f"https://api.osv.dev/v1/vulns/{vid}", timeout=20) as resp:
                record = json.load(resp)
        except (urllib.error.URLError, TimeoutError, ValueError):
            continue
        severity = (record.get("database_specific") or {}).get("severity")
        if severity:
            return severity.lower()
    return None


# --- the decision ------------------------------------------------------------

def evaluate(findings: Iterable[Finding], allowlist: Sequence[AllowlistEntry]) -> Result:
    result = Result()
    allowed_ids = {e.id for e in allowlist}
    used: set[str] = set()
    for f in findings:
        match = allowed_ids.intersection(f.ids)
        if match:
            used |= match
            result.allowed.append(f)
        elif f.severity in BLOCKING:
            result.blocking.append(f)
        else:
            result.reported.append(f)
    result.unused = [e for e in allowlist if e.id not in used]
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument("--pip-audit", type=Path, action="append", default=[])
    parser.add_argument("--npm-audit", type=Path, action="append", default=[])
    args = parser.parse_args(argv)

    try:
        allowlist = load_allowlist(args.allowlist, date.today())
    except AllowlistError as exc:
        print(f"FAIL allowlist: {exc}")
        return 1

    findings: list[Finding] = []
    for path in args.pip_audit:
        findings += findings_from_pip_audit(json.loads(path.read_text(encoding="utf-8")), osv_severity)
    for path in args.npm_audit:
        findings += findings_from_npm_audit(json.loads(path.read_text(encoding="utf-8")))

    result = evaluate(findings, allowlist)
    for f in result.reported:
        print(f"report  {f.severity:<8} {f.id:<22} {f.package}")
    for f in result.allowed:
        print(f"allowed {f.severity:<8} {f.id:<22} {f.package}")
    for e in result.unused:
        print(f"unused  allowlist entry {e.id} matches no finding; remove it")
    for f in result.blocking:
        print(f"BLOCK   {f.severity:<8} {f.id:<22} {f.package}")
    print(f"{len(result.blocking)} blocking, {len(result.allowed)} allowlisted, "
          f"{len(result.reported)} below the gate")
    return 1 if result.blocking else 0


if __name__ == "__main__":
    sys.exit(main())
