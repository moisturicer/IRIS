"""`extract_evidence`: sourced fields, typed metrics or screening (IR-591).

Brief fields reuse a cached IR-556 brief; any other bounded field is read
from the paper with page-cited quotes and verified the same way. Screening
covers the issued records only. Cross-paper synthesis is the answer model's.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace

from django.conf import settings

from apps.ai.briefs import cached_brief
from apps.ai.briefs.reading import FIELDS, SYSTEM as BRIEF_SYSTEM
from apps.ai.briefs.reading import combine, reading_sections, verify_fields
from apps.ai.comparison.service import table_fields
from apps.ai.history import estimate_tokens
from apps.ai.inference import InferenceTask, profile_for
from apps.ai.inference.providers import BRIEF_OUTPUT_TOKENS
from apps.ai.models.chunk import ChunkSet
from apps.ai.overview.assembly import whole_paper
from apps.ai.overview.pages import build_page_prompt
from apps.ai.providers.deadline import model_call_deadline
from apps.ai.research.budget import BudgetExhausted
from apps.ai.research.registry import Tool, ToolRun
from apps.ai.research.results import (
    Completeness, Coverage, CoverageSubject, Shaped, Status, SubjectCoverage, ToolResult,
    coverage_for, status_for,
)
from apps.ai.research.schema import ArgumentsRejected

from .common import QUERY, collect_record, disclosable
from .passages import RECORD_HANDLES
from .read import brief_facts, cited_facts
from .screening import screen_records

logger = logging.getLogger(__name__)

#: Papers one describe or compare call extracts from.
MAX_RECORDS = 5
#: Model reads per paper per call; a longer paper is reported partial.
MAX_BATCHES = 6

SYSTEM = BRIEF_SYSTEM.replace(
    "Use exactly these field names: " + ", ".join(FIELDS) + ". ",
    "Use exactly the field keys listed in the request; each key names a requested "
    "detail. ",
) + (
    ' A value that reports a number may add "metric":{"name":"accuracy","value":92.5,'
    '"unit":"%","context":"dataset, task and conditions as reported"}; the number '
    "must appear in its cited quote."
)


def extract_evidence(run: ToolRun, args: dict) -> ToolResult:
    handles = list(dict.fromkeys(args["records"]))
    if not handles:
        raise ArgumentsRejected("missing_argument")
    ids = [run.ledger.record_id(handle) for handle in handles]
    if args["purpose"] == "screen":
        if "fields" in args or "criterion" not in args:
            raise ArgumentsRejected("screen_needs_criterion_only")
        return _screen(run, args, ids)
    if "criterion" in args or not args.get("fields"):
        raise ArgumentsRejected("fields_required")
    if len(handles) > MAX_RECORDS:
        raise ArgumentsRejected("too_many_records")

    fields = list(dict.fromkeys(f.strip() for f in args["fields"]))
    allowed = disclosable(run.ctx, ids)
    items, facts, evidence, limitations = [], [], [], set()
    answered = 0
    for handle, pk in zip(handles, ids):
        record = allowed.get(pk)
        if record is None:
            items.append({"record": handle, "state": "unavailable"})
            continue
        evidence.append(collect_record(run.ledger, record))
        chunk_set = ChunkSet.objects.filter(record=record, is_active=True).first()
        if chunk_set is None:
            items.append({"record": handle, "state": "not_indexed"})
            continue

        remaining, state = list(fields), "read"
        briefed = {f: _brief_name(f) for f in fields if _brief_name(f)}
        if briefed:
            cached = cached_brief(record, user=run.ctx.user)
            if cached["state"] == "ready" and cached["brief"]["chunk_set_id"] == chunk_set.pk:
                brief = cached["brief"]
                verified, _ = table_fields(brief, record)
                wanted = {name: verified[name] for name in briefed.values()}
                brief_rows, cited = brief_facts(run, record, handle, brief, wanted)
                by_field = {row["name"]: row for row in brief_rows}
                facts.extend({**by_field[briefed[f]], "name": f} for f in briefed)
                evidence.extend(cited)
                remaining = [f for f in fields if f not in briefed]
        if remaining:
            try:
                extracted, partial = _extract(run, record, chunk_set, remaining)
            except BudgetExhausted:
                limitations.add("budget_exhausted")
                extracted, partial = None, False
            except Exception as exc:
                # A vendor can echo input in its exception; log the type only.
                logger.warning("evidence extraction failed", extra={
                    "run_id": run.ctx.run_id, "error": type(exc).__name__})
                extracted, partial = None, False
            if extracted is None:
                state = "extraction_unavailable"
            else:
                rows, cited = cited_facts(
                    run, record, handle, extracted, chunk_set.content_hash,
                    {"kind": "extraction", "source_version": chunk_set.content_hash[:12],
                     "cached": False})
                facts.extend(rows)
                evidence.extend(cited)
                state = "partial" if partial else state
        # Fenced: a paper withheld or re-chunked meanwhile contributes nothing.
        if pk not in disclosable(run.ctx, [pk]) or not ChunkSet.objects.filter(
                pk=chunk_set.pk, is_active=True, content_hash=chunk_set.content_hash).exists():
            facts = [f for f in facts if f["record"] != handle]
            evidence = [e for e in evidence if e.record_id != pk]
            items.append({"record": handle, "state": "unavailable"})
            continue
        items.append({"record": handle, "state": state,
                      "source_version": chunk_set.content_hash[:12]})
        answered += state in ("read", "partial")

    for item in items:
        if item["state"] not in ("read",):
            limitations.add(f"record_{item['state']}")
    evidence = [e for e in dict.fromkeys(evidence) if run.ledger.holds(e)]
    complete = answered == len(handles) and all(i["state"] == "read" for i in items)
    if complete:
        status = Status.OK
    elif answered or facts:
        status = Status.PARTIAL
    else:
        status = Status.UNAVAILABLE if any(
            i["state"] == "extraction_unavailable" for i in items) else Status.EMPTY
    return ToolResult(
        status_for(len(facts)),
        Coverage(Completeness.EXHAUSTIVE if complete else Completeness.SAMPLE,
                 returned=answered),
        tuple(evidence),
        shaped=Shaped(
            status,
            SubjectCoverage(CoverageSubject.REQUESTED_SELECTION, returned=answered,
                            total=len(handles), complete=complete),
            items=tuple(items), facts=tuple(facts), limitations=tuple(sorted(limitations)),
        ),
    )


def _brief_name(field: str):
    name = "_".join(field.casefold().split())
    return name if name in FIELDS else None


def _extract(run: ToolRun, record, chunk_set, fields):
    """Verified fields by key, and whether the paper was only partly read."""
    profile = profile_for(InferenceTask.BRIEF)
    window = dict(profile.model_context_windows).get(profile.model)
    if window is None:
        return None, False
    keys = {f"field_{i}": name for i, name in enumerate(fields, 1)}
    request = f"Extract these details from {record.title}: " + json.dumps(keys, ensure_ascii=False)
    sources = whole_paper(chunk_set)
    if not sources:
        return None, False
    batches = reading_sections(request, sources, window, BRIEF_OUTPUT_TOKENS, system=SYSTEM)
    partial = len(batches) > MAX_BATCHES
    stored_text = dict(chunk_set.chunks.values_list("pk", "text"))
    llm = run.root.llm_for(InferenceTask.BRIEF)
    sections = []
    for batch in batches[:MAX_BATCHES]:
        if run.spend.remaining_seconds <= 0:
            raise BudgetExhausted("wall_clock_seconds")
        # Rechecked before every paid read, not only after.
        if record.pk not in disclosable(run.ctx, [record.pk]):
            raise PermissionError("withheld")
        prompt = build_page_prompt(request, batch)
        run.spend.charge_prompt_tokens(estimate_tokens(SYSTEM + prompt))
        with model_call_deadline(run.spend.remaining_seconds):
            reply = llm.generate(SYSTEM, prompt)
        sections.append(verify_fields(reply, batch, stored_text, fields=tuple(keys),
                                      metrics=True))
    combined = combine(sections, fields=tuple(keys))
    if partial:
        # Unread sections may report what the read ones did not.
        for field in combined.values():
            if field["state"] == "not_reported":
                field["state"] = "unsupported"
    return {keys[key]: field for key, field in combined.items()}, partial


def _screen(run: ToolRun, args: dict, ids: list[int]) -> ToolResult:
    if len(ids) > max(1, settings.AI_SCREEN_MAX_RECORDS):
        raise ArgumentsRejected("too_many_records")
    result = screen_records(replace(run, screen_candidate_ids=tuple(ids)),
                            {"criterion": args["criterion"]})
    coverage = coverage_for(result, CoverageSubject.SCREENED_SUBSET)
    rows = tuple(result.detail.get("rows", ()))
    if not result.evidence:
        status = Status.EMPTY
    else:
        status = Status.OK if coverage.complete else Status.PARTIAL
    facts = ({"name": "screening_method", "value": result.detail.get("method"),
              "provenance": {"kind": "screening", "criterion": args["criterion"]}},)
    return replace(result, shaped=Shaped(
        status, coverage, items=rows, facts=facts,
        limitations=("subset_classification",),
    ))


EXTRACT_EVIDENCE = Tool(
    name="extract_evidence",
    description=(
        "From papers named by record handle, extract requested details with "
        "page-cited quotes (purpose=describe or compare; up to 8 fields, typed "
        "metrics where a number is reported), or screen them against a criterion "
        "(purpose=screen). Each field is reported, not_reported or unsupported. "
        "Comparing the papers is left to you."
    ),
    parameters={
        "type": "object",
        "properties": {
            "records": {**RECORD_HANDLES, "maxItems": 20},
            "purpose": {"type": "string", "enum": ["describe", "compare", "screen"]},
            "fields": {"type": "array", "maxItems": 8,
                       "items": {"type": "string", "minLength": 1, "maxLength": 80}},
            "criterion": QUERY,
        },
        "required": ["records", "purpose"],
        "additionalProperties": False,
    },
    execute=extract_evidence,
    subject=CoverageSubject.REQUESTED_SELECTION,
)
