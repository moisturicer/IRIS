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
