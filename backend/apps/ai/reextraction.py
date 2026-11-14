"""Planning the corpus cutover to LlamaParse before paying for it (IR-842, ADR-056).

The plan is a value computed before anything is sent. Credits are an upper
bound: the price is the tier's dearest rate plus every add-on, as admission
reserves it. Descriptions cost per Figure and the Figures are not known until a
paper is read, so they are not estimated here.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Optional, Sequence

from django.db.models import Sum

ALREADY_READ = "already read by LlamaParse"
AWAITING_CONSENT = "awaiting consent or release"
NO_MANUSCRIPT = "no manuscript to read"
UNREADABLE = "file missing or not a readable PDF"
IN_FLIGHT = "a read is already queued or running"


@dataclass(frozen=True)
class CutoverItem:
    record_id: int
    pages: int = 0
    reason: str = ""
    #: Tokens of the active chunks, the most a re-embed could send.
    embed_tokens: int = 0


@dataclass(frozen=True)
class CutoverPlan:
    items: tuple[CutoverItem, ...]
    credits_per_page: Decimal
    credit_usd: Decimal
    embed_cost_per_million: float

    @property
    def to_read(self) -> tuple[CutoverItem, ...]:
        return tuple(i for i in self.items if not i.reason)

    @property
    def skipped(self) -> tuple[CutoverItem, ...]:
        return tuple(i for i in self.items if i.reason)

    @property
    def pages(self) -> int:
        return sum(i.pages for i in self.to_read)

    @property
    def credits(self) -> Decimal:
        return self.pages * self.credits_per_page

    @property
    def usd(self) -> Decimal:
        return self.credits * self.credit_usd

    @property
    def embed_tokens(self) -> int:
        return sum(i.embed_tokens for i in self.to_read)

    @property
    def embed_usd(self) -> float:
        return self.embed_tokens * self.embed_cost_per_million / 1_000_000

    def limited(self, count: int) -> "CutoverPlan":
        keep = {i.record_id for i in self.to_read[:count]}
        items = tuple(i for i in self.items if i.reason or i.record_id in keep)
        return replace(self, items=items)

    def exceeds(self, ceiling_credits: Decimal) -> bool:
        return ceiling_credits > 0 and self.credits > ceiling_credits


def _page_count(record) -> Optional[int]:
    from apps.ai.admission.extraction import pdf_pages

    try:
        with record.abstract_file.open("rb") as source:
            return pdf_pages(source.read())
    except (OSError, ValueError):
        return None


def _embed_tokens(record_id: int) -> int:
    from apps.ai.models import DocumentChunk

    total = DocumentChunk.objects.filter(
        record_id=record_id, chunk_set__is_active=True, deleted_at__isnull=True
    ).aggregate(total=Sum("token_count"))["total"]
    return total or 0


def _reason(record, extraction) -> str:
    from apps.ai.extraction.gate import permits
    from apps.documents.phases import ExtractionPhase

    if not record.abstract_file:
        return NO_MANUSCRIPT
    current = extraction is not None and extraction.source_revision == record.manuscript_revision
    if current and extraction.extractor == "llamaparse" and extraction.status == "done":
        return ALREADY_READ
    queued = extraction is not None and extraction.status == "queued" and extraction.phase == ExtractionPhase.QUEUED
    if current and (extraction.status in {"running", "retrying"} or queued):
        return IN_FLIGHT
    if not permits(record):
        return AWAITING_CONSENT
    return ""


def plan_cutover(record_ids: Optional[Sequence[int]] = None) -> CutoverPlan:
    """Every live Record with a manuscript, costed or skipped with its reason."""
    from apps.ai.admission.limits import read_extraction_price
    from apps.ai.backfill import cost_per_million
    from apps.documents.models import PdfExtraction
    from apps.records.models import Record

    price = read_extraction_price()
    records = Record.objects.filter(is_deleted=False).exclude(abstract_file="").order_by("pk")
    if record_ids:
        records = records.filter(pk__in=list(record_ids))
    extractions = {e.record_id: e for e in PdfExtraction.objects.filter(record__in=records)}

    items = []
    for record in records:
        reason = _reason(record, extractions.get(record.pk))
        pages = 0
        if not reason:
            pages = _page_count(record) or 0
            if not pages:
                reason = UNREADABLE
        items.append(CutoverItem(
            record_id=record.pk, pages=pages, reason=reason,
            embed_tokens=0 if reason else _embed_tokens(record.pk),
        ))
    return CutoverPlan(
        items=tuple(items),
        credits_per_page=price.credits_per_page + price.addon_credits_per_page,
        credit_usd=price.credit_usd,
        embed_cost_per_million=cost_per_million(),
    )


def queue_reads(plan: CutoverPlan) -> int:
    """Queue each planned read through the normal upload path, so the gate and
    admission apply. The reason is re-read under the Record lock: a paper read,
    queued or withdrawn since the plan was made is not sent twice or sent late.
    The old ChunkSet stays active until the new one swaps in."""
    from django.db import transaction

    from apps.documents.models import PdfExtraction
    from apps.documents.sources import reset_manuscript
    from apps.records.models import Record

    queued = 0
    for item in plan.to_read:
        with transaction.atomic():
            record = Record.objects.select_for_update().filter(pk=item.record_id, is_deleted=False).first()
            if record is None:
                continue
            extraction = PdfExtraction.objects.filter(record=record).first()
            if _reason(record, extraction):
                continue
            reset_manuscript(record, retry=True)
            queued += 1
    return queued


def rollback(record_ids: Sequence[int]) -> int:
    """Make each named record's previous ChunkSet active again.

    Only a live record whose manuscript was read by LlamaParse and that has an
    inactive set older than its active one has anything to go back to. Only
    chunks tombstoned by the swap (at or after the active set was made) come
    back. The extraction row is left as read: going forward again means a new
    paid read, because re-chunking the same read is a no-op."""
    from django.db import transaction

    from apps.ai.extraction.gate import permits
    from apps.ai.models import ChunkSet, DocumentChunk
    from apps.documents.models import PdfExtraction
    from apps.records.models import Record

    restored = 0
    for record_id in record_ids:
        with transaction.atomic():
            record = Record.objects.select_for_update().filter(pk=record_id, is_deleted=False).first()
            if record is None or not permits(record) or not PdfExtraction.objects.filter(
                record=record, extractor="llamaparse"
            ).exists():
                continue
            active = ChunkSet.objects.filter(record_id=record_id, is_active=True).first()
            if active is None:
                continue
            previous = (
                ChunkSet.objects.filter(record_id=record_id, is_active=False, trial_variant__isnull=True,
                                        created_at__lt=active.created_at)
                .order_by("-created_at", "-pk").first()
            )
            if previous is None:
                continue
            ChunkSet.objects.filter(pk=active.pk).update(is_active=False)
            ChunkSet.objects.filter(pk=previous.pk).update(is_active=True)
            DocumentChunk.objects.filter(
                chunk_set=previous, deleted_at__gte=active.created_at
            ).update(deleted_at=None)
            restored += 1
    return restored
