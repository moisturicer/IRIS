"""Turning retrieved passages into the shape the API already serves (IR-283).

This ticket is the **switch-over**, not the wire contract: Ask IRIS starts
answering from inside papers, and a citation still names a Record. Passage-
level citations -- the page and the quoted span -- are IR-284's.

So there is a gap to bridge. Retrieval now returns passages; the response the
interface renders is a list of record cards. One function bridges it, in one
place, so IR-284 has one thing to change rather than three views to find.

**The record lookup is keyed on ids retrieval already permitted.** It does not
re-derive visibility and must not: `TwoStageRetriever` narrowed the candidate
set with `visible_to(user)` before anything was scored, and a second predicate
here would be the drift ADR-014 rejected. Fetching a record by an id that
survived that filter is a join, not a decision.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from apps.ai.retrieval.ports import RetrievedChunk
from apps.records.models import Record


def _ranked_record_ids(passages: Sequence[RetrievedChunk]) -> list[int]:
    """The records behind ``passages``, best passage first, no duplicates.

    Retrieval returns passages in rank order, so first appearance *is* the
    record's rank: a record whose best passage came third outranks one whose
    best came ninth. Deduplicating any other way would reorder the answer's
    evidence against the ranking that produced it.
    """
    seen: list[int] = []
    for passage in passages:
        if passage.record_id not in seen:
            seen.append(passage.record_id)
    return seen


def record_sources(passages: Sequence[RetrievedChunk]) -> list[dict]:
    """Record cards for the passages retrieved, in rank order.

    ``score`` is the best score among that record's passages, because that is
    the passage the ranking actually put it there for; averaging would let a
    long record with one excellent passage sink below a short mediocre one.

    A record that vanished between retrieval and rendering is skipped rather
    than rendered hollow -- a card with no title reads as a broken result,
    and a deleted record is not a result at all.
    """
    ordered_ids = _ranked_record_ids(passages)
    best_score = {}
    for passage in passages:
        current = best_score.get(passage.record_id)
        if current is None or passage.score > current:
            best_score[passage.record_id] = passage.score

    records = (
        Record.objects.filter(pk__in=ordered_ids)
        .select_related("classification")
        .prefetch_related("authors")
        .in_bulk()
    )

    cards = []
    for record_id in ordered_ids:
        record = records.get(record_id)
        if record is None:
            continue
        cards.append(
            {
                "id": record.id,
                "title": record.title,
                "abstract": (record.abstract or "").strip(),
                "authors": ", ".join(a.name for a in record.authors.all())
                or "Institutional Author",
                "year": record.year_accomplished,
                "classification": (
                    record.classification.name if record.classification_id else None
                ),
                "score": round(float(best_score.get(record_id, 0.0)), 4),
            }
        )
    return cards


def cited_record_ids(citations: Iterable) -> list[int]:
    """The records the answer actually cited, in marker order, deduplicated.

    Distinct from ``record_sources``: the sources are everything the model was
    shown, and these are what it used. A reader checking a claim wants the
    second; a reader browsing what IRIS read wants the first, and collapsing
    them would quietly present unread sources as evidence.
    """
    ordered: list[int] = []
    for citation in citations:
        if citation.record_id not in ordered:
            ordered.append(citation.record_id)
    return ordered
