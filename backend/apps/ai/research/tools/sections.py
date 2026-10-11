"""`read_record_sections`: one paper in reading order, within a cap (ADR-038 §2)."""

from __future__ import annotations

from apps.ai.models.chunk import DocumentChunk
from apps.ai.research.ledger import PASSAGE
from apps.ai.research.registry import Tool, ToolRun
from apps.ai.research.results import Completeness, Coverage, ToolResult, ToolStatus, status_for
from apps.ai.research.schema import ArgumentsRejected
from apps.records.models import Record

from .common import collect_record, disclosable

#: A deliberately read section outranks any retrieval score for the ledger cap.
READ_SCORE = 1.0


def read_record_sections(run: ToolRun, args: dict) -> ToolResult:
    record_id = run.ledger.record_id(args["record"])
    record = disclosable(run.ctx, [record_id]).get(record_id)
    if record is None:
        return ToolResult(ToolStatus.EMPTY, Coverage(Completeness.SAMPLE))

    chunks = list(
        DocumentChunk.objects.filter(
            record=record, chunk_set__is_active=True, deleted_at__isnull=True
        )
        .select_related("chunk_set")
        .order_by("sequence")
    )
    headings = _headings(record, chunks)
    sections = {s.strip().casefold() for s in args.get("sections", ())}
    if sections - {h.casefold() for h in headings}:
        raise ArgumentsRejected("unknown_section")
    pages = set(args.get("pages", ()))
    if pages - {chunk.source_page for chunk in chunks}:
        raise ArgumentsRejected("unknown_page")

    selected = [
        chunk for chunk in chunks
        if (not sections and not pages)
        or sections & {p.casefold() for p in chunk.context_path or ()}
        or chunk.source_page in pages
    ]

    evidence = [collect_record(run.ledger, record)]
    spent, truncated = 0, False
    for chunk in selected:
        if spent + chunk.token_count > run.ctx.budget.read_token_cap:
            truncated = True
            break
        spent += chunk.token_count
        evidence.append(
            run.ledger.add_passage(
                record_id=record.pk, chunk_id=chunk.pk,
                chunk_set_hash=chunk.chunk_set.content_hash,
                record_title=record.title, text=chunk.content,
                page=chunk.source_page,
                context_path=tuple(chunk.context_path or ()), score=READ_SCORE,
            )
        )
    evidence = [e for e in evidence if run.ledger.holds(e)]
    found = sum(1 for e in evidence if e.kind == PASSAGE)
    label = Completeness.SAMPLE if truncated else Completeness.EXHAUSTIVE
    return ToolResult(
        status_for(found),
        Coverage(label, returned=found, truncated=truncated),
        tuple(evidence),
        detail={"headings": headings},
    )


def _headings(record: Record, chunks: list[DocumentChunk]) -> list[str]:
    seen: dict[str, str] = {}
    for chunk in chunks:
        for part in chunk.context_path or ():
            if part != record.title:
                seen.setdefault(part.casefold(), part)
    return list(seen.values())


READ_RECORD_SECTIONS = Tool(
    name="read_record_sections",
    description=(
        "Read one paper (a record handle from this run) in reading order: "
        "named sections from its own heading list, or pages. With neither, "
        "reads from the start. Output is capped; truncation is reported."
    ),
    parameters={
        "type": "object",
        "properties": {
            "record": {"type": "string", "minLength": 1, "maxLength": 12},
            "sections": {
                "type": "array", "maxItems": 10,
                "items": {"type": "string", "minLength": 1, "maxLength": 200},
            },
            "pages": {
                "type": "array", "maxItems": 20,
                "items": {"type": "integer", "minimum": 1, "maximum": 10_000},
            },
        },
        "required": ["record"],
        "additionalProperties": False,
    },
    execute=read_record_sections,
)
