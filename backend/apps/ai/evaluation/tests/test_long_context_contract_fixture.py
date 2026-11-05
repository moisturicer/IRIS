"""IR-736: the long-context contract pack names real, executable proof for every case.

Pure: no database, no vendor. The pack is contract evidence in the shape of
`general_tools_contract_v1.json`; it is never quality or capacity evidence.
"""

import ast
import hashlib
import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "long_context_contract_v1.json"
CONTRACT = Path(__file__).resolve().parents[2] / "tests" / "test_ai_runtime_long_context_contract.py"
CHECKS = {"request_fit", "original_allowance", "atomic_revision", "citations"}


def _pack():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _contract_tests():
    tree = ast.parse(CONTRACT.read_text(encoding="utf-8"))
    return {node.name for node in tree.body if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")}


def test_the_pack_is_labelled_contract_evidence_with_a_matching_snapshot():
    pack = _pack()
    assert pack["schema_version"] == 1 and pack["ticket"] == "IR-736"
    assert pack["status"] == "deterministic_contract_not_quality_evidence"
    assert pack["provider"] == "deterministic_script_only_no_vendor_calls"
    encoded = json.dumps(pack["paper_set"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert pack["snapshot"]["paper_set_sha256"] == hashlib.sha256(encoded).hexdigest()
    assert pack["snapshot"]["source_kind"] == "synthetic"


def test_every_case_is_shaped_like_the_general_tools_pack_and_the_four_checks_are_each_proved():
    cases = _pack()["cases"]
    assert [case["id"] for case in cases] == [f"L0{n}" for n in range(1, 7)]
    for case in cases:
        assert case["family"] and case["turns"] and case["script"] and case["expected"]
        # A check is listed only with the test that asserts it, and that test is one the case names.
        checks = case["expected"]["checks"]
        assert set(checks) <= CHECKS
        assert set(checks.values()) <= set(case["proved_by"])
    # Request fit, the original allowance, atomic revision and citations are each asserted somewhere.
    assert {name for case in cases for name in case["expected"]["checks"]} == CHECKS


def test_every_case_names_contract_tests_that_exist():
    proved = {name for case in _pack()["cases"] for name in case["proved_by"]}
    assert all(case["proved_by"] for case in _pack()["cases"])
    available = _contract_tests()
    assert proved <= available, sorted(proved - available)


def test_the_cited_pages_are_the_papers_middle_and_late_passages():
    pack = _pack()
    [paper] = [p for p in pack["paper_set"] if p["key"] == "monsoon"]
    pages = {f"monsoon:p{fact['page']}": fact["role"] for fact in paper["facts"]}
    expected = next(c for c in pack["cases"] if c["id"] == "L01")["expected"]["late_contradiction_cited"]
    assert set(expected) == set(pages) and sorted(pages.values()) == ["late_contradiction", "middle"]
    assert next(c for c in pack["cases"] if c["id"] == "L02")["expected"]["not_in_context"] == paper["passages"]
