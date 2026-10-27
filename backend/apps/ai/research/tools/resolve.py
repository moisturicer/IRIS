"""`resolve_papers`: names and displayed ordinals to record handles (IR-591).

Exact titles are a fast path; anything looser that fits several papers is an
ambiguity group, never a silent choice. Unknown and withheld references look
the same. Discovery ("find two papers") belongs to `search_research`.
"""

from __future__ import annotations

import re

from apps.ai.research.registry import Tool, ToolRun
from apps.ai.research.results import (
    Completeness, Coverage, CoverageSubject, Shaped, Status, SubjectCoverage, ToolResult,
    status_for,
)
from apps.ai.research.schema import ArgumentsRejected
from apps.ai.research.titles import title_matches

from .common import QUERY, collect_record, disclosable, readable_records

#: How many candidates an ambiguity group shows.
MAX_CANDIDATES = 5


def _overlap(record, topic: str) -> int:
    words = set(re.findall(r"\w{4,}", topic.casefold()))
    return len(words & set(re.findall(r"\w{4,}", f"{record.title} {record.abstract}".casefold())))


def resolve_papers(run: ToolRun, args: dict) -> ToolResult:
    references, ordinals = args.get("references", []), args.get("ordinals", [])
    if not references and not ordinals:
        raise ArgumentsRejected("missing_argument")
    titled = list(readable_records(run.ctx).only("pk", "title"))
    matches = [title_matches(titled, reference) for reference in references]
    current = run.current_presentation
    presented = current.record_ids if current is not None else ()
    wanted = {r.pk for _, found in matches for r in found}
    wanted |= {presented[n - 1] for n in ordinals if n <= len(presented)}
    # Withheld from a vendor is indistinguishable from unknown.
    allowed = disclosable(run.ctx, wanted)

    items, evidence, limitations = [], [], set()
    resolved = ambiguous = 0
    for index, (basis, found) in enumerate(matches, 1):
        found = [allowed[r.pk] for r in found if r.pk in allowed]
        if not found:
            items.append({"reference": index, "kind": "title", "match": "none"})
            continue
        if len(found) == 1:
            item = collect_record(run.ledger, found[0])
            evidence.append(item)
            items.append({"reference": index, "kind": "title", "match": basis,
                          "record": item.handle, "title": item.record_title})
            resolved += 1
            continue
        topic = args.get("topic", "")
        found.sort(key=lambda r: (-_overlap(r, topic), r.title, r.pk))
        if len(found) > MAX_CANDIDATES:
            limitations.add("candidates_truncated")
        candidates = []
        for record in found[:MAX_CANDIDATES]:
            item = collect_record(run.ledger, record)
            evidence.append(item)
            candidates.append({"record": item.handle, "title": record.title,
                               "year": record.year_completed})
        items.append({"reference": index, "kind": "title", "match": "ambiguous",
                      "basis": basis, "candidates": candidates})
        ambiguous += 1

    if ordinals and run.presented is None:
        limitations.add("no_presented_list")
    elif ordinals and current is None:
        limitations.add("stale_presentation")
    for offset, ordinal in enumerate(ordinals, len(references) + 1):
        pk = presented[ordinal - 1] if ordinal <= len(presented) else None
        if pk is None or pk not in allowed:
            items.append({"reference": offset, "kind": "ordinal", "ordinal": ordinal,
                          "match": "none"})
            continue
        item = collect_record(run.ledger, allowed[pk])
        evidence.append(item)
        items.append({"reference": offset, "kind": "ordinal", "ordinal": ordinal,
                      "match": "presented_order", "record": item.handle,
                      "title": item.record_title})
        resolved += 1

    requested = len(references) + len(ordinals)
    if ambiguous:
        status = Status.AMBIGUOUS
    elif resolved == requested:
        status = Status.OK
    else:
        status = Status.PARTIAL if resolved else Status.EMPTY
    coverage = SubjectCoverage(CoverageSubject.REQUESTED_SELECTION, returned=resolved,
                               total=requested, complete=resolved == requested)
    return ToolResult(
        status_for(len(evidence)), Coverage(Completeness.MATCHES_FOUND, returned=resolved),
        tuple(evidence),
        shaped=Shaped(status, coverage, items=tuple(items),
                      limitations=tuple(sorted(limitations))),
    )


def _presentation(run: ToolRun):
    p = run.current_presentation
    return None if p is None else [p.revision, list(p.record_ids)]


RESOLVE_PAPERS = Tool(
    name="resolve_papers",
    description=(
        "Turn paper names the reader used (full titles, short names) or "
        "ordinals of the papers last shown to them into record handles. "
        "Several matches come back as an ambiguity group to ask about. For "
        "finding papers on a topic, use search_research instead."
    ),
    parameters={
        "type": "object",
        "properties": {
            "references": {"type": "array", "maxItems": 8,
                           "items": {"type": "string", "minLength": 1, "maxLength": 300}},
            "ordinals": {"type": "array", "maxItems": 8,
                         "items": {"type": "integer", "minimum": 1, "maximum": 50}},
            "topic": QUERY,
        },
        "additionalProperties": False,
    },
    execute=resolve_papers,
    subject=CoverageSubject.REQUESTED_SELECTION,
    cache_context=_presentation,
)
