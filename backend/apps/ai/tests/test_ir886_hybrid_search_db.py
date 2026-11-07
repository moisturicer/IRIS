"""The agent's search finds permitted Passages by meaning and metadata (IR-886, ADR-049).

Driven through the run routes with a scripted executor, as the restricted
`iris_ai_runtime` login under Django-issued reader grants. Query vectors come
from a recording provider: a deterministic contract, never answer quality.
"""

import asyncio
import json
from dataclasses import dataclass

import pytest

from apps.ai.models import EmbeddingSpace
from apps.ai.models.admission import ProviderReservation
from apps.ai.models.chunk import ChunkEmbedding, DocumentChunk
from apps.ai.models.embedding import RecordSpaceEmbedding
from apps.records.models import Record
from core.enums import PipelineStatus

from . import test_ai_runtime_runs_db as runs_db
from .corpus import make_user
from .test_ai_runtime_admission_db import limits
from . import test_ai_runtime_research_db as research_db
from .test_ai_runtime_research_db import ScriptedResearch, paper
from apps.ai.grants import issue

# Shared fixtures, by name.
api = runs_db.api
runtime = runs_db.runtime
research = research_db.research

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

MODEL = "voyage-context-4"
PRICES = json.dumps({MODEL: {"input": 1, "output": 0}, "rerank-2.5": {"input": 1, "output": 0}})


def axis(n):
    """A unit vector on axis `n`: cosine 1 to itself, 0 to every other axis."""
    vector = [0.0] * 1024
    vector[n] = 1.0
    return vector


@dataclass
class Embedded:
    vectors: list
    input_tokens: int = 3


class QueryEmbedder:
    model, dimensions, data_policy, account = MODEL, 1024, "no-training", "recording"

    def __init__(self, vectors):
        self.vectors = vectors
        self.calls = []

    async def embed(self, texts, *, input_type):
        self.calls.append((list(texts), input_type))
        return Embedded([self.vectors[t] for t in texts])


@pytest.fixture
def space(research):
    EmbeddingSpace.objects.filter(state="active").update(state="retired")
    return EmbeddingSpace.objects.create(model_id=MODEL, dimensions=1024, metric="cosine", state="active")


def embed(space, record, *, record_axis, chunk_axes):
    """Vectors for one paper: its Record vector and one per Passage, in sequence order."""
    RecordSpaceEmbedding.objects.create(record=record, space=space, embedding=axis(record_axis))
    chunks = DocumentChunk.objects.filter(record=record, chunk_set__is_active=True).order_by("sequence")
    for chunk, n in zip(chunks, chunk_axes):
        ChunkEmbedding.objects.create(chunk=chunk, space=space, embedding=axis(n))


def run(api, reader, script, *, key, embedder=None, record_id=None, **service_kw):
    from ai.admission.ledger import Ledger
    from ai.runs.service import RunService

    client, holder = api
    executor = ScriptedResearch(script)
    base = runs_db.service(holder["dsn"], executor)
    built = RunService(
        base.store, base.cfg, base.executor, base.notifier,
        embedding_provider=embedder,
        embedding_ledger=Ledger(holder["dsn"], limits(
            AI_ADMISSION_LANE_CONCURRENCY=json.dumps({"research": 4}),
            AI_ADMISSION_PRICES=PRICES)) if embedder is not None else None,
        **service_kw,
    )
    built.notifier.service = built
    holder["service"] = built
    grant = issue.reader_session_grant(reader, record_id).token
    response = runs_db.submit(client, grant, key)
    assert response.status_code == 201, response.json()
    return executor.seen


