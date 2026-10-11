"""`find_records`: record vectors, record full text and passage hits, fused by rank (ADR-033 §1)."""

from __future__ import annotations

from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import F
from pgvector.django import CosineDistance

from apps.ai.keyword_index import CONFIG
from apps.ai.models.embedding import RecordEmbedding
from apps.ai.models.embedding_space import EmbeddingSpace, EmbeddingSpaceState
from apps.ai.research.registry import Tool, ToolRun
from apps.ai.research.results import Completeness, Coverage, ToolResult, status_for
from apps.ai.retrieval.fusion import fuse_by_rank

from .common import (
    FILTER_PROPERTIES, QUERY, apply_filters, collect_record, disclosable,
    readable_records, scoped_ids,
)

#: How deep each signal is read before fusion.
SIGNAL_DEPTH = 40

#: How a record matched, reported to the planner.
BY_VECTOR, BY_KEYWORD, BY_PASSAGE = "vector", "keyword", "passage"


def rank_record_candidates(run: ToolRun, args: dict):
    """Rank visible scoped IDs locally, before disclosure (also used by screening).

    The embedding request carries only the topic; retrieved passage text is
    gated by the retrieval stack. No record content is returned to a model here.
    """
    topic = args["topic"]
    candidates = apply_filters(readable_records(run.ctx), args)
    degraded = False

    try:
        by_vector = _by_vector(run, candidates, topic)
    except Exception as exc:
        if not run.root.vendor_unavailable(exc):
            raise
        by_vector, degraded = [], True

    by_keyword = list(
        candidates.annotate(
            rank=SearchRank(F("search_vector"), SearchQuery(topic, config=CONFIG))
        )
        .filter(rank__gt=0)
        .order_by("-rank", "pk")
        .values_list("pk", flat=True)[:SIGNAL_DEPTH]
    )

    allowed_ids = set(candidates.values_list("pk", flat=True))
    # With a filter, passages are recalled within it rather than trimmed after.
    filtered = any(name in args for name in FILTER_PROPERTIES)
    scope = scoped_ids(run.ctx, allowed_ids) if filtered else scoped_ids(run.ctx, None)
    passages = run.root.retriever(records=scope).retrieve(
        topic, run.ctx.user, limit=SIGNAL_DEPTH
    )
    degraded = degraded or passages.degraded
    by_passage = list(
        dict.fromkeys(
            p.record_id for p in _relevant(passages) if p.record_id in allowed_ids
        )
    )

    signals = {BY_VECTOR: by_vector, BY_KEYWORD: by_keyword, BY_PASSAGE: by_passage}
    fused = fuse_by_rank(signals.values(), key=lambda pk: pk)
    return fused, degraded, signals


def find_records(run: ToolRun, args: dict) -> ToolResult:
    fused, degraded, signals = rank_record_candidates(run, args)
    k = args.get("k", 10)
    # Gated before the trim to `k`, so a withheld record leaves no gap.
    allowed = disclosable(run.ctx, fused)
    chosen = [pk for pk in fused if pk in allowed][:k]

    evidence, annotations = [], {}
    for pk in chosen:
        record = allowed[pk]
        item = collect_record(run.ledger, record)
        evidence.append(item)
        annotations[item.handle] = {
            "year": record.year_completed,
            "area": record.classification.name if record.classification else None,
            "type": record.record_type.name if record.record_type else None,
            "matched_by": [name for name, ids in signals.items() if pk in ids],
        }

    return ToolResult(
        status_for(len(evidence), degraded),
        Coverage(Completeness.MATCHES_FOUND, returned=len(evidence)),
        tuple(evidence),
        annotations=annotations,
    )


def _relevant(result):
    """Passages clearing the relevance cut-off (ADR-033 §3), once IR-396 adds it.

    Reranker scores only, so a degraded result has no cut-off to clear.
    """
    cut_off = getattr(settings, "AI_RELEVANCE_MIN_SCORE", None)
    if cut_off is None or result.degraded:
        return result.passages
    return [p for p in result.passages if p.score >= cut_off]


def _by_vector(run: ToolRun, candidates, topic: str) -> list[int]:
    if not EmbeddingSpace.objects.filter(state=EmbeddingSpaceState.ACTIVE).exists():
        return []
    vector = run.root.embedder().embed_query(topic)
    return list(
        RecordEmbedding.objects.filter(record__in=candidates.values("pk"))
        .order_by(CosineDistance("embedding", vector))
        .values_list("record_id", flat=True)[:SIGNAL_DEPTH]
    )


FIND_RECORDS = Tool(
    name="find_records",
    description=(
        "Find papers this reader can see about a topic, optionally filtered by "
        "classification, PSCED area, record type or completion year. Returns "
        "ranked matches with why each matched; never a complete list."
    ),
    parameters={
        "type": "object",
        "properties": {
            "topic": QUERY,
            **FILTER_PROPERTIES,
            "k": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        "required": ["topic"],
        "additionalProperties": False,
    },
    execute=find_records,
)
