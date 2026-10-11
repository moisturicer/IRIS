"""`search_passages`: passages from the one retrieval stack (ADR-038 §2)."""

from __future__ import annotations

from typing import Iterable

from apps.ai.models.chunk import DocumentChunk
from apps.ai.research.ledger import PASSAGE, EvidenceItem
from apps.ai.research.registry import Tool, ToolRun
from apps.ai.research.results import Completeness, Coverage, ToolResult, ToolStatus, status_for

from .common import QUERY, collect_record, disclosable, scoped_ids

RECORD_HANDLES = {"type": "array", "items": {"type": "string"}, "maxItems": 10}

#: How many passages are recalled before the gate and the trim to `k`.
RECALL_DEPTH = 40


def _chunk_set_hashes(chunk_ids: Iterable[int]) -> dict[int, str]:
    return dict(
        DocumentChunk.objects.filter(pk__in=set(chunk_ids)).values_list(
            "pk", "chunk_set__content_hash"
        )
    )


def search_passages(run: ToolRun, args: dict) -> ToolResult:
    requested = (
        [run.ledger.record_id(h) for h in args["records"]] if "records" in args else None
    )
    records = scoped_ids(run.ctx, requested)
    if records is not None and not records:
        return ToolResult(ToolStatus.EMPTY, Coverage(Completeness.SAMPLE))

    # Recalled deeper than `k` and trimmed after the gate, so a withheld
    # record leaves no gap (ADR-035 §7).
    result = run.root.retriever(records=records).retrieve(
        args["query"], run.ctx.user, limit=RECALL_DEPTH
    )
    allowed = disclosable(run.ctx, (p.record_id for p in result.passages))
    hashes = _chunk_set_hashes(p.chunk_id for p in result.passages)
    permitted = [
        p for p in result.passages
        if p.record_id in allowed and p.chunk_id in hashes
    ][: args.get("k", 10)]

    evidence: list[EvidenceItem] = []
    for passage in permitted:
        record = allowed[passage.record_id]
        evidence.append(collect_record(run.ledger, record))
        evidence.append(
            run.ledger.add_passage(
                record_id=record.pk, chunk_id=passage.chunk_id,
                chunk_set_hash=hashes[passage.chunk_id],
                record_title=record.title, text=passage.content,
                page=passage.source_page,
                context_path=tuple(passage.context_path), score=passage.score,
            )
        )
    # A passage the ledger cap dropped is never handed to the planner.
    evidence = [e for e in _unique(evidence) if run.ledger.holds(e)]
    found = sum(1 for e in evidence if e.kind == PASSAGE)
    return ToolResult(
        status_for(found, result.degraded),
        Coverage(Completeness.SAMPLE, returned=found),
        tuple(evidence),
    )


def _unique(items: list[EvidenceItem]) -> list[EvidenceItem]:
    seen: set[str] = set()
    return [i for i in items if not (i.handle in seen or seen.add(i.handle))]


SEARCH_PASSAGES = Tool(
    name="search_passages",
    description=(
        "Search passages in the papers this reader can see. Optionally narrow "
        "to record handles (R1, R2...) returned earlier in this run. Returns "
        "the top passages only, never every match."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": QUERY,
            "records": RECORD_HANDLES,
            "k": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    execute=search_passages,
)
