"""Per-run evidence handles (IR-500, ADR-038 §2.5)."""

import pytest

from apps.ai.research.ledger import HandleRejected, Ledger


def _passage(ledger, chunk_id, record_id=1, score=0.5):
    return ledger.add_passage(
        record_id=record_id, chunk_id=chunk_id, chunk_set_hash="h",
        record_title="T", text=f"text {chunk_id}", page=2,
        context_path=("T", "Methods"), score=score,
    )


def _record(ledger, record_id):
    return ledger.add_record(record_id=record_id, title=f"R{record_id}", abstract="a")


def test_handles_are_issued_in_order_per_kind():
    ledger = Ledger()
    assert _record(ledger, 40).handle == "R1"
    assert _passage(ledger, 900, record_id=40).handle == "E1"
    assert _record(ledger, 41).handle == "R2"
    assert _passage(ledger, 901, record_id=41).handle == "E2"


def test_the_same_source_keeps_its_handle():
    ledger = Ledger()
    first = _passage(ledger, 900)
    again = _passage(ledger, 900)
    assert again.handle == first.handle
    assert len(ledger.passages()) == 1
    assert _record(ledger, 7).handle == _record(ledger, 7).handle


def test_the_stored_pointer_is_record_chunk_and_chunk_set():
    item = _passage(Ledger(), 900, record_id=40)
    assert item.pointer == (40, 900, "h")


def test_an_issued_record_handle_resolves():
    ledger = Ledger()
    _record(ledger, 40)
    assert ledger.record_id("R1") == 40


@pytest.mark.parametrize("value", ["R2", "R0", "E1", "40", 40, "r1", " R1", None, "R1x"])
def test_anything_but_an_issued_record_handle_is_rejected(value):
    ledger = Ledger()
    _record(ledger, 40)
    _passage(ledger, 900, record_id=40)
    with pytest.raises(HandleRejected):
        ledger.record_id(value)


def test_the_weakest_passage_is_dropped_past_the_cap():
    ledger = Ledger(max_passages=2)
    _passage(ledger, 1, score=0.9)
    _passage(ledger, 2, score=0.1)
    _passage(ledger, 3, score=0.5)
    assert [p.chunk_id for p in ledger.passages()] == [1, 3]


def test_records_are_never_dropped():
    ledger = Ledger(max_passages=1)
    for record_id in range(5):
        _record(ledger, record_id)
    assert len(ledger.records()) == 5


def test_a_dropped_passage_keeps_its_handle_if_collected_again():
    ledger = Ledger(max_passages=1)
    first = _passage(ledger, 1, score=0.1)
    _passage(ledger, 2, score=0.9)
    assert _passage(ledger, 1, score=0.1).handle == first.handle


def test_holds_is_false_for_a_passage_dropped_on_arrival():
    ledger = Ledger(max_passages=1)
    kept = _passage(ledger, 1, score=0.9)
    dropped = _passage(ledger, 2, score=0.1)
    assert ledger.holds(kept) and not ledger.holds(dropped)
    assert ledger.holds(_record(ledger, 7))


def test_a_negative_passage_cap_is_rejected_before_collection():
    with pytest.raises(ValueError, match="max_passages"):
        Ledger(max_passages=-1)


# -- IR-590: run-scoped handles and bound cursors ----------------------------


def test_a_tagged_ledger_issues_handles_only_it_accepts():
    ledger = Ledger(tag="a1b2c3")
    record = _record(ledger, 40)
    assert record.handle == "R1-a1b2c3"
    assert _passage(ledger, 900, record_id=40).handle == "E1-a1b2c3"
    assert ledger.record_id("R1-a1b2c3") == 40


@pytest.mark.parametrize("value", ["R1", "R1-ffffff", "R1-a1b2c3 ", "R1-A1B2C3"])
def test_another_runs_handle_is_rejected_like_an_unissued_one(value):
    ledger = Ledger(tag="a1b2c3")
    _record(ledger, 40)
    with pytest.raises(HandleRejected) as rejected:
        ledger.record_id(value)
    assert str(rejected.value) in {"unissued_handle", "not_a_record_handle"}


def test_a_tag_must_be_short_lowercase_hex():
    with pytest.raises(ValueError, match="tag"):
        Ledger(tag="R1")


def _cursor(**overrides):
    return {"tool": "read", "query": "q1", "caller": "7", "source_version": "v1", **overrides}


def test_a_cursor_resumes_only_for_its_tool_query_caller_and_version():
    ledger = Ledger(tag="a1b2c3")
    token = ledger.issue_cursor(position=12, **_cursor())
    assert token == "C1-a1b2c3"
    assert ledger.resume(token, **_cursor()) == 12
    for field, value in (("tool", "search"), ("query", "q2"), ("caller", "8")):
        with pytest.raises(HandleRejected, match="cursor_mismatch"):
            ledger.resume(token, **_cursor(**{field: value}))
    with pytest.raises(HandleRejected, match="stale_cursor"):
        ledger.resume(token, **_cursor(source_version="v2"))


@pytest.mark.parametrize("token", ["C9-a1b2c3", "C1", "C1-ffffff", "R1-a1b2c3", None, 3])
def test_an_unissued_cursor_is_rejected(token):
    ledger = Ledger(tag="a1b2c3")
    ledger.issue_cursor(position=1, **_cursor())
    with pytest.raises(HandleRejected, match="unissued_cursor"):
        ledger.resume(token, **_cursor())


def test_cursors_are_bounded_per_run():
    ledger = Ledger(tag="a1b2c3", max_cursors=2)
    assert ledger.issue_cursor(position=1, **_cursor())
    assert ledger.issue_cursor(position=2, **_cursor())
    assert ledger.issue_cursor(position=3, **_cursor()) is None


def test_a_passage_collected_on_a_new_version_replaces_the_old_item():
    ledger = Ledger()
    first = _passage(ledger, 900)
    newer = ledger.add_passage(
        record_id=1, chunk_id=900, chunk_set_hash="h2", record_title="T",
        text="text 900", page=2, context_path=("T",), score=0.5,
    )
    assert newer.handle == first.handle and newer.source_version == "h2"
    assert ledger.passages() == (newer,)


def test_a_record_carries_a_source_version_of_its_metadata():
    ledger = Ledger()
    first = ledger.add_record(record_id=1, title="T", abstract="a")
    version = first.source_version
    assert len(version) == 12
    assert ledger.add_record(record_id=1, title="T", abstract="b").source_version != version
    assert _passage(ledger, 900).source_version == "h"
