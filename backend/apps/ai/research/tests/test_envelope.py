"""The versioned tool-result envelope (IR-590, general-tools spec §3.3)."""

import json

import pytest

from apps.ai.research.ledger import Ledger
from apps.ai.research.tests.helpers import scalars
from apps.ai.research.results import (
    SCHEMA_VERSION, Completeness, Coverage, CoverageSubject, Envelope, Status,
    SubjectCoverage, ToolResult, ToolStatus, Trace, envelope_of,
)

TRACE = Trace(run_id="r", tool="t")


def _envelope(**overrides):
    fields = {"status": Status.OK,
              "coverage": SubjectCoverage(CoverageSubject.SEARCH_CANDIDATES, returned=1),
              "trace": TRACE, **overrides}
    return Envelope(**fields)


def test_the_public_shape_is_the_seven_fields_and_a_version():
    public = _envelope().public()
    assert set(public) == {"schema_version", "status", "items", "evidence", "facts",
                           "coverage", "continuation", "limitations"}
    assert public["schema_version"] == SCHEMA_VERSION


def test_an_unknown_total_is_null_never_zero():
    coverage = _envelope().public()["coverage"]
    assert "total" in coverage and coverage["total"] is None
    assert coverage["subject"] == "search_candidates"
    assert coverage["complete"] is False


def test_the_private_trace_never_reaches_the_public_payload():
    envelope = _envelope(trace=Trace(run_id="secret-run", tool="t", reason="KeyError"))
    text = json.dumps(envelope.public())
    assert "secret-run" not in text and "KeyError" not in text
    assert envelope.trace.reason == "KeyError"


@pytest.mark.parametrize("key", ["answer", "Answer", "wording", "markdown", "route", "lane",
                                 "ui_hint", "suggestedReply", "record_id", "recordId",
                                 "user_id", "pk"])
def test_answer_wording_route_and_raw_id_keys_are_refused(key):
    with pytest.raises(ValueError, match="forbidden"):
        _envelope(items=({"record": "R1", "nested": {key: "x"}},))
    with pytest.raises(ValueError, match="forbidden"):
        _envelope(facts=({"name": "total", "value": 1, key: "x"},))


@pytest.mark.parametrize("code", ["Free text, not a code", "", "a b"])
def test_limitations_are_machine_codes(code):
    with pytest.raises(ValueError, match="limitation"):
        _envelope(limitations=(code,))


def test_a_denied_result_carries_nothing_about_what_was_withheld():
    with pytest.raises(ValueError, match="denied"):
        _envelope(status=Status.DENIED, items=({"record": "R1"},))
    with pytest.raises(ValueError, match="denied"):
        _envelope(status=Status.DENIED,
                  coverage=SubjectCoverage(CoverageSubject.METADATA_POPULATION, total=3))


def test_complete_must_name_a_scope():
    with pytest.raises(ValueError, match="scope"):
        SubjectCoverage(CoverageSubject.NONE, complete=True)


# -- the adapter from the legacy ToolResult ---------------------------------


def _ledger_with_passage():
    ledger = Ledger(tag="a1b2c3")
    record = ledger.add_record(record_id=40, title="Flood forecasting", abstract="Abstract.")
    passage = ledger.add_passage(
        record_id=40, chunk_id=900, chunk_set_hash="f" * 64, record_title="Flood forecasting",
        text="Rainfall predicts floods.", page=4, context_path=("Flood forecasting", "Results"),
        score=0.8,
    )
    return record, passage


def test_records_become_items_and_passages_become_versioned_evidence():
    record, passage = _ledger_with_passage()
    result = ToolResult(ToolStatus.OK, Coverage(Completeness.SAMPLE, returned=1),
                        (record, passage), annotations={record.handle: {"year": 2021}})
    public = envelope_of(result, CoverageSubject.SEARCH_CANDIDATES, TRACE).public()
    assert public["items"] == [{"record": "R1-a1b2c3", "title": "Flood forecasting", "year": 2021}]
    by_kind = {e["content_kind"]: e for e in public["evidence"]}
    assert by_kind["passage"] == {
        "ref": "E1-a1b2c3", "record": "R1-a1b2c3", "content_kind": "passage",
        "source_version": "f" * 12, "page": 4, "section": "Flood forecasting > Results",
        "text": "Rainfall predicts floods.",
    }
    assert by_kind["abstract"]["source_version"] == record.source_version
    assert not {40, 900} & set(scalars(public))


