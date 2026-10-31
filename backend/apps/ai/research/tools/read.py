"""`read_papers`: outline, sections, pages or a cached brief (IR-591).

Section identifiers come from the outline, never guessed headings. Each
record has its own continuation, so a long paper's late sections are read
without replaying its prefix. Every read checks the active version and gate.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

from apps.ai.briefs import cached_brief
from apps.ai.comparison.service import table_fields
from apps.ai.models.chunk import DocumentChunk
from apps.ai.research.ledger import HANDLE_SCHEMA
from apps.ai.research.registry import Tool, ToolRun
from apps.ai.research.results import (
    Completeness, Coverage, CoverageSubject, Shaped, Status, SubjectCoverage, ToolResult,
    status_for,
)
from apps.ai.research.schema import ArgumentsRejected

from .common import collect_record, disclosable
from .passages import RECORD_HANDLES
from .sections import READ_SCORE

VIEWS = ("outline", "sections", "pages", "brief")
SECTION_ID = {"type": "string", "minLength": 9, "maxLength": 9}


def section_id(path: tuple[str, ...]) -> str:
    """Keyed by the whole heading path, so repeated headings stay distinct."""
    key = "\x1f".join(part.casefold() for part in path)
    return "S" + hashlib.sha256(key.encode()).hexdigest()[:8]


def _headings(record, chunk) -> list[str]:
    return [part for part in chunk.context_path or () if part != record.title]


def _section_ids(record, chunk) -> list[str]:
    path = _headings(record, chunk)
    return [section_id(tuple(path[:level])) for level in range(1, len(path) + 1)]


def _outline(record, chunks) -> list[dict]:
    sections: dict[str, dict] = {}
    for chunk in chunks:
        path = _headings(record, chunk)
        for level, ident in enumerate(_section_ids(record, chunk), 1):
            entry = sections.setdefault(ident, {
                "section": ident, "heading": path[level - 1], "level": level,
                "first_page": chunk.source_page, "last_page": chunk.source_page,
            })
            entry["last_page"] = chunk.source_page
    return list(sections.values())


def _check(args: dict) -> None:
    view = args["view"]
    if "sections" in args and view != "sections":
        raise ArgumentsRejected("selector_view_mismatch")
    if "pages" in args and view != "pages":
        raise ArgumentsRejected("selector_view_mismatch")
    if "sections" in args and not args["sections"]:
        raise ArgumentsRejected("missing_argument")
    if view == "pages" and not args.get("pages"):
        raise ArgumentsRejected("missing_argument")
    if "cursor" in args and (len(args["records"]) != 1 or view not in ("sections", "pages")):
        raise ArgumentsRejected("cursor_needs_one_record")
    if not args["records"]:
        raise ArgumentsRejected("missing_argument")


def read_papers(run: ToolRun, args: dict) -> ToolResult:
    _check(args)
    handles = list(dict.fromkeys(args["records"]))
    ids = {handle: run.ledger.record_id(handle) for handle in handles}
    allowed = disclosable(run.ctx, ids.values())
    # Each paper reads within its own share, so one cannot starve another.
    share = max(1, run.ctx.budget.read_token_cap // len(handles))

    items, facts, evidence, continuations = [], [], [], []
    returned, complete = 0, True
    for handle in handles:
        record = allowed.get(ids[handle])
        if record is None:
            items.append({"record": handle, "state": "unavailable"})
            complete = False
            continue
        evidence.append(collect_record(run.ledger, record))
        chunks = list(
            DocumentChunk.objects.filter(
                record=record, chunk_set__is_active=True, deleted_at__isnull=True)
            .select_related("chunk_set").order_by("sequence")
        )
        if not chunks:
            items.append({"record": handle, "state": "not_indexed"})
            complete = False
            continue
        version = chunks[0].chunk_set.content_hash
        if args["view"] == "outline":
            pages = [c.source_page for c in chunks if c.source_page is not None]
            items.append({
                "record": handle, "state": "read", "source_version": version[:12],
                "sections": _outline(record, chunks),
                "pages": [min(pages), max(pages)] if pages else None,
            })
            continue
        if args["view"] == "brief":
            item, brief_facts, brief_evidence = _brief(run, handle, record)
            items.append(item)
            facts.extend(brief_facts)
            evidence.extend(brief_evidence)
            complete = complete and item["state"] == "read"
            continue

        selected = _selected(record, chunks, args)
        cursor_args = {**args, "records": [handle]}
        position = (run.resume_cursor(args["cursor"], "read_papers", cursor_args,
                                      source_version=version) if "cursor" in args else 0)
        spent, stop = 0, len(selected)
        for index in range(position, len(selected)):
            chunk = selected[index]
            # The first chunk is always read, so a continuation always advances.
            if index > position and spent + chunk.token_count > share:
                stop = index
                break
            spent += chunk.token_count
            evidence.append(run.ledger.add_passage(
                record_id=record.pk, chunk_id=chunk.pk, chunk_set_hash=version,
                record_title=record.title, text=chunk.content, page=chunk.source_page,
                context_path=tuple(chunk.context_path or ()), score=READ_SCORE,
            ))
        read = selected[position:stop]
        returned += len(read)
        following = None
        if stop < len(selected):
            complete = False
            following = run.issue_cursor("read_papers", cursor_args,
                                         source_version=version, position=stop)
            continuations.append(following)
        pages = [c.source_page for c in read if c.source_page is not None]
        items.append({
            "record": handle, "state": "partial" if following else "read",
            "source_version": version[:12],
            "sections": list(dict.fromkeys(
                ident for c in read for ident in _section_ids(record, c))),
            "pages": [min(pages), max(pages)] if pages else None,
            "continuation": following,
        })

    evidence = [e for e in dict.fromkeys(evidence) if run.ledger.holds(e)]
    read_any = any(item["state"] in ("read", "partial") for item in items)
    if not read_any:
        status = Status.EMPTY
    else:
        status = Status.OK if complete else Status.PARTIAL
    limitations = sorted({f"record_{item['state']}" for item in items
                          if item["state"] not in ("read", "partial")}
                         | ({"truncated"} if continuations else set()))
    return ToolResult(
        status_for(int(read_any)),
        Coverage(Completeness.EXHAUSTIVE if complete else Completeness.SAMPLE,
                 returned=returned, truncated=bool(continuations)),
        tuple(evidence),
        shaped=Shaped(
            status,
            SubjectCoverage(CoverageSubject.REQUESTED_SELECTION, returned=returned,
                            complete=complete and read_any),
            items=tuple(items), facts=tuple(facts),
            continuation=continuations[0] if len(handles) == 1 and continuations else None,
            limitations=tuple(limitations),
        ),
    )


def _selected(record, chunks, args) -> list:
    if args["view"] == "pages":
        pages = set(args["pages"])
        if pages - {c.source_page for c in chunks}:
            raise ArgumentsRejected("unknown_page")
        return [c for c in chunks if c.source_page in pages]
    wanted = set(args.get("sections", ()))
    if not wanted:
        return chunks
    known = {entry["section"] for entry in _outline(record, chunks)}
    if wanted - known:
        raise ArgumentsRejected("unknown_section")
    return [c for c in chunks if wanted & set(_section_ids(record, c))]


def _brief(run: ToolRun, handle: str, record):
    """A cached IR-556 brief; it is never generated from here."""
    result = cached_brief(record, user=run.ctx.user)
    if result["state"] != "ready":
        return {"record": handle, "state": "brief_unavailable",
                "reason": result.get("reason", result["state"])}, [], []
    brief = result["brief"]
    fields, _ = table_fields(brief, record)
    facts, evidence = brief_facts(run, record, handle, brief, fields)
    return {"record": handle, "state": "read", "source_version": brief["content_hash"][:12],
            "cached": True}, facts, evidence


def brief_facts(run: ToolRun, record, handle: str, brief: dict, fields: dict):
    provenance = {"kind": "paper_brief", "source_version": brief["content_hash"][:12],
                  "prompt_version": brief["prompt_version"], "cached": True}
    return cited_facts(run, record, handle, fields, brief["content_hash"], provenance)


def cited_facts(run: ToolRun, record, handle: str, fields: dict, version: str,
                provenance: dict):
    """Verified fields as facts whose citations are passage handles."""
    chunks = DocumentChunk.objects.in_bulk({
        c["chunk_id"] for field in fields.values() for v in field["values"]
        for c in v["citations"]})
    facts, evidence = [], []
    for name, field in fields.items():
        values = []
        for value in field["values"]:
            citations = []
            for citation in value["citations"]:
                item = passage(run, record, chunks[citation["chunk_id"]], version)
                evidence.append(item)
                citations.append({"ref": item.handle, "page": citation["page"],
                                  "quote": citation["quote"]})
            values.append({k: v for k, v in value.items() if k != "citations"}
                          | {"citations": citations})
        facts.append({"name": name, "record": handle, "state": field["state"],
                      "values": values, "provenance": provenance})
    return facts, evidence


def passage(run: ToolRun, record, chunk, version: str):
    return run.ledger.add_passage(
        record_id=record.pk, chunk_id=chunk.pk, chunk_set_hash=version,
        record_title=record.title, text=chunk.content, page=chunk.source_page,
        context_path=tuple(chunk.context_path or ()), score=READ_SCORE,
    )


def without_brief(tool: Tool) -> Tool:
    """`read_papers` offered with no brief view, while briefs are off (IR-703)."""
    views = [v for v in VIEWS if v != "brief"]
    properties = {**tool.parameters["properties"], "view": {"type": "string", "enum": views}}
    description = tool.description.replace(
        "view=brief returns a cached whole-paper brief when one exists. ", "")
    return replace(tool, description=description,
                   parameters={**tool.parameters, "properties": properties})


READ_PAPERS = Tool(
    name="read_papers",
    description=(
        "Read papers by record handle. view=outline lists each paper's section "
        "identifiers and pages; view=sections reads those identifiers (or the "
        "paper from the start); view=pages reads given pages; view=brief returns "
        "a cached whole-paper brief when one exists. Long reads return a "
        "per-paper continuation token to resume where they stopped."
    ),
    parameters={
        "type": "object",
        "properties": {
            "records": {**RECORD_HANDLES, "maxItems": 5},
            "view": {"type": "string", "enum": list(VIEWS)},
            "sections": {"type": "array", "maxItems": 20, "items": SECTION_ID},
            "pages": {"type": "array", "maxItems": 20,
                      "items": {"type": "integer", "minimum": 1, "maximum": 10_000}},
            "cursor": HANDLE_SCHEMA,
        },
        "required": ["records", "view"],
        "additionalProperties": False,
    },
    execute=read_papers,
    subject=CoverageSubject.REQUESTED_SELECTION,
)
