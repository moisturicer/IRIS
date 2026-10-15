"""`search_research`: papers or passages, ranked, never exhaustive (IR-591).

Adapts `find_records`' fusion and `search_passages`' retrieval; weights and
thresholds stay application policy. A cursor pages the same ranking.
"""

from __future__ import annotations

import hashlib

from apps.ai.research.ledger import HANDLE_SCHEMA, PASSAGE, EvidenceItem
from apps.ai.research.registry import Tool, ToolRun
from apps.ai.research.results import (
    Completeness, Coverage, CoverageSubject, Shaped, Status, SubjectCoverage, ToolResult,
    status_for,
)
from apps.ai.research.titles import title_key

from .common import (
    FILTER_PROPERTIES, QUERY, apply_filters, collect_record, disclosable,
    readable_records, scoped_ids, visible_record_ids,
)
from .passages import RECALL_DEPTH, RECORD_HANDLES, _chunk_set_hashes
from .records import rank_record_candidates


def _version(run: ToolRun) -> str:
    """What a cursor is valid for: the reader's visible set as it stood."""
    ids = ",".join(map(str, sorted(visible_record_ids(run.ctx))))
    return hashlib.sha256(ids.encode()).hexdigest()[:16]


def search_research(run: ToolRun, args: dict) -> ToolResult:
    requested = (
        {run.ledger.record_id(h) for h in args["records"]} if "records" in args else None
    )
    version = _version(run)
    start = (run.resume_cursor(args["cursor"], "search_research", args, source_version=version)
             if "cursor" in args else 0)
    limit = args.get("limit", 10)
    rank = _papers if args["target"] == "papers" else _passages
    ranked, degraded, issue = rank(run, args, requested)
    # Handles are issued for the page shown, never for the rest of the ranking.
    items, evidence = [], []
    for position in range(start, min(start + limit, ranked)):
        item, collected = issue(position)
        items.append(item)
        evidence.extend(collected)
    evidence = [e for e in dict.fromkeys(evidence) if run.ledger.holds(e)]
    following = None
    if start + limit < ranked:
        following = run.issue_cursor("search_research", args, source_version=version,
                                     position=start + limit)
    limitations = ["non_exhaustive"]
    if degraded:
        limitations.append("degraded")
    if start + limit < ranked and following is None:
        limitations.append("continuation_limit")
    if not items:
        status = Status.EMPTY
    else:
        status = Status.PARTIAL if degraded else Status.OK
    return ToolResult(
        status_for(len(items), degraded),
        Coverage(Completeness.SAMPLE, returned=len(items)),
        tuple(evidence),
        shaped=Shaped(
            status, SubjectCoverage(CoverageSubject.SEARCH_CANDIDATES, returned=len(items)),
            items=tuple(items), continuation=following, limitations=tuple(limitations),
        ),
    )


def _papers(run: ToolRun, args: dict, requested):
    fused, degraded, signals = rank_record_candidates(run, {"topic": args["query"], **{
        name: args[name] for name in FILTER_PROPERTIES if name in args}})
    if requested is not None:
        fused = [pk for pk in fused if pk in requested]
    allowed = disclosable(run.ctx, fused)
    ordered = [allowed[pk] for pk in fused if pk in allowed]
    # A paper named exactly by the query leads, apart from related candidates.
    key = title_key(args["query"])
    ordered.sort(key=lambda r: title_key(r.title) != key)

    def issue(position: int):
        record = ordered[position]
        item = collect_record(run.ledger, record)
        return {
            "record": item.handle, "title": record.title, "rank": position + 1,
            "match_kind": "exact_title" if title_key(record.title) == key else "related",
            "matched_by": [name for name, ids in signals.items() if record.pk in ids],
            "year": record.year_completed,
            "area": record.classification.name if record.classification else None,
            "type": record.record_type.name if record.record_type else None,
        }, (item,)

    return len(ordered), degraded, issue


def _passages(run: ToolRun, args: dict, requested):
    filtered = None
    if any(name in args for name in FILTER_PROPERTIES):
        filtered = set(apply_filters(readable_records(run.ctx), args).values_list("pk", flat=True))
    wanted = requested if filtered is None else (
        filtered if requested is None else requested & filtered)
    records = scoped_ids(run.ctx, wanted)
    if records is not None and not records:
        return 0, False, None
    result = run.root.retriever(records=records).retrieve(
        args["query"], run.ctx.user, limit=RECALL_DEPTH)
    allowed = disclosable(run.ctx, (p.record_id for p in result.passages))
    hashes = _chunk_set_hashes(p.chunk_id for p in result.passages)
    permitted = [p for p in result.passages if p.record_id in allowed and p.chunk_id in hashes]

    # Each paper's best passage before any paper's second (document diversity).
    by_record: dict[int, list] = {}
    for passage in permitted:
        by_record.setdefault(passage.record_id, []).append(passage)
    diverse = [group[depth] for depth in range(max(map(len, by_record.values()), default=0))
               for group in by_record.values() if depth < len(group)]

    def issue(position: int):
        passage = diverse[position]
        record = allowed[passage.record_id]
        owner = collect_record(run.ledger, record)
        item: EvidenceItem = run.ledger.add_passage(
            record_id=record.pk, chunk_id=passage.chunk_id,
            chunk_set_hash=hashes[passage.chunk_id], record_title=record.title,
            text=passage.content, page=passage.source_page,
            context_path=tuple(passage.context_path), score=passage.score,
        )
        return {"ref": item.handle, "record": owner.handle, "rank": position + 1,
                "match_kind": PASSAGE}, (owner, item)

    return len(diverse), result.degraded, issue


SEARCH_RESEARCH = Tool(
    name="search_research",
    description=(
        "Search the papers this reader can see, returning ranked papers or "
        "passages with their evidence. Optionally narrow to record handles "
        "from this run and filter by classification, PSCED area, record type "
        "or completion year. Results are the top matches, never every match; "
        "a continuation token pages further."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": QUERY,
            "target": {"type": "string", "enum": ["papers", "passages"]},
            "records": RECORD_HANDLES,
            **FILTER_PROPERTIES,
            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            "cursor": HANDLE_SCHEMA,
        },
        "required": ["query", "target"],
        "additionalProperties": False,
    },
    execute=search_research,
    subject=CoverageSubject.SEARCH_CANDIDATES,
)
