"""`aggregate_records`: exact metadata counts and facets (IR-591).

Adapts `count_records` and `corpus_facets`. There is no topic argument: a
topic total is a screened subset, never a catalogue count.
"""

from __future__ import annotations

from apps.ai.models.chunk import ChunkSet
from apps.ai.research.registry import Tool, ToolRun
from apps.ai.research.results import CoverageSubject, ToolResult
from apps.ai.research.schema import ArgumentsRejected

from .aggregates import _AREAS, _GROUPS, corpus_facets, count_records
from .common import FILTER_PROPERTIES, apply_filters, readable_records, visible_record_ids


def aggregate_records(run: ToolRun, args: dict) -> ToolResult:
    args = dict(args)
    operation = args.pop("operation")
    if operation == "facets":
        if set(args) != {"dimension"}:
            raise ArgumentsRejected("unsupported_for_facets")
        return corpus_facets(run, args)
    if "dimension" in args:
        raise ArgumentsRejected("unsupported_for_count")
    result = count_records(run, args)
    counted = apply_filters(readable_records(run.ctx).filter(pk__in=result.visible_record_ids),
                            args)
    if "is_ip" in args:
        counted = counted.filter(is_ip=args["is_ip"])
    indexed = set(ChunkSet.objects.filter(record__in=counted, is_active=True)
                  .values_list("record_id", flat=True))
    # How many of the counted papers Ask IRIS could read: a separate fact.
    eligible = sum(1 for record in counted.filter(pk__in=indexed) if run.ctx.permits(record))
    return ToolResult(
        result.status, result.coverage, result.evidence,
        detail={**result.detail, "ai_readable": eligible},
        visible_record_ids=result.visible_record_ids,
    )


def _visibility(run: ToolRun) -> list[int]:
    return sorted(visible_record_ids(run.ctx))


AGGREGATE_RECORDS = Tool(
    name="aggregate_records",
    description=(
        "Exact metadata facts over the papers this reader can see. "
        "operation=count counts by classification, PSCED area, record type, "
        "completion year or IP flag, optionally grouped; operation=facets gives "
        "per-Area counts over time. Cannot count by topic."
    ),
    parameters={
        "type": "object",
        "properties": {
            "operation": {"type": "string", "enum": ["count", "facets"]},
            **FILTER_PROPERTIES,
            "is_ip": {"type": "boolean"},
            "group_by": {"type": "string", "enum": list(_GROUPS)},
            "dimension": {"type": "string", "enum": list(_AREAS)},
        },
        "required": ["operation"],
        "additionalProperties": False,
    },
    execute=aggregate_records,
    subject=CoverageSubject.METADATA_POPULATION,
    cache_context=_visibility,
)
