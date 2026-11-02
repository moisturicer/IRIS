"""A record's AI Overview: generated once from the whole paper, then stored.

Invalidated by a re-chunk or a ``PROMPT_VERSION`` bump. Runs as the
``summary`` task, off until ``LLM_SUMMARY_MODEL`` is set (IR-380).
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.ai.answers.service import generate_cited, model_that_answered
from apps.ai.composition import composition_root
from apps.ai.inference import InferenceTask
from apps.ai.models import ChunkSet, RecordOverview
from apps.ai.presentation import citations as citations_wire
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.records.models import Record

from .assembly import whole_paper
from .hook import HOOK_INSTRUCTION, split_hook
from .pages import SYSTEM_PROMPT, build_page_prompt, parse_page_citations

logger = logging.getLogger(__name__)

#: 2: grounded in the whole paper, not six retrieved passages (IR-431).
#: 3: cites pages, not chunk numbers (IR-434).
#: 4: the comprehensive skeleton replaces two paragraphs of prose (IR-433).
#: 5: the same completion also writes a catalogue hook (IR-604).
PROMPT_VERSION = 5

# Formatting rules come from SYSTEM_PROMPT (IR-424); only structure lives here.
# The omission rule matters most: a filled-in Limitations section the paper
# never wrote is fabrication (ADR-025).
_QUESTION = (
    "Write a comprehensive overview of this work for a reader deciding "
    "whether to read it.\n"
    "Open with one paragraph: the problem, what the authors did, and what "
    "they found.\n"
    "Then use these '## ' sections, in this order: '## Objectives', "
    "'## Methodology', '## Key findings', '## Limitations and scope'.\n"
    "Omit any section the paper does not support. Never write a heading you "
    "cannot fill from the document, and never infer a limitation the authors "
    "do not state.\n"
    "Where a figure or table carries a finding, name it in the sentence and "
    "cite it.\n"
    "Close with one paragraph separating what the work demonstrates from what "
    "it only suggests.\n"
    f"{HOOK_INSTRUCTION}"
)


def _too_large(chunk_set: ChunkSet) -> bool:
    ceiling = getattr(settings, "AI_OVERVIEW_TOKEN_CEILING", 0)
    if not ceiling:
        return False
    total = chunk_set.chunks.filter(deleted_at__isnull=True).aggregate(
        total=Sum("token_count")
    )["total"]
    return (total or 0) > ceiling


def _claim_expired(stored: RecordOverview) -> bool:
    """A claim whose task was lost never reports back; reclaim it (IR-650)."""
    timeout = getattr(settings, "AI_OVERVIEW_CLAIM_TIMEOUT_SECONDS", 0)
    if not timeout:
        return False
    return timezone.now() - stored.updated_at > timedelta(seconds=timeout)


def overview_for(record: Record, *, retry: bool = False) -> dict:
    """Return a cached overview or queue one generation for the active paper."""
    # Disclosure applies to every read, including a previously generated row.
    if not composition_root().vendor_permits()(record):
        logger.info("overview not generated for record %s: disclosure gate", record.pk)
        return {"state": "unavailable", "overview": None}

    chunk_set = (
        ChunkSet.objects.filter(record=record, is_active=True)
        .select_related("record")
        .first()
    )
    if chunk_set is None:
        return {"state": "not_indexed", "overview": None}

    if _too_large(chunk_set):
        # Before assembly: an oversized paper costs nothing and stores nothing (IR-432).
        logger.info(
            "overview not generated for record %s: over AI_OVERVIEW_TOKEN_CEILING",
            record.pk,
        )
        return {"state": "unavailable", "overview": None, "reason": "too_large"}

    return _claim_generation(
        record.pk, chunk_set.pk, chunk_set.content_hash, retry_unavailable=retry
    )


def queue_overview_for_chunk_set(chunk_set_id: int) -> None:
    """Queue an overview after chunking, without doing generation in the worker."""
    chunk_set = (
        ChunkSet.objects.filter(pk=chunk_set_id, is_active=True)
        .select_related("record")
        .first()
    )
    if chunk_set is None or _too_large(chunk_set):
        return
    _claim_generation(chunk_set.record_id, chunk_set.pk, chunk_set.content_hash)


def _claim_generation(
    record_id: int,
    chunk_set_id: int,
    content_hash: str,
    *,
    retry_unavailable: bool = False,
) -> dict:
    """Persist one claim per record/hash/version, then publish after commit."""
    with transaction.atomic():
        # Locking the parent serializes the initial OneToOne row creation as
        # well as retries from multiple readers across application processes.
        record = Record.objects.select_for_update().get(pk=record_id)
        chunk_set = ChunkSet.objects.filter(
            pk=chunk_set_id,
            record_id=record_id,
            is_active=True,
            content_hash=content_hash,
        ).first()
        if chunk_set is None:
            active = ChunkSet.objects.filter(record_id=record_id, is_active=True).first()
            if active is None:
                return {"state": "not_indexed", "overview": None}
            chunk_set = active
            content_hash = active.content_hash

        stored = RecordOverview.objects.filter(record_id=record_id).first()
        is_current = (
            stored is not None
            and stored.content_hash == content_hash
            and stored.prompt_version == PROMPT_VERSION
        )
        if is_current and stored.state == "ready":
            return {"state": "ready", "overview": _wire(stored), "cached": True}
        if is_current and stored.state == "generating" and not _claim_expired(stored):
            return {"state": "generating", "overview": None}
        if is_current and stored.state == "unavailable" and not retry_unavailable:
            return {"state": "unavailable", "overview": None}

        # A failed generation is retried on an explicit request. The chunking
        # path also reaches this code, so a new chunk set is queued immediately.
        if stored is None:
            stored = RecordOverview(record=record)
        stored.state = "generating"
        stored.text = ""
        stored.citations = []
        stored.hook = ""
        stored.degraded = False
        stored.model_id = ""
        stored.content_hash = content_hash
        stored.prompt_version = PROMPT_VERSION
        stored.save()
        response = {"state": "generating", "overview": None}
        transaction.on_commit(
            lambda: _enqueue_overview(record_id, chunk_set.pk, content_hash)
        )
    return response


def _enqueue_overview(record_id: int, chunk_set_id: int, content_hash: str) -> None:
    from apps.ai.tasks import generate_record_overview

    try:
        generate_record_overview.delay(
            record_id, chunk_set_id, content_hash, PROMPT_VERSION
        )
    except Exception:
        # The claim is already committed when this callback runs. Mark it
        # unavailable so a broker outage cannot leave readers polling forever.
        logger.exception("could not queue overview generation for record %s", record_id)
        RecordOverview.objects.filter(
            record_id=record_id,
            state="generating",
            content_hash=content_hash,
            prompt_version=PROMPT_VERSION,
        ).update(state="unavailable", updated_at=timezone.now())


def generate_overview(record_id: int, chunk_set_id: int, content_hash: str, prompt_version: int) -> None:
    """Generate one claimed overview in the worker and fence the result."""
    if prompt_version != PROMPT_VERSION:
        return
    chunk_set = (
        ChunkSet.objects.filter(
            pk=chunk_set_id,
            record_id=record_id,
            is_active=True,
            content_hash=content_hash,
        )
        .select_related("record")
        .first()
    )
    if chunk_set is None:
        return
    claimed = RecordOverview.objects.filter(
        record_id=record_id,
        state="generating",
        content_hash=content_hash,
        prompt_version=prompt_version,
    )
    if not claimed.exists():
        return

    generated = None if _too_large(chunk_set) else _generate(chunk_set)
    if generated is None:
        claimed.update(state="unavailable")
        return

    text, wire_citations, model, hook = generated
    claimed.update(
        state="ready",
        text=text,
        hook=hook,
        citations=wire_citations,
        degraded=False,
        model_id=model or "",
        updated_at=timezone.now(),
    )


def _generate(chunk_set: ChunkSet):
    """``(text, citations, model, hook)``, or ``None`` when nothing was generated."""
    record = chunk_set.record
    root = composition_root()

    # Rechecked in the worker: the gate can change between claim and generation.
    if not root.vendor_permits()(record):
        logger.info("overview not generated for record %s: disclosure gate", record.pk)
        return None

    sources = whole_paper(chunk_set)
    if not sources:
        return None

    try:
        llm = root.llm_for(InferenceTask.SUMMARY)
    except LLMUnavailable:
        logger.info("overview not generated: LLM_SUMMARY_MODEL is not set")
        return None

    prompt = build_page_prompt(f"{record.title}. {_QUESTION}", sources)
    hook = ""

    def parse(raw, chunks):
        nonlocal hook
        body, hook = split_hook(raw)
        return parse_page_citations(body, chunks)

    generated = generate_cited(llm, prompt, sources, system=SYSTEM_PROMPT, parse=parse)
    if generated is None:
        return None
    text, citations = generated
    return text, citations_wire(citations), model_that_answered(llm), hook


def hook_for(record: Record) -> str | None:
    """The stored catalogue hook for a record the reader may see (IR-604).

    Reads the joined row and never generates; same disclosure gate as the overview.
    """
    try:
        stored = record.ai_overview
    except RecordOverview.DoesNotExist:
        return None
    if stored.state != "ready" or stored.prompt_version != PROMPT_VERSION or not stored.hook:
        return None
    if not composition_root().vendor_permits()(record):
        return None
    return stored.hook


def _wire(stored: RecordOverview) -> dict:
    return {
        "text": stored.text,
        "citations": stored.citations,
        "degraded": stored.degraded,
        "model": stored.model_id or None,
        "generated_at": stored.updated_at,
    }