def test_a_meaning_only_match_is_found_even_when_its_paper_is_outside_the_paper_first_candidates(research, space):
    reader = make_user("hybrid-meaning@cit.edu")
    answer = paper("Catchment hydrology", {7: [("Results", "the river burst its banks after heavy rain")]})
    embed(space, answer, record_axis=900, chunk_axes=[0])
    # Twenty-one papers whose abstracts resemble the question better fill every paper-first slot.
    for n in range(21):
        decoy = paper(f"Decoy {n}", {1: [("Body", f"unrelated decoy text {n}")]})
        embed(space, decoy, record_axis=0, chunk_axes=[100 + n])
    embedder = QueryEmbedder({"inundation": axis(0)})

    async def script(tools):
        await tools.hybrid_search("inundation", 5)

    ((_, found),) = run(research, reader, script, key="hybrid-meaning-1", embedder=embedder)
    assert found.status == "ok"
    hits = [(p.record_id, p.page) for p in found.passages]
    assert (answer.pk, 7) in hits
    assert dict(found.signals)["semantic"] == "ok"
    assert embedder.calls == [(["inundation"], "query")]


def test_without_a_provider_search_answers_by_keyword_and_says_meaning_search_is_unavailable(research, space):
    reader = make_user("hybrid-gated@cit.edu")
    flood = paper("Flood forecasting", {4: [("Methods", "rainfall gauges predict flooding")]})
    embed(space, flood, record_axis=0, chunk_axes=[0])

    async def script(tools):
        await tools.hybrid_search("flooding")
        await tools.hybrid_search("inundation")

    (_, term), (_, meaning) = run(research, reader, script, key="hybrid-gated-1")
    assert term.status == "ok" and [p.record_id for p in term.passages] == [flood.pk]
    assert dict(term.signals) == {"keyword": "ok", "semantic": "provider_gated", "rerank": "off"}
    # Nothing found by keyword is a no-match by keyword only: the gap is stated, not hidden.
    assert meaning.status == "no_match"
    assert dict(meaning.signals)["semantic"] == "provider_gated"


def test_a_term_only_match_is_found_with_meaning_search_on(research, space):
    reader = make_user("hybrid-term@cit.edu")
    flood = paper("Flood forecasting", {4: [("Methods", "tilapia ponds stocked weekly")]})
    embed(space, flood, record_axis=1, chunk_axes=[1])
    embedder = QueryEmbedder({"tilapia": axis(2)})

    async def script(tools):
        await tools.hybrid_search("tilapia")

    ((_, found),) = run(research, reader, script, key="hybrid-term-1", embedder=embedder)
    assert [p.record_id for p in found.passages][0] == flood.pk
    assert dict(found.signals)["semantic"] == "ok"


def test_metadata_filters_narrow_every_signal_and_an_unknown_value_is_explicit(research, space):
    reader = make_user("hybrid-filter@cit.edu")
    old = paper("Flood study 2019", {1: [("Body", "flooding in the old catchment")]})
    new = paper("Flood study 2023", {1: [("Body", "flooding in the new catchment")]})
    Record.objects.filter(pk=old.pk).update(year_completed=2019)
    Record.objects.filter(pk=new.pk).update(year_completed=2023)
    embed(space, old, record_axis=0, chunk_axes=[0])
    embed(space, new, record_axis=0, chunk_axes=[0])
    embedder = QueryEmbedder({"flooding": axis(0)})

    async def script(tools):
        await tools.hybrid_search("flooding", 10, {"year_from": 2020})
        await tools.hybrid_search("flooding", 10, {"classification": "No such area"})
        await tools.hybrid_search("flooding", 10, {"colour": "red"})

    (_, narrowed), (_, unknown), (_, invalid) = run(
        research, reader, script, key="hybrid-filter-1", embedder=embedder)
    assert {p.record_id for p in narrowed.passages} == {new.pk}
    assert (unknown.status, unknown.reason) == ("unavailable", "unknown_filter_value")
    assert (invalid.status, invalid.reason) == ("unavailable", "invalid_argument")
    # Only the narrowed search embedded: an unknown filter is refused before anything is spent.
    assert embedder.calls == [(["flooding"], "query")]
    assert ProviderReservation.objects.filter(purpose="query", lane="research", owner="ai").count() == 1


