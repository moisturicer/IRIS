"""A hit brings its unretrieved neighbours from the same section (IR-1055, ADR-033 §4).

Driven through the run routes as the restricted runtime login, so section
keys come through the migrated `research_chunks()`.
"""

import pytest

from apps.ai.models.chunk import DocumentChunk

from . import test_ir886_hybrid_search_db as hybrid_db
from .corpus import make_user
from .test_ai_runtime_research_db import paper

# Shared fixtures, by name.
api = hybrid_db.api
runtime = hybrid_db.runtime
research = hybrid_db.research
space = hybrid_db.space
run = hybrid_db.run

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]


def sections(record, *keys):
    for chunk, key in zip(DocumentChunk.objects.filter(record=record).order_by("sequence"), keys):
        chunk.section_key = list(key) if key else None
        chunk.save(update_fields=["section_key"])


def test_the_explanation_after_a_hit_arrives_with_it_but_not_the_section_before(research, space):
    reader = make_user("mates-follow@cit.edu")
    study = paper("Tilapia trial", {
        2: [("2 Methods", "ponds were stocked in June")],
        5: [("3.2 Results", "the treatment group reached a yield of 42 percent")],
        6: [("3.2 Results", "because aeration kept oxygen above five milligrams")],
    })
    sections(study, ("T", "2 Methods"), ("T", "3 Results", "3.2"), ("T", "3 Results", "3.2"))

    async def script(tools):
        await tools.hybrid_search("yield", 1)

    ((_, found),) = run(research, reader, script, request="mates-follow-1")
    hit, mate = found.passages
    assert (hit.page, mate.page) == (5, 6)
    assert (hit.section_mate, mate.section_mate) == (False, True)
    assert mate.continues == hit.handle
    assert mate.handle != hit.handle


def test_a_paper_chunked_before_section_keys_gets_no_mates(research, space):
    reader = make_user("mates-unknown@cit.edu")
    paper("Old tilapia trial", {
        5: [("Results", "the treatment group reached a yield of 42 percent")],
        6: [("Results", "because aeration kept oxygen above five milligrams")],
    })

    async def script(tools):
        await tools.hybrid_search("yield", 1)

    ((_, found),) = run(research, reader, script, request="mates-unknown-1")
    assert [p.page for p in found.passages] == [5]
