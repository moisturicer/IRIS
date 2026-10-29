"""The dependency-audit gate (IR-613).

CI runs ``pip-audit`` and ``npm audit`` with JSON output, then hands both files
to this script. It fails the job when:

- a **high or critical** finding is not in ``security/allowlist.yml``, or
- any allowlist entry is malformed, duplicated or **past its expiry date**, or
- a dependency could not be audited, or no report was given at all (IR-633).

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
import http.client
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
    entries, problems, seen = [], [], set()
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
        if str(item["id"]).upper() in seen:
            problems.append(f"{label}: duplicate id")
            continue
        seen.add(str(item["id"]).upper())
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
        if dep.get("skip_reason"):
            # pip-audit could not look at it, so nothing says it is safe (IR-633).
            # Accepted, if at all, by an entry with id `skipped:<package>`.
            findings.append(Finding(
                id=f"skipped:{dep['name']}",
                ids=(f"skipped:{dep['name']}",),
                package=f"{dep['name']} ({dep['skip_reason']})",
                severity="high",
            ))
            continue
        for vuln in dep.get("vulns", []):
            ids = (vuln["id"], *vuln.get("aliases", []))
            findings.append(Finding(
                id=vuln["id"],
                ids=ids,
                package=f"{dep['name']} {dep['version']}",
                severity=severity_of(ids) or "high",
            ))
    return findings


def findings_from_npm_audit(
    report: dict, aliases_of: Callable[[str], Sequence[str]] = lambda ghsa: ()
) -> list[Finding]:
    """One finding per advisory. npm reports only the GHSA id, so `aliases_of`
    supplies the rest (CVE) for allowlist matching (IR-633)."""
    by_id: dict[str, Finding] = {}
    for vuln in report.get("vulnerabilities", {}).values():
        for via in vuln.get("via", []):
            if not isinstance(via, dict):
                continue  # a package name: the advisory itself is listed under it
            ghsa = via["url"].rstrip("/").rsplit("/", 1)[-1]
            if ghsa in by_id:
                continue  # the same advisory reached through another package
            by_id[ghsa] = Finding(
                id=ghsa,
                ids=(ghsa, *aliases_of(ghsa)),
                package=f"{via['name']} {via['range']}",
                severity=via["severity"],
            )
    return list(by_id.values())


def osv_record(vid: str) -> dict | None:
    """OSV's record for ``vid``, or None when it cannot be had.

    Any network, protocol or parse failure is None -- "unknown" -- which the
    callers treat as high severity and no aliases: it can fail the gate, never
    pass it.
    """
    try:
        with urllib.request.urlopen(f"https://api.osv.dev/v1/vulns/{vid}", timeout=20) as resp:
            return json.load(resp)
    except (OSError, http.client.HTTPException, ValueError):
        return None


def severity_lookup(osv: Callable[[str], dict | None]) -> Callable[[Sequence[str]], str | None]:
    """The GitHub-reviewed severity for any of the ids, from OSV, or None."""
    def severity_of(ids):
        for vid in ids:
            severity = ((osv(vid) or {}).get("database_specific") or {}).get("severity")
            if severity:
                return severity.lower()
        return None
    return severity_of


def alias_lookup(osv: Callable[[str], dict | None]) -> Callable[[str], Sequence[str]]:
    return lambda vid: tuple((osv(vid) or {}).get("aliases") or ())


# --- the decision ------------------------------------------------------------

def evaluate(findings: Iterable[Finding], allowlist: Sequence[AllowlistEntry]) -> Result:
    result = Result()
    # Ids compare case-insensitively: GHSA ids are written both ways.
    allowed_ids = {e.id.upper() for e in allowlist}
    used: set[str] = set()
    for f in findings:
        match = allowed_ids.intersection(i.upper() for i in f.ids)
        if match:
            used |= match
            result.allowed.append(f)
        elif f.severity in BLOCKING:
            result.blocking.append(f)
        else:
            result.reported.append(f)
    result.unused = [e for e in allowlist if e.id.upper() not in used]
    return result


def main(argv: Sequence[str] | None = None, osv: Callable[[str], dict | None] = osv_record) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument("--pip-audit", type=Path, action="append", default=None)
    parser.add_argument("--npm-audit", type=Path, action="append", default=None)
    args = parser.parse_args(argv)
    if not args.pip_audit and not args.npm_audit:
        # Nothing audited is not "nothing found" (IR-633).
        parser.error("give at least one --pip-audit or --npm-audit report")

    try:
        allowlist = load_allowlist(args.allowlist, date.today())
    except AllowlistError as exc:
        print(f"FAIL allowlist: {exc}")
        return 1

    findings: list[Finding] = []
    for path in args.pip_audit or []:
        findings += findings_from_pip_audit(json.loads(path.read_text(encoding="utf-8")), severity_lookup(osv))
    for path in args.npm_audit or []:
        findings += findings_from_npm_audit(json.loads(path.read_text(encoding="utf-8")), alias_lookup(osv))

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