def test_a_passage_the_reader_cannot_read_is_never_returned_however_close_its_vector(research, space):
    owner = make_user("hybrid-owner@cit.edu")
    stranger = make_user("hybrid-stranger@cit.edu")
    private = paper("Unpublished flood draft", {2: [("Body", "flooding draft finding")]},
                    status=PipelineStatus.DRAFT, owner=owner)
    public = paper("Published pond study", {3: [("Body", "pond sampling")]})
    embed(space, private, record_axis=0, chunk_axes=[0])
    embed(space, public, record_axis=1, chunk_axes=[1])
    embedder = QueryEmbedder({"flooding": axis(0)})

    async def script(tools):
        await tools.hybrid_search("flooding")

    ((_, as_owner),) = run(research, owner, script, key="hybrid-owner-1", embedder=embedder)
    ((_, as_stranger),) = run(research, stranger, script, key="hybrid-stranger-1", embedder=embedder)
    assert private.pk in {p.record_id for p in as_owner.passages}
    assert {p.record_id for p in as_stranger.passages} == {public.pk}
    assert as_stranger.coverage.inspected_records == 1
    assert private.pk not in {r.record_id for r in as_stranger.records}


def test_paper_chat_scope_confines_every_signal_to_its_paper(research, space):
    reader = make_user("hybrid-scope@cit.edu")
    chosen = paper("Chosen paper", {1: [("Body", "pond sampling")]})
    other = paper("Other paper", {1: [("Body", "flooding everywhere")]})
    embed(space, chosen, record_axis=1, chunk_axes=[1])
    embed(space, other, record_axis=0, chunk_axes=[0])
    embedder = QueryEmbedder({"flooding": axis(0)})

    async def script(tools):
        await tools.hybrid_search("flooding")

    ((_, found),) = run(research, reader, script, key="hybrid-scope-1", embedder=embedder,
                        record_id=chosen.pk)
    assert {p.record_id for p in found.passages} == {chosen.pk}


def test_a_space_change_during_the_run_refuses_meaning_search_and_never_mixes_spaces(research, space):
    reader = make_user("hybrid-space@cit.edu")
    flood = paper("Flood forecasting", {4: [("Methods", "rainfall gauges")]})
    embed(space, flood, record_axis=0, chunk_axes=[0])
    embedder = QueryEmbedder({"inundation": axis(0)})

    async def script(tools):
        await tools.hybrid_search("inundation")
        await asyncio.to_thread(promote_a_new_space, space)
        await tools.hybrid_search("inundation")

    (_, before), (_, after) = run(research, reader, script, key="hybrid-space-1", embedder=embedder)
    assert dict(before.signals)["semantic"] == "ok" and before.passages
    assert dict(after.signals)["semantic"] == "embedding_space_changed"
    assert after.status == "no_match" and not after.passages
    assert len(embedder.calls) == 1, "nothing is paid for once the space has moved"


def promote_a_new_space(old):
    from django.db import connections

    EmbeddingSpace.objects.filter(pk=old.pk).update(state="retired")
    EmbeddingSpace.objects.create(model_id=MODEL, dimensions=1024, metric="cosine", state="active")
    connections.close_all()


