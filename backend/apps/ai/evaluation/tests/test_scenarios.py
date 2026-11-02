import json
import pytest
from apps.ai.evaluation.scenarios import BROWSER_CHECKS, browser_result, junit_result
from apps.ai.evaluation.tests.test_replay_contract import Reader, case
from apps.ai.evaluation.replay import collect_case

def test_actions_and_observer():
    actions, observations = [], []
    result = collect_case(Reader(), case(), before_turn=lambda *args: actions.append(args),
                          observe=lambda *args: observations.append(args))
    assert [number for number, cid in actions] == [1, 2]
    assert len(observations) == 2 and result["turns"][0]["public_events"][0][0] == "done"

@pytest.mark.parametrize("xml,code,status,passed", [
    ('<testsuite><testcase/></testsuite>', 0, "measured", True),
    ('<testsuite><testcase><skipped/></testcase></testsuite>', 0, "not_measured", False),
    ('<testsuite><testcase><failure>SECRET</failure></testcase></testsuite>', 1, "measured", False),
    ('<testsuite><testcase><error/></testcase></testsuite>', 1, "not_measured", False),
    ('<testsuite/>', 5, "not_measured", False),
    ('<testsuite><testcase/></testsuite>', 2, "not_measured", False)])
def test_missing_environments_never_pass(tmp_path, xml, code, status, passed):
    path = tmp_path / "junit.xml"
    path.write_text(xml)
    result = junit_result(path, code)
    assert (result["status"], result["passed"]) == (status, passed)
    assert "SECRET" not in json.dumps(result)

def browser():
    return {"operator": "Named reviewer", "timestamp_utc": "2026-10-30T00:00:00Z",
            "git_commit": "abc", "browser": "Chromium", "viewport": "390x844", "conversation_id": 1,
            "checks": {key: {"status": "measured", "passed": True, "evidence_ref": "private screenshot"} for key in BROWSER_CHECKS}}

def test_browser_requires_all_surfaces():
    assert browser_result()["status"] == "not_measured"
    data = browser()
    assert browser_result(data)["passed"]
    assert "private screenshot" not in json.dumps(browser_result(data))
    data["checks"].pop("exported")
    with pytest.raises(ValueError):
        browser_result(data)

def test_unmeasured_or_failed_browser_blocks_enablement():
    data = browser()
    data["checks"]["mobile"] = {"status": "not_measured"}
    assert not browser_result(data)["passed"]
    data = browser()
    data["checks"]["copied"]["passed"] = False
    assert browser_result(data)["status"] == "measured" and not browser_result(data)["passed"]


def test_invalid_report_is_not_measured(tmp_path):
    path = tmp_path / "report.xml"
    path.write_text("incomplete")
    assert junit_result(path, 2)["status"] == "not_measured"


@pytest.mark.parametrize("declaration", [
    '<!ENTITY payload "expanded content">',
    '<!ENTITY payload SYSTEM "file:///must-not-be-read">',
])
def test_xml_entities_are_rejected_as_unmeasured(tmp_path, declaration):
    path = tmp_path / "report.xml"
    path.write_text(
        f'<!DOCTYPE testsuite [{declaration}]>'
        '<testsuite><testcase><system-out>&payload;</system-out></testcase></testsuite>'
    )
    result = junit_result(path, 0)
    assert result["status"] == "not_measured"
    assert not result["passed"]
    assert "expanded content" not in json.dumps(result)
