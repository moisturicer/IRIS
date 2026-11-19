"""A Turn keeps the sources its answer drew on, and a later run reloads them (IR-994, ADR-049).

The store alone on real PostgreSQL under the restricted runtime login; the
executor's side is `test_ai_runtime_followups_contract.py`'s.
"""

import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.research.tools import Source  # noqa: E402
from ai.runs.executor import Citation, Result  # noqa: E402
from ai.runs.store import RunStore  # noqa: E402
from apps.ai.models import ChunkSet  # noqa: E402
from .corpus import make_user
from .test_ai_runtime_compaction_db import follow_up
from .test_ai_runtime_research_db import FLOOD, POND, paper
from .test_ai_runtime_runs_db import ScriptedExecutor, run, service, session

from . import test_ai_runtime_runs_db as runs_db

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

runtime = runs_db.runtime


def source_of(record):
    chunk_set = ChunkSet.objects.get(record=record, is_active=True)
    return Source(record.pk, chunk_set.pk, chunk_set.extraction_hash)


def answered(runtime, grant, key, result):
    svc = service(runtime, ScriptedExecutor(result))
    done, _ = run(svc.submit(grant, key=key, question="Which paper predicts floods?",
                             conversation_id=None, base_revision=None))
    return done


def test_a_turns_sources_are_stored_and_reloaded_for_the_next_run(runtime):
    grant = session(make_user("sources-stored@cit.edu"))
    flood = source_of(paper("Flood forecasting", {4: [("Methods", FLOOD)]}))
    pond = source_of(paper("Pond sampling", {2: [("Methods", POND)]}))
    done = answered(runtime, grant, "sources-stored",
                    Result(answer="One predicted floods.", sources=frozenset({flood, pond})))

    _, later = follow_up(runtime, grant, "sources-stored-next", uuid.UUID(done["conversation_id"]), 1)
    (prior,) = later.prior
    assert prior.sources == {flood, pond}


def test_an_older_turn_is_labelled_by_its_citations_and_the_sources_its_run_read(runtime):
    grant = session(make_user("sources-legacy@cit.edu"))
    flood = source_of(paper("Flood forecasting", {4: [("Methods", FLOOD)]}))
    pond = source_of(paper("Pond sampling", {2: [("Methods", POND)]}))
    cited = Citation(flood.record_id, FLOOD, 4, flood.revision)
    done = answered(runtime, grant, "sources-legacy", Result(answer="One predicted floods.", citations=(cited,)))

    async def journal_a_read():
        async with RunStore(runtime)._connect() as conn:
            await RunStore._journal(conn, uuid.UUID(done["id"]), "tool",
                                    {"tool": "search", "sources": [pond.revision]})

    run(journal_a_read())
    _, later = follow_up(runtime, grant, "sources-legacy-next", uuid.UUID(done["conversation_id"]), 1)
    (prior,) = later.prior
    assert prior.sources == {flood, pond}


def test_a_turns_cited_papers_and_pages_are_reloaded_in_citation_order(runtime):
    # IR-1168: research-10 lists them under the earlier answer.
    grant = session(make_user("sources-cited@cit.edu"))
    flood = source_of(paper("Flood forecasting", {4: [("Methods", FLOOD)]}))
    pond = source_of(paper("Pond sampling", {2: [("Methods", POND)]}))
    citations = (Citation(pond.record_id, POND, 2, pond.revision),
                 Citation(flood.record_id, FLOOD, 4, flood.revision))
    done = answered(runtime, grant, "sources-cited", Result(answer="Both [1] [2].", citations=citations))

    _, later = follow_up(runtime, grant, "sources-cited-next", uuid.UUID(done["conversation_id"]), 1)
    (prior,) = later.prior
    assert prior.cited == ((pond.record_id, 2), (flood.record_id, 4))


def test_a_turn_with_no_citations_reloads_none(runtime):
    grant = session(make_user("sources-uncited@cit.edu"))
    done = answered(runtime, grant, "sources-uncited", Result(answer="General background."))
    _, later = follow_up(runtime, grant, "sources-uncited-next", uuid.UUID(done["conversation_id"]), 1)
    (prior,) = later.prior
    assert prior.cited == ()
