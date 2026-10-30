"""IR-608 scenario evidence. Contract checks never stand in for a browser/worker run."""
from __future__ import annotations

import xml.etree.ElementTree as ET

# Fixed suites: an operator cannot turn an unrelated passing test into safety evidence.
SUITES = {
    "access_and_recovery": ("deterministic_provider_contract", [
        "apps/ai/evaluation/tests/test_scenario_http.py",
        "apps/ai/tests/test_controller_http.py",
        "apps/ai/tests/test_controller_security_http.py",
        "apps/ai/tests/test_public_protocol_http.py",
        "apps/ai/tests/test_public_history_http.py",
        "apps/ai/research/tests/test_general_tools.py",
    ]),
    "durability": ("postgres_independent_processes_scripted_provider", [
        "apps/ai/tests/test_durable_processes.py",
        "apps/ai/tests/test_durable_ask_http.py",
        "apps/ai/tests/test_conversation_state.py",
    ]),
}
BROWSER_CHECKS = (
    "live", "reopened", "copied", "exported", "paper_chat", "mobile",
    "keyboard", "accessible_summary", "ask_notice_before_submit", "paper_notice_before_submit",
)


def junit_result(path, returncode):
    """Only counts leave pytest; failure messages can contain protected paper text."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return {"status": "not_measured", "passed": False, "reason": "invalid_or_missing_test_report"}
    rows = list(root.iter("testcase"))
    failed = sum(row.find("failure") is not None for row in rows)
    errors = sum(row.find("error") is not None for row in rows)
    skipped = sum(row.find("skipped") is not None for row in rows)
    complete = bool(rows) and not errors and not skipped and returncode in (0, 1)
    status = "measured" if complete or failed else "not_measured"
    return {"status": status, "passed": bool(complete and returncode == 0 and not failed),
            "tests": len(rows), "failed": failed, "errors": errors, "skipped": skipped,
            "checks": [{"name": row.get("classname", "") + "." + row.get("name", ""),
                        "status": "not_measured" if row.find("skipped") is not None or row.find("error") is not None else "measured",
                        "passed": not any(row.find(tag) is not None for tag in ("failure", "error", "skipped"))}
                       for row in rows],
            "reason": ("assertion_failed" if failed else "missing_environment_or_incomplete_suite"
                       if status == "not_measured" else None)}



def browser_result(evidence=None):
    """Named manual browser exercise; missing surfaces cannot be inferred from jsdom."""
    if not evidence:
        return {"status": "not_measured", "passed": False, "kind": "manual_browser",
                "reason": "browser_exercise_not_supplied"}
    required = ("operator", "timestamp_utc", "git_commit", "browser", "viewport", "conversation_id")
    if any(not evidence.get(key) for key in required):
        raise ValueError("browser evidence needs operator, time, commit, browser, viewport and Conversation")
    checks = evidence.get("checks", {})
    if set(checks) != set(BROWSER_CHECKS):
        raise ValueError("browser evidence must name every required surface/check")
    for check in checks.values():
        if check.get("status") not in ("measured", "not_measured"):
            raise ValueError("invalid browser measurement status")
        if check["status"] == "measured" and (type(check.get("passed")) is not bool or
                                              not check.get("evidence_ref")):
            raise ValueError("measured browser checks need a boolean result and private evidence reference")
    complete = all(check["status"] == "measured" for check in checks.values())
    # No supplied text, title, screenshot or diagnostic is copied to the report.
    return {"status": "measured" if complete else "not_measured",
            "passed": complete and all(check.get("passed") is True for check in checks.values()),
            "kind": "manual_browser", "operator": evidence["operator"],
            "git_commit": evidence["git_commit"],
            "checks": {key: {"status": value["status"], "passed": value.get("passed") is True}
                       for key, value in checks.items()}}
