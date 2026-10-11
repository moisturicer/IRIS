"""A record's AI Overview: generated once from the whole paper, then stored.

Invalidated by a re-chunk or a ``PROMPT_VERSION`` bump. Runs as the
``summary`` task, off until ``LLM_SUMMARY_MODEL`` is set (IR-380).
"""

from __future__ import annotations

import logging

from apps.ai.answers.citations import build_prompt
from apps.ai.answers.service import generate_cited, model_that_answered
from apps.ai.composition import composition_root
from apps.ai.inference import InferenceTask
from apps.ai.models import ChunkSet, RecordOverview
from apps.ai.presentation import citations as citations_wire
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.records.models import Record

from .assembly import whole_paper

logger = logging.getLogger(__name__)

#: 2: grounded in the whole paper, not six retrieved passages (IR-431).
PROMPT_VERSION = 2

_QUESTION = (
    "Summarise this work for a reader deciding whether to read it: its "
    "research objectives, the methodology it used, and its key findings. "
    "Write it as flowing prose in two or three short paragraphs."
)


def overview_for(record: Record) -> dict:
    """The record's overview; one stored row serves every reader."""
    chunk_set = (
        ChunkSet.objects.filter(record=record, is_active=True)
        .select_related("record")
        .first()
    )
    if chunk_set is None:
        return {"state": "not_indexed", "overview": None}

    stored = RecordOverview.objects.filter(record=record).first()
    if (
        stored is not None
        and stored.content_hash == chunk_set.content_hash
        and stored.prompt_version == PROMPT_VERSION
    ):
        return {"state": "ready", "overview": _wire(stored), "cached": True}

    generated = _generate(chunk_set)
    if generated is None:
        # Not stored, so the next view tries again.
        return {"state": "unavailable", "overview": None}

    text, wire_citations, model = generated
    stored, _ = RecordOverview.objects.update_or_create(
        record=record,
        defaults={
            "text": text,
            "citations": wire_citations,
            "degraded": False,
            "model_id": model or "",
            "content_hash": chunk_set.content_hash,
            "prompt_version": PROMPT_VERSION,
        },
    )
    return {"state": "ready", "overview": _wire(stored), "cached": False}


def _generate(chunk_set: ChunkSet):
    """``(text, citations, model)``, or ``None`` when nothing was generated."""
    record = chunk_set.record
    root = composition_root()

    # Before assembly: every chunk is content sent to a vendor.
    permits = root.vendor_permits()
    if not permits(record):
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

    prompt = build_prompt(f"{record.title}. {_QUESTION}", sources)
    generated = generate_cited(llm, prompt, sources)
    if generated is None:
        return None
    text, citations = generated
    return text, citations_wire(citations), model_that_answered(llm)


def _wire(stored: RecordOverview) -> dict:
    return {
        "text": stored.text,
        "citations": stored.citations,
        "degraded": stored.degraded,
        "model": stored.model_id or None,
        "generated_at": stored.updated_at,
    }