@pytest.mark.parametrize("legacy, status, limitation", [
    (ToolStatus.OK, Status.OK, None),
    (ToolStatus.EMPTY, Status.EMPTY, None),
    (ToolStatus.DEGRADED, Status.PARTIAL, "degraded"),
    (ToolStatus.FAILED, Status.UNAVAILABLE, "tool_unavailable"),
])
def test_legacy_statuses_map_onto_the_six(legacy, status, limitation):
    envelope = envelope_of(ToolResult(legacy, Coverage(Completeness.SAMPLE), reason="KeyError"),
                           CoverageSubject.SEARCH_CANDIDATES, TRACE)
    assert envelope.status is status
    assert envelope.limitations == ((limitation,) if limitation else ())
    assert "KeyError" not in json.dumps(envelope.public())


@pytest.mark.parametrize("reason, status, limitation", [
    ("unknown_argument", Status.UNAVAILABLE, "invalid_arguments"),
    ("malformed_json", Status.UNAVAILABLE, "invalid_arguments"),
    ("unknown_tool", Status.UNAVAILABLE, "unknown_tool"),
    ("unissued_handle", Status.DENIED, "invalid_reference"),
    ("not_a_record_handle", Status.DENIED, "invalid_reference"),
    ("stale_cursor", Status.UNAVAILABLE, "stale_continuation"),
    ("unissued_cursor", Status.DENIED, "invalid_reference"),
    ("cursor_mismatch", Status.DENIED, "invalid_reference"),
])
def test_a_rejected_call_fails_predictably_with_a_safe_code(reason, status, limitation):
    envelope = envelope_of(ToolResult.rejected(reason), CoverageSubject.SEARCH_CANDIDATES, TRACE)
    assert (envelope.status, envelope.limitations) == (status, (limitation,))
    assert envelope.trace.reason == reason


def test_budget_and_floor_refusals_are_unavailable_without_counts():
    budget = envelope_of(ToolResult(ToolStatus.REFUSED, Coverage(Completeness.SAMPLE),
                                    reason="budget:max_tool_calls"),
                         CoverageSubject.SEARCH_CANDIDATES, TRACE)
    assert (budget.status, budget.limitations) == (Status.UNAVAILABLE, ("budget_exhausted",))
    floor = envelope_of(ToolResult(ToolStatus.REFUSED,
                                   Coverage(Completeness.EXHAUSTIVE, note="below_floor"),
                                   detail={"sample_size": 2, "floor": 5}),
                        CoverageSubject.METADATA_POPULATION, TRACE)
    assert (floor.status, floor.limitations) == (Status.UNAVAILABLE, ("below_floor",))
    assert floor.public()["facts"] == [] and floor.public()["coverage"]["total"] is None


def test_metadata_facts_carry_population_and_predicate_not_wording():
    result = ToolResult(ToolStatus.OK, Coverage(Completeness.EXHAUSTIVE, returned=3),
                        detail={"total": 3, "relative_to": "of the records you can see"},
                        visible_record_ids=frozenset({1, 2, 3}))
    envelope = envelope_of(result, CoverageSubject.METADATA_POPULATION, TRACE,
                           predicate={"year_from": 2020})
    public = envelope.public()
    assert public["coverage"] == {"subject": "metadata_population", "returned": 3,
                                  "total": 3, "complete": True}
    [fact] = public["facts"]
    assert fact["name"] == "total" and fact["value"] == 3
    assert fact["provenance"]["kind"] == "metadata"
    assert fact["provenance"]["population"] == "records_visible_to_reader"
    assert fact["provenance"]["predicate"] == {"year_from": 2020}
    assert len(fact["provenance"]["snapshot"]) == 12
    assert "records you can see" not in json.dumps(public)


def test_a_screened_subset_reports_assessed_uncertain_and_unassessed():
    rows = [{"record": "R1", "decision": "include", "quote": "q"},
            {"record": "R2", "decision": "uncertain", "quote": ""},
            {"record": "R3", "decision": "unassessed", "quote": ""}]
    result = ToolResult(ToolStatus.DEGRADED, Coverage(Completeness.SCREENED, returned=3),
                        detail={"rows": rows, "checked": 1, "unassessed": 2})
    coverage = envelope_of(result, CoverageSubject.SCREENED_SUBSET, TRACE).public()["coverage"]
    assert coverage == {"subject": "screened_subset", "returned": 3, "total": None,
                        "complete": False, "selected": 3, "assessed": 1, "uncertain": 1,
                        "unassessed": 1}


def test_a_requested_selection_is_complete_only_when_nothing_was_cut():
    full = envelope_of(ToolResult(ToolStatus.OK, Coverage(Completeness.EXHAUSTIVE, returned=2)),
                       CoverageSubject.REQUESTED_SELECTION, TRACE)
    assert full.coverage.complete
    cut = envelope_of(ToolResult(ToolStatus.OK,
                                 Coverage(Completeness.SAMPLE, returned=2, truncated=True)),
                      CoverageSubject.REQUESTED_SELECTION, TRACE)
    assert full.status is Status.OK
    assert cut.status is Status.PARTIAL
    assert not cut.coverage.complete and "truncated" in cut.limitations
