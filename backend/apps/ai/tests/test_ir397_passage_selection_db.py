"""The agent's search selects passages, not a slice of the ranking (IR-397, ADR-033 §4).

Driven through the run routes as the restricted runtime login, so the
migrated `research_chunks()` columns and the reader's grant are both real.
"""

import pytest

from apps.ai.models.chunk import DocumentChunk

from .corpus import make_user
from . import test_ir886_hybrid_search_db as hybrid_db
from .test_ai_runtime_research_db import paper

# Shared fixtures, by name.
api = hybrid_db.api
runtime = hybrid_db.runtime
research = hybrid_db.research
space = hybrid_db.space
run = hybrid_db.run

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]


def flooding(n):
    return ("Results", f"flooding observation number {n} in the lower catchment")


def test_a_paper_that_outranks_the_rest_still_leaves_room_for_another(research, space, monkeypatch):
    # The share is off by default (IR-1150); this checks it when switched on.
    from ai.research import selection, tools
    monkeypatch.setattr(tools, "Policy", lambda: selection.Policy(paper_share=50))
    reader = make_user("select-cap@cit.edu")
    verbose = paper("Verbose flood study", {p: [flooding(p)] for p in range(1, 7)})
    other = paper("Short flood note", {1: [("Results", "flooding seen once")]})
    # Full-size chunks: five requested is a 3,500-token budget, 1,750 per paper.
    DocumentChunk.objects.filter(record__in=[verbose, other]).update(token_count=700)

    async def script(tools):
        await tools.hybrid_search("flooding", 5)
        await tools.search("flooding", 5)

    (_, hybrid), (_, keyword) = run(research, reader, script, request="select-cap-1")
    for found in (hybrid, keyword):
        per_paper = [p.record_id for p in found.passages]
        assert other.pk in per_paper
        assert per_paper.count(verbose.pk) == 4


def test_paper_chat_is_not_capped(research, space):
    reader = make_user("select-scope@cit.edu")
    verbose = paper("Verbose flood study", {p: [flooding(p)] for p in range(1, 7)})

    async def script(tools):
        await tools.hybrid_search("flooding", 5)

    ((_, found),) = run(research, reader, script, request="select-scope-1", record_id=verbose.pk)
    assert [p.record_id for p in found.passages] == [verbose.pk] * 5


def test_adjacent_hits_arrive_together_each_with_its_own_handle_and_page(research, space):
    reader = make_user("select-join@cit.edu")
    study = paper("Flood study", {
        3: [("Results", "flooding peaked in March")],
        4: [("Results", "flooding receded by May")],
        9: [("Appendix", "station list without the term")],
    })

    async def script(tools):
        await tools.hybrid_search("flooding", 5)

    ((_, found),) = run(research, reader, script, request="select-join-1")
    first, second = found.passages
    assert (first.page, second.page) == (3, 4)
    assert first.handle != second.handle
    assert (first.continues, second.continues) == (None, first.handle)
    assert {p.record_id for p in found.passages} == {study.pk}


def test_the_budget_counts_stored_chunker_tokens(research, space):
    reader = make_user("select-budget@cit.edu")
    study = paper("Flood study", {1: [flooding(1)], 5: [flooding(5)], 9: [flooding(9)]})
    # Stored counts, not words: two of these fill a two-passage budget of 1,400.
    DocumentChunk.objects.filter(record=study).update(token_count=700)

    async def script(tools):
        await tools.hybrid_search("flooding", 2)

    ((_, found),) = run(research, reader, script, request="select-budget-1")
    assert len(found.passages) == 2
    DocumentChunk.objects.filter(record=study).update(token_count=800)

    ((_, again),) = run(research, reader, script, request="select-budget-2")
    assert len(again.passages) == 1