@pytest.mark.parametrize("name", ["PAPER_FIRST_SQL", "FLAT_SQL"])
def test_vector_reads_scan_policy_filtered_rows_exactly_and_never_an_hnsw_index(research, space, name):
    """No HNSW scan depth can cut a filtered read short, because no HNSW index is read at all."""
    from ai.research import tools as research_tools
    from .grant_support import probe_login

    reader = make_user(f"hybrid-explain-{name.lower()}@cit.edu")
    flood = paper("Flood forecasting", {4: [("Methods", "rainfall gauges")]})
    embed(space, flood, record_axis=0, chunk_axes=[0])
    sql = getattr(research_tools, name)
    vector = json.dumps(axis(0))
    args = [space.pk, None, vector, 20, *([20] if name == "PAPER_FIRST_SQL" else []), *([None] * 6)]
    with probe_login("iris_ai_runtime") as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT iris_authz.begin_research(%s, 'reader_session')",
                               [issue.reader_session_grant(reader).token])
                # Give the planner every reason to prefer an index if one could serve the read.
                cursor.execute("SET LOCAL enable_seqscan = off")
                cursor.execute("PREPARE probe AS " + sql)
                cursor.execute("EXPLAIN EXECUTE probe(" + ", ".join(["%s"] * len(args)) + ")", args)
                plan = "\n".join(row[0] for row in cursor.fetchall())
        finally:
            conn.rollback()
    assert "Function Scan on research_vectors" in plan
    assert "hnsw" not in plan.lower()
    assert "embedding" not in " ".join(line for line in plan.splitlines() if "Index" in line)


@dataclass
class Ranked:
    order: list
    input_tokens: int = 7


class RecordingReranker:
    model, endpoint, adapter = "rerank-2.5", "https://api.voyageai.com/v1", "recording"
    data_policy, account = "no-training", "recording"

    def __init__(self):
        self.calls = []

    async def rerank(self, query, texts):
        self.calls.append((query, list(texts)))
        return Ranked(list(reversed(range(len(texts)))))


def two_proxy_papers(space):
    from django.utils import timezone

    first = paper("Flood forecasting", {1: [("Body", "flooding first")]})
    second = paper("Flood mapping", {1: [("Body", "flooding second")]})
    Record.objects.filter(pk__in=[first.pk, second.pk]).update(
        origin="synthetic", is_ip=False, is_embargoed=False, embargo_released_at=timezone.now())
    embed(space, first, record_axis=0, chunk_axes=[0])
    embed(space, second, record_axis=1, chunk_axes=[1])
    return first, second


def test_reranking_sends_nothing_unless_the_send_guard_admits_every_candidate(research, space):
    reader = make_user("hybrid-rerank-closed@cit.edu")
    two_proxy_papers(space)
    reranker = RecordingReranker()

    async def script(tools):
        await tools.hybrid_search("flooding")

    ((_, found),) = run(research, reader, script, key="hybrid-rerank-closed-1",
                        embedder=QueryEmbedder({"flooding": axis(0)}), reranker=reranker)
    assert dict(found.signals)["rerank"] == "withheld"
    assert reranker.calls == []
    assert len(found.passages) == 2
    assert not ProviderReservation.objects.filter(operation="rerank").exists()


def test_an_admitted_rerank_reorders_the_fused_candidates_and_is_charged_to_the_run(research, space):
    from datetime import timedelta

    from django.utils import timezone

    from ai.admission.guard import ProxyApproval, SendGuard
    from ai.research.tools import Source

    reader = make_user("hybrid-rerank-open@cit.edu")
    first, second = two_proxy_papers(space)
    sources = frozenset(Source(r.pk, cs.pk, cs.extraction_hash) for r in (first, second)
                        for cs in r.chunk_sets.filter(is_active=True))
    reranker = RecordingReranker()
    approval = ProxyApproval("IR-889", reranker.model, reranker.endpoint, reranker.account, "ir725-test",
                             timezone.now() + timedelta(hours=1), sources)

    async def script(tools):
        await tools.hybrid_search("flooding")

    ((_, found),) = run(research, reader, script, key="hybrid-rerank-open-1",
                        embedder=QueryEmbedder({"flooding": axis(0)}), reranker=reranker,
                        send_guard=SendGuard(research[1]["dsn"], approval, stage="development"))
    assert dict(found.signals)["rerank"] == "ok"
    (query, texts), = reranker.calls
    assert query == "flooding" and texts == ["flooding first", "flooding second"]
    assert [p.text for p in found.passages] == ["flooding second", "flooding first"]
    assert ProviderReservation.objects.filter(operation="rerank", purpose="query", lane="research").count() == 1
