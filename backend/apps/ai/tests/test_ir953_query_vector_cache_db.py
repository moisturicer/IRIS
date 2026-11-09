"""A query's embedding is reused within one run, and only there (IR-953, ADR-049).

Driven through the run routes as the restricted runtime login, with the same
recording embedder as IR-886's tests: a deterministic contract, never latency.
"""

import json
from dataclasses import replace

import pytest

from apps.ai.models.admission import ProviderReservation
from apps.ai.grants import issue
from ai.admission.ledger import Ledger
from ai.runs.service import RunService

from . import test_ai_runtime_runs_db as runs_db
from . import test_ai_runtime_research_db as research_db
from .corpus import make_user
from .test_ai_runtime_admission_db import limits
from .test_ai_runtime_research_db import ScriptedResearch, paper
from . import test_ir886_hybrid_search_db as hybrid
from .test_ir886_hybrid_search_db import PRICES, QueryEmbedder, axis, embed

api = runs_db.api
runtime = runs_db.runtime
research = research_db.research
space = hybrid.space

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]


def run(api, reader, script, *, request, embedder, cache):
    client, holder = api
    executor = ScriptedResearch(script)
    base = runs_db.service(holder["dsn"], executor)
    built = RunService(
        base.store, replace(base.cfg, query_vector_cache=cache), base.executor, base.notifier,
        embedding_provider=embedder,
        embedding_ledger=Ledger(holder["dsn"], limits(
            AI_ADMISSION_LANE_CONCURRENCY=json.dumps({"research": 4}), AI_ADMISSION_PRICES=PRICES)),
    )
    built.notifier.service = built
    holder["service"] = built
    response = runs_db.submit(client, issue.reader_session_grant(reader).token, request)
    assert response.status_code == 201, response.json()
    return executor.seen


def embeds():
    return ProviderReservation.objects.filter(owner="ai", operation="embed").count()


def corpus(space):
    found = paper("Catchment hydrology", {7: [("Results", "the river burst its banks after heavy rain")]})
    embed(space, found, record_axis=0, chunk_axes=[0])
    return found


def test_the_same_query_twice_in_one_run_is_embedded_and_paid_for_once(research, space):
    reader = make_user("vector-cache-on@cit.edu")
    found = corpus(space)
    embedder = QueryEmbedder({"inundation": axis(0)})

    async def script(tools):
        await tools.hybrid_search("inundation", 5)
        await tools.hybrid_search("inundation", 5)

    first, second = (r for _, r in run(research, reader, script, request="vector-cache-on-1",
                                       embedder=embedder, cache=True))
    assert embedder.calls == [(["inundation"], "query")]
    assert embeds() == 1
    # The reused vector finds exactly what the first search found.
    assert [(p.record_id, p.page) for p in first.passages] == [(p.record_id, p.page) for p in second.passages]
    assert (found.pk, 7) in [(p.record_id, p.page) for p in second.passages]


def test_turned_off_every_search_embeds_again(research, space):
    reader = make_user("vector-cache-off@cit.edu")
    corpus(space)
    embedder = QueryEmbedder({"inundation": axis(0)})

    async def script(tools):
        await tools.hybrid_search("inundation", 5)
        await tools.hybrid_search("inundation", 5)

    run(research, reader, script, request="vector-cache-off-1", embedder=embedder, cache=False)
    assert len(embedder.calls) == 2
    assert embeds() == 2


def test_the_cache_never_crosses_runs(research, space):
    reader = make_user("vector-cache-runs@cit.edu")
    corpus(space)
    embedder = QueryEmbedder({"inundation": axis(0)})

    async def script(tools):
        await tools.hybrid_search("inundation", 5)

    run(research, reader, script, request="vector-cache-runs-1", embedder=embedder, cache=True)
    run(research, reader, script, request="vector-cache-runs-2", embedder=embedder, cache=True)
    assert len(embedder.calls) == 2, "each run pays for its own query vector"
