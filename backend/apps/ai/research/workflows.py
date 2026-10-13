"""Application-owned corpus workflows; topic counts are never model-written."""

from dataclasses import replace

from django.conf import settings
from django.db.models import Count
from apps.ai.providers.deadline import model_call_deadline

from .registry import ToolRun, research_tools
from .results import Completeness, Coverage, ToolResult, ToolStatus
from .tools.common import FILTER_PROPERTIES, QUERY, apply_filters, readable_records
from .schema import validate
from .tools.records import rank_record_candidates


def topic_count(run: ToolRun, criterion: str, *, filters=None) -> ToolResult:
    """Find, screen, and count distinct visible papers. Never an exact count.

    `criterion` is visible in the result. The caller is application code, not
    another model tool; candidate identity and completeness are code-owned.
    """
    args = validate({"criterion": criterion, **(filters or {})}, {
        "type": "object", "properties": {"criterion": QUERY, **FILTER_PROPERTIES},
        "required": ["criterion"], "additionalProperties": False,
    })
    records = apply_filters(readable_records(run.ctx), args)
    visible = records.count()
    maximum = max(1, settings.AI_SCREEN_MAX_RECORDS)
    registry = research_tools()
    label = Completeness.SCREENED
    if visible <= maximum:
        ids = tuple(records.order_by("pk").values_list("pk", flat=True))
    else:
        label = Completeness.MATCHES_FOUND
        with model_call_deadline(run.spend.remaining_seconds):
            ranked, _, _ = rank_record_candidates(run, {"topic": criterion, **(filters or {})})
        ids = tuple(ranked[:min(10, maximum)])
    screened = registry.call(replace(run, screen_candidate_ids=ids),
                             "screen_records", {"criterion": criterion})
    if screened.status not in (ToolStatus.OK, ToolStatus.EMPTY, ToolStatus.DEGRADED):
        return screened
    included = [row["record"] for row in screened.detail["rows"]
                if row["decision"] == "include"]
    # SQL counts records, not retrieved chunks, versions, owners or a top-k size.
    current = records.filter(pk__in=[run.ledger.record_id(h) for h in included])
    total = current.aggregate(n=Count("pk", distinct=True))["n"]
    current_ids = set(current.values_list("pk", flat=True))
    matches = [row for row in screened.detail["rows"] if row["decision"] == "include"
               and run.ledger.record_id(row["record"]) in current_ids]
    checked, unassessed = screened.detail["checked"], screened.detail["unassessed"]
    wording = f"{total} matched out of {checked} checked; {unassessed} could not be assessed."
    if label is Completeness.MATCHES_FOUND:
        wording += " These are matches found; other visible papers were not checked."
    return replace(screened,
        coverage=Coverage(label, returned=total, truncated=label is Completeness.MATCHES_FOUND),
        detail={**screened.detail, "total": total, "matches": matches,
                "relative_to": "of the records you can see",
                "wording": wording},
    )
