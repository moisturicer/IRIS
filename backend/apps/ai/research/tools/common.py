"""Visibility, scope, filters and the gate, shared by every tool (ADR-038 §2.2)."""

from __future__ import annotations

import hashlib
import json
from typing import Iterable, Optional

from django.db.models import QuerySet

from apps.ai.research.context import RunContext
from apps.ai.research.ledger import EvidenceItem, Ledger
from apps.ai.research.schema import ArgumentsRejected
from apps.records.models import Classification, PSCEDClassification, Record, RecordType

QUERY = {"type": "string", "minLength": 1, "maxLength": 300}
YEAR = {"type": "integer", "minimum": 1900, "maximum": 2100}
FILTER_PROPERTIES = {
    "classification": {"type": "string", "minLength": 1, "maxLength": 200},
    "psced": {"type": "string", "minLength": 1, "maxLength": 200},
    "record_type": {"type": "string", "minLength": 1, "maxLength": 100},
    "year_from": YEAR,
    "year_to": YEAR,
}
_TAXONOMIES = {
    "classification": Classification,
    "psced": PSCEDClassification,
    "record_type": RecordType,
}


def readable_records(ctx: RunContext) -> QuerySet:
    """The only way a tool reaches `Record`: `visible_to`, then scope."""
    visible = Record.objects.visible_to(ctx.user)
    if ctx.scope_record_id is not None:
        visible = visible.filter(pk=ctx.scope_record_id)
    # A plain queryset over the ids, so counts and grouping need no DISTINCT.
    return Record.objects.filter(pk__in=visible.values("pk"))


def scoped_ids(ctx: RunContext, requested: Optional[Iterable[int]]) -> Optional[frozenset[int]]:
    """The retriever's record set; `None` is unscoped. Never wider than scope."""
    wanted = frozenset(requested) if requested is not None else None
    if ctx.scope_record_id is None:
        return wanted
    scope = frozenset({ctx.scope_record_id})
    return scope & wanted if wanted is not None else scope


def visible_record_ids(ctx: RunContext) -> frozenset[int]:
    return frozenset(readable_records(ctx).values_list("pk", flat=True))


def apply_filters(records: QuerySet, args: dict) -> QuerySet:
    for name, model in _TAXONOMIES.items():
        value = args.get(name)
        if value is None:
            continue
        match = model.objects.filter(name__iexact=value.strip()).first()
        if match is None:
            raise ArgumentsRejected("unknown_filter_value")
        records = records.filter(**{name: match})
    if "year_from" in args:
        records = records.filter(year_completed__gte=args["year_from"])
    if "year_to" in args:
        records = records.filter(year_completed__lte=args["year_to"])
    return records


def disclosable(ctx: RunContext, record_ids: Iterable[int]) -> dict[int, Record]:
    """Readable records whose content may reach a vendor, by id."""
    records = readable_records(ctx).filter(pk__in=set(record_ids)).select_related(
        "classification", "record_type"
    )
    return {record.pk: record for record in records if ctx.permits(record)}


def collect_record(ledger: Ledger, record: Record) -> EvidenceItem:
    return ledger.add_record(record_id=record.pk, title=record.title, abstract=record.abstract)


def metadata_version(ctx: RunContext) -> str:
    """Fingerprint every visible aggregate input, including AI eligibility.

    Names participate because filters/facets use them. Gate decisions and active
    chunk sets participate because aggregate_records reports ai_readable. This
    digest is private; public population provenance continues to name only IDs.
    """
    from apps.ai.models.chunk import ChunkSet

    records = list(readable_records(ctx).select_related(
        "classification", "psced", "record_type").order_by("pk"))
    rows = [
        (record.pk, record.year_completed,
         record.classification.name if record.classification_id else None,
         record.psced.name if record.psced_id else None,
         record.record_type.name if record.record_type_id else None,
         record.is_ip, bool(ctx.permits(record)))
        for record in records
    ]
    indexed = list(ChunkSet.objects.filter(
        record_id__in=[record.pk for record in records], is_active=True,
    ).order_by("record_id", "pk").values_list(
        "record_id", "pk", "content_hash", "extraction_hash", "strategy_id"))
    payload = json.dumps({"records": rows, "index": indexed}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()
