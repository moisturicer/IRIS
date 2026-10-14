"""Safety invariants of the application-owned lane workflows, without a vendor."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apps.ai.answers.citations import Citation, NO_SOURCES, UNAVAILABLE
from apps.ai.research.ledger import EvidenceItem, RECORD
from apps.ai.research.results import Completeness, Coverage, ToolResult, ToolStatus
from apps.ai.retrieval.ports import RetrievedChunk, RetrievalResult
from apps.ai.routing import lanes

pytestmark = pytest.mark.django_required


def item(pk, title):
    return EvidenceItem(f"R{pk}", RECORD, pk, title, "abstract")


def run_for(records):
    root = Mock()
    root.source_selection.return_value.apply.side_effect = lambda passages: list(passages)
    return SimpleNamespace(ctx=SimpleNamespace(permits=lambda record: True, user=object()), root=root), {
        record.pk: record for record in records
    }


def record(pk):
    return SimpleNamespace(pk=pk, title=f"Paper {pk}", abstract="abstract")


# IR-546 replaced the listing lane's find-then-screen tool calls with
# `research.listing.screen_listing`, so the two tests that mocked those calls
# are replaced here by the same two invariants at the new seam. The end-to-end
# behaviour is in `test_listing_workflow_http.py`.
def listing_outcome(*candidates):
    from apps.ai.research.listing import Candidate, Outcome

    return Outcome(tuple(Candidate(pk, f"Paper {pk}", state) for pk, state in candidates))


def run_listing(monkeypatch, outcome):
    run = SimpleNamespace(root=Mock())

    def screened(run, question):
        return outcome
        yield  # a generator, as the real one is

    monkeypatch.setattr(lanes, "screen_listing", screened)
    events = lanes._listing_events(run, "aquaponics")
    try:
        while True:
            next(events)
    except StopIteration as stop:
        return stop.value, run


def test_listing_answer_is_the_code_written_wording_and_lists_only_included(monkeypatch):
    (answer, listing), run = run_listing(
        monkeypatch, listing_outcome((1, "included"), (2, "excluded"), (3, "uncertain")))
    assert listing["records"] == [{"record_id": 1, "title": "Paper 1"}]
    assert answer.text == listing["wording"] and answer.state != NO_SOURCES
    assert "1 matched, 1 did not match, 1 uncertain, 0 could not be assessed" in answer.text
    run.root.llm_for.assert_not_called()


def test_listing_unassessed_is_not_claimed_as_a_match(monkeypatch):
    (answer, listing), run = run_listing(monkeypatch, listing_outcome((1, "unassessed")))
    assert answer.state == NO_SOURCES
    assert listing["records"] == [] and listing["completeness"] == "inconclusive"
    assert answer.text.startswith("Inconclusive: none of the 1 candidate papers could be assessed")
    run.root.llm_for.assert_not_called()


def passage(pk, n):
    return RetrievedChunk(n, pk, f"Paper {pk}", "evidence", (), 1, .9)


def setup_comparison(monkeypatch, *, missing=()):
    records = [record(1), record(2)]
    run, allowed = run_for(records)
    monkeypatch.setattr(lanes, "_named_records", lambda ctx, q: (records, list(missing)))
    monkeypatch.setattr(lanes, "disclosable", lambda ctx, ids: {pk: allowed[pk] for pk in ids if pk in allowed})
    run.root.retriever.return_value.retrieve.side_effect = [
        RetrievalResult((passage(1, 11), passage(1, 12))),
        RetrievalResult((passage(2, 21),)),
    ]
    return run


def cite(pk, chunk, marker):
    return Citation(marker, chunk, pk, f"Paper {pk}", 1, "evidence", ())


def test_comparison_reserves_one_passage_and_requires_citation_from_each_paper(monkeypatch):
    run = setup_comparison(monkeypatch)
    generated = Mock(return_value=("Compared [1].", (cite(1, 11, 1),)))
    monkeypatch.setattr(lanes, "generate_cited", generated)
    answer, listing = lanes._comparison(run, "Compare papers", 2)
    assert [p.record_id for p in generated.call_args.args[2]] == [1, 2]
    assert answer.state == UNAVAILABLE
    assert [p.record_id for p in answer.sources] == [1, 2]
    assert listing is None
    assert [call.kwargs["records"] for call in run.root.retriever.call_args_list] == [frozenset({1}), frozenset({2})]


def test_comparison_reports_named_paper_with_no_evidence(monkeypatch):
    run = setup_comparison(monkeypatch, missing=("Unknown title",))
    run.root.retriever.return_value.retrieve.side_effect = [RetrievalResult((passage(1, 11),)), RetrievalResult()]
    monkeypatch.setattr(lanes, "generate_cited", lambda *args, **kwargs: ("Finding [1].", (cite(1, 11, 1),)))
    answer, _ = lanes._comparison(run, "Compare", 2)
    assert "Unknown title" in answer.text
    assert "Paper 2" in answer.text
    assert answer.degraded


def test_comparison_does_not_retrieve_or_transmit_gated_paper(monkeypatch):
    run = setup_comparison(monkeypatch)
    run.ctx.permits = lambda record: record.pk == 1
    run.root.retriever.return_value.retrieve.side_effect = [RetrievalResult((passage(1, 11),))]
    generated = Mock(return_value=("Finding [1].", (cite(1, 11, 1),)))
    monkeypatch.setattr(lanes, "generate_cited", generated)
    answer, _ = lanes._comparison(run, "Compare", 2)
    assert [p.record_id for p in generated.call_args.args[2]] == [1]
    assert run.root.retriever.call_count == 1
    assert "Paper 2" in answer.text


def test_count_uses_computed_workflow_wording_without_answer_model(monkeypatch):
    run, allowed = run_for([record(1)])
    monkeypatch.setattr(lanes, "disclosable", lambda ctx, ids: allowed)
    monkeypatch.setattr(lanes, "topic_count", lambda run, q: ToolResult(
        ToolStatus.OK, Coverage(Completeness.SCREENED), (item(1, "Paper 1"),),
        detail={"total": 1, "wording": "1 matched out of 2 checked; 0 could not be assessed.",
                "matches": [{"record": "R1"}]}))
    answer, listing = lanes._count(run, "aquaponics")
    assert answer.text.startswith("1 matched out of 2 checked")
    assert listing["records"] == [{"record_id": 1, "title": "Paper 1"}]
    run.root.llm_for.assert_not_called()


def test_comparison_over_source_limit_does_not_silently_drop_a_paper(monkeypatch):
    run = setup_comparison(monkeypatch)
    answer, _ = lanes._comparison(run, "Compare", 1)
    assert answer.state == NO_SOURCES
    assert "source limit" in answer.text
    run.root.retriever.assert_not_called()


def test_comparison_relevance_cutoff_reports_paper_without_usable_passage(monkeypatch, settings):
    settings.AI_RELEVANCE_MIN_SCORE = .95
    run = setup_comparison(monkeypatch)
    generated = Mock()
    monkeypatch.setattr(lanes, "generate_cited", generated)
    answer, _ = lanes._comparison(run, "Compare", 2)
    assert answer.state == NO_SOURCES
    assert "Paper 1" in answer.text and "Paper 2" in answer.text
    generated.assert_not_called()


def test_title_resolution_uses_only_visible_full_titles_and_reports_unknown_quotes(monkeypatch):
    queryset = Mock()
    queryset.only.return_value = [record(1), record(2)]
    monkeypatch.setattr(lanes, "readable_records", lambda ctx: queryset)
    matches, missing = lanes._named_records(object(), 'Compare Paper 1 with "Unknown title"')
    assert [r.pk for r in matches] == [1]
    assert missing == ["Unknown title"]
    matches, _ = lanes._named_records(object(), "Compare Paper 10 and paper 20")
    assert matches == []
