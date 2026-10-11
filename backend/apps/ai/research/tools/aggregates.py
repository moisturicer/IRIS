"""`count_records` and `corpus_facets`: `COUNT(DISTINCT id)` over readable records (ADR-038 §6)."""

from __future__ import annotations

from django.conf import settings
from django.db.models import Count

from apps.ai.research.registry import Tool, ToolRun
from apps.ai.research.results import Completeness, Coverage, ToolResult, ToolStatus, status_for

from .common import FILTER_PROPERTIES, apply_filters, readable_records

_GROUPS = {
    "classification": "classification__name",
    "psced": "psced__name",
    "record_type": "record_type__name",
    "year": "year_completed",
}
_AREAS = {"classification": "classification__name", "psced": "psced__name"}

#: Every count is relative to the asker (ADR-027 §3); the planner words it so.
RELATIVE_TO = "of the records you can see"


def _grouped(records, column: str) -> list[dict]:
    rows = records.values(column).annotate(n=Count("pk", distinct=True)).order_by(column)
    return [{"value": row[column], "count": row["n"]} for row in rows]


def count_records(run: ToolRun, args: dict) -> ToolResult:
    records = apply_filters(readable_records(run.ctx), args)
    if "is_ip" in args:
        records = records.filter(is_ip=args["is_ip"])
    total = records.count()
    detail: dict = {"total": total, "relative_to": RELATIVE_TO}

    group_by = args.get("group_by")
    if group_by:
        groups = _grouped(records, _GROUPS[group_by])
        detail["groups"] = [g for g in groups if g["value"] is not None]
        detail["unclassified" if group_by != "year" else "undated"] = sum(
            g["count"] for g in groups if g["value"] is None
        )

    return ToolResult(
        status_for(total),
        Coverage(Completeness.EXHAUSTIVE, returned=total),
        detail=detail,
    )


def corpus_facets(run: ToolRun, args: dict) -> ToolResult:
    records = readable_records(run.ctx)
    sample = records.count()
    floor = settings.AI_LANDSCAPE_MIN_RECORDS
    if sample < floor:
        # ADR-027 §1d: below the floor there is no landscape to describe.
        return ToolResult(
            ToolStatus.REFUSED,
            Coverage(Completeness.EXHAUSTIVE, note="below_floor"),
            detail={"sample_size": sample, "floor": floor},
        )

    column = _AREAS[args["dimension"]]
    unclassified = records.filter(**{f"{column}__isnull": True}).count()
    share = round(unclassified / sample, 3) if sample else 0.0
    limit = settings.AI_LANDSCAPE_MAX_UNCLASSIFIED_SHARE
    if share > limit:
        # ADR-027 §1b: too much is unfiled for a landscape to mean anything.
        return ToolResult(
            ToolStatus.REFUSED,
            Coverage(Completeness.EXHAUSTIVE, note="unclassified_share"),
            detail={"sample_size": sample, "unclassified": unclassified,
                    "unclassified_share": share, "limit": limit},
        )

    areas = [g for g in _grouped(records, column) if g["value"] is not None]
    by_year: dict[str, list[dict]] = {}
    rows = (
        records.exclude(**{f"{column}__isnull": True})
        .values(column, "year_completed")
        .annotate(n=Count("pk", distinct=True))
        .order_by(column, "year_completed")
    )
    for row in rows:
        by_year.setdefault(row[column], []).append(
            {"year": row["year_completed"], "count": row["n"]}
        )
    return ToolResult(
        ToolStatus.OK,
        Coverage(Completeness.EXHAUSTIVE, returned=len(areas)),
        detail={
            "dimension": args["dimension"],
            "sample_size": sample,
            "areas": [{**a, "by_year": by_year.get(a["value"], [])} for a in areas],
            "unclassified": unclassified,
            "unclassified_share": share,
            "relative_to": RELATIVE_TO,
        },
    )


COUNT_RECORDS = Tool(
    name="count_records",
    description=(
        "Count the papers this reader can see by metadata: classification, "
        "PSCED area, record type, completion year, IP flag. Exact over visible "
        "records; optionally grouped. Cannot count by topic."
    ),
    parameters={
        "type": "object",
        "properties": {
            **FILTER_PROPERTIES,
            "is_ip": {"type": "boolean"},
            "group_by": {"type": "string", "enum": list(_GROUPS)},
        },
        "additionalProperties": False,
    },
    execute=count_records,
)

CORPUS_FACETS = Tool(
    name="corpus_facets",
    description=(
        "Paper counts per named Area over time, with the unclassified count and "
        "sample size. Refuses below a minimum number of visible papers, or "
        "when too many are unclassified."
    ),
    parameters={
        "type": "object",
        "properties": {"dimension": {"type": "string", "enum": list(_AREAS)}},
        "required": ["dimension"],
        "additionalProperties": False,
    },
    execute=corpus_facets,
)
