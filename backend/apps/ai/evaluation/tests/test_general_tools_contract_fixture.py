"""IR-589: validate the approved conversation contract, not the future runtime."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "general_tools_contract_v1.json"
MANIFEST = ROOT / "docs" / "evaluation" / "general-tools" / "manifest.example.json"
IDS = {f"A{number:02}" for number in range(1, 16)}


def _pack():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_all_fifteen_scenarios_have_separate_expected_and_current_results():
    pack = _pack()
    assert pack["schema_version"] == 1
    assert pack["status"] == "approved_contract_not_runtime_baseline"
    assert pack["provider"] == "deterministic_script_only_no_vendor_calls"
    cases = pack["cases"]
    assert len(cases) == len(IDS)
    assert {case["id"] for case in cases} == IDS
    for case in cases:
        assert case["family"] and case["turns"] and case["script"]
        assert case["expected"]
        observation = case["current_observation"]
        assert observation["kind"] in {"not_measured", "source_observed_failure"}
        if observation["kind"] == "source_observed_failure":
            source = ROOT / observation["source"]
            assert observation["text"] in source.read_text(encoding="utf-8")


def test_paper_references_and_displayed_ordinals_are_consistent():
    pack = _pack()
    papers = pack["paper_set"]
    encoded = json.dumps(papers, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert pack["snapshot"]["paper_set_sha256"] == hashlib.sha256(encoded).hexdigest()
    assert json.loads(MANIFEST.read_text(encoding="utf-8"))["corpus"]["paper_set_sha256"] == (
        pack["snapshot"]["paper_set_sha256"]
    )
    assert json.loads(MANIFEST.read_text(encoding="utf-8"))["fixture_sha256"] == (
        hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    )
    keys = {paper["key"] for paper in papers}
    assert len(keys) == len(papers)
    assert len({paper["title"] for paper in papers}) == len(papers)
    cases = {case["id"]: case for case in pack["cases"]}
    for case in cases.values():
        expected = case["expected"]
        for field in ("presented_order", "selected", "excluded", "exact_selected", "never_expose"):
            assert set(expected.get(field, [])) <= keys
    ordered = cases["A02"]["expected"]["presented_order"]
    assert cases["A02"]["expected"]["selected"] == [ordered[0], ordered[2]]
    assert all(paper["readable"] for paper in papers if paper["key"] in ordered)
    assert cases["A01"]["expected"]["topic"] == "MeshKV"


def test_known_regressions_have_specific_independent_oracles():
    cases = {case["id"]: case for case in _pack()["cases"]}
    assert cases["A01"]["expected"]["citations_retained_on_simplify"]
    assert cases["A09"]["expected"]["distinct_states"] == [
        "not_reported", "no_match_found", "unavailable"
    ]
    assert cases["A09"]["expected"]["retain_supported_after_tool_failure"]
    assert cases["A09"]["expected"]["disclose_material_limit"]
    assert cases["A10"]["expected"]["allow_literal_fragments"] == [
        "1.", "2.", "x = 2", "3 approaches"
    ]
    assert cases["A10"]["expected"]["reject_unsupported_factual_number"] == "37%"
    assert cases["A10"]["expected"]["max_repair_attempts"] == 1
    assert cases["A11"]["expected"]["direct_general_explanation_allowed"]
    assert cases["A11"]["expected"]["general_explanation_not_attributed_to_paper"]
    assert not cases["A11"]["expected"]["paper_specific_claim_without_current_evidence"]
    assert cases["A12"]["expected"]["new_paid_calls_after_cancel"] == 0
    assert cases["A13"]["expected"]["public_fields"] == [
        "activity", "reasoning_summary", "answer"
    ]
    assert cases["A13"]["expected"]["default_reader_controller_without_toggle"]
    assert cases["A13"]["expected"]["prompt_warning"] == (
        "Ask IRIS can make mistakes. Check important details against the cited papers."
    )
    assert cases["A13"]["expected"]["warning_visible_before_submit"]
    assert cases["A14"]["expected"]["reasoning_only_state"] == "unavailable"
    assert cases["A15"]["expected"]["confidential_public_query"] is False
