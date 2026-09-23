"""Generating a record's AI Overview once, and reading it back (IR-334).

The overview used to be an ordinary `/ai/ask/` call fired from the paper view
on every mount, unscoped to the record being read. Two things were wrong with
that: the vendor was paid on every page view for an answer that cannot change,
and a corpus-wide search for "summarise this paper" can answer from a
different paper that happens to match the title.

So: scoped to the record, generated once, stored, and invalidated only by the
thing that can actually change the answer — a re-chunk of the record, or a
change to the prompt here.
"""

from __future__ import annotations

import logging
from typing import Optional

from apps.ai.composition import composition_root
from apps.ai.models import ChunkSet, RecordOverview
from apps.ai.presentation import citations as citations_wire
from apps.records.models import Record

logger = logging.getLogger(__name__)

#: Bumped whenever the question below changes. A stored row generated under an
#: older version is stale by definition, however fresh its chunks are.
PROMPT_VERSION = 1

#: How many passages ground an overview. Small deliberately: this is a summary
#: of one paper, not a survey, and every passage above it is prompt cost.
OVERVIEW_TOP_K = 6

_QUESTION = (
    "Summarise this work for a reader deciding whether to read it: its "
    "research objectives, the methodology it used, and its key findings. "
    "Write it as flowing prose in two or three short paragraphs."
)


def _active_content_hash(record: Record) -> Optional[str]:
    """The hash of the record's active chunk set, or ``None`` if it has none.

    No chunk set means nothing was ever extracted from this record, so there
    is nothing to summarise and nothing to key a cache on.
    """
    return (
        ChunkSet.objects.filter(record=record, is_active=True)
        .values_list("content_hash", flat=True)
        .first()
    )


def _fresh(overview: RecordOverview, content_hash: str) -> bool:
    return (
        overview.content_hash == content_hash
        and overview.prompt_version == PROMPT_VERSION
    )


def overview_for(record: Record, user) -> dict:
    """The record's overview, generated only if there is not a current one.

    ``user`` is passed through to retrieval rather than used to key the cache.
    One row serves every reader because every passage in it comes from this
    record, which the caller has already been permitted to open — there is no
    narrower view of it a second reader could need. Retrieval still applies
    ``visible_to`` internally, so a reader who lost access mid-request gets
    nothing rather than a cached quote.
    """
    content_hash = _active_content_hash(record)
    if content_hash is None:
        return {"state": "not_indexed", "overview": None}

    stored = RecordOverview.objects.filter(record=record).first()
    if stored is not None and _fresh(stored, content_hash):
        return {"state": "ready", "overview": _wire(stored), "cached": True}

    generated = _generate(record, user)
    if generated is None:
        # An unavailable model is a condition that passes. Storing it would
        # keep the paper blank long after the vendor came back.
        return {"state": "unavailable", "overview": None}

    answer, wire_citations = generated
    stored, _ = RecordOverview.objects.update_or_create(
        record=record,
        defaults={
            "text": answer.text,
            "citations": wire_citations,
            "degraded": answer.degraded,
            "model_id": answer.model or "",
            "content_hash": content_hash,
            "prompt_version": PROMPT_VERSION,
        },
    )
    return {"state": "ready", "overview": _wire(stored), "cached": False}


def _generate(record: Record, user):
    """One scoped answer, or ``None`` when it was not a generative one."""
    from apps.ai.answers.citations import GENERATED

    service = composition_root().answer_service(
        max_sources=OVERVIEW_TOP_K, record=record
    )
    answer = service.answer(f"{record.title}. {_QUESTION}", user)
    if answer.state != GENERATED or not answer.text:
        logger.info(
            "overview not generated for record %s: state=%s",
            record.pk,
            answer.state,
        )
        return None

    # Scoped retrieval should only ever return this record's passages; a
    # citation into another record would mean the scope leaked, and the
    # overview is not the place to find that out.
    wire = [
        item
        for item in citations_wire(answer.citations)
        if item["record_id"] == record.pk
    ]
    return answer, wire


def _wire(stored: RecordOverview) -> dict:
    return {
        "text": stored.text,
        "citations": stored.citations,
        "degraded": stored.degraded,
        "model": stored.model_id or None,
        "generated_at": stored.updated_at,
    }
