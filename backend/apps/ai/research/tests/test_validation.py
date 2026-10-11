import pytest

from apps.ai.research.ledger import Ledger
from apps.ai.research.results import ToolResult, ToolStatus, Coverage, Completeness
from apps.ai.research.validation import validate_answer
from apps.ai.retrieval.ports import RetrievedChunk


def check(text, *, computed=None, label=Completeness.SAMPLE):
    ledger = Ledger()
    ledger.add_record(record_id=1, title="Flood forecasting", abstract="")
    sources = [RetrievedChunk(1, 1, "Flood forecasting", "Accuracy was 92.5 percent in 2021. Two gauges were used.", (), 1, 1)]
    results = [ToolResult(ToolStatus.OK, Coverage(label), detail=computed or {})]
    return validate_answer(text, sources=sources, ledger=ledger, results=results)


@pytest.mark.parametrize("text, code", [
    ("Accuracy was 92.5 percent [99].", "unknown_citation"),
    ("Accuracy was 98 percent [1].", "unsupported_number"),
    ("The paper «Invented flood study» agrees [1].", "unknown_title"),
    ('The paper "Invented flood study" agrees [1].', "unknown_title"),
    ("The paper Imaginary Study supports this [1].", "unknown_title"),
    ("All papers agree [1].", "completeness_overclaim"),
    ("There are 2 studies [1].", "completeness_overclaim"),
    ("Two gauges were used [E9].", "unknown_citation"),
])
def test_invented_answer_content_is_flagged(text, code):
    assert code in check(text)


def test_supported_numbers_titles_and_citations_pass():
    assert check("«Flood forecasting» used two gauges and achieved 92.5 percent accuracy in 2021 [1].") == ()


def test_an_uncited_number_is_not_supported_by_an_uncited_passage():
    assert "unsupported_number" in check("Accuracy was 92.5 percent.")


def test_computed_count_is_usable_but_does_not_make_a_sample_exhaustive():
    assert check("A count of 7 was computed [1].", computed={"total": 7}) == ()
    assert "completeness_overclaim" in check("There are 7 studies [1].", computed={"total": 7})


def test_an_exact_count_can_be_described_as_exact():
    assert check("There are 7 records you can see.", computed={"total": 7}, label=Completeness.EXHAUSTIVE) == ()
