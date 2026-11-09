"""Reading a stored Turn back safely (IR-295, IR-299).

Django stopped writing Turns in IR-957; the AI runtime keeps its own
Conversations. What remains is reading the Turns Django wrote.

Reading is where the security lives. A stored citation is a pointer, so
reopening a transcript re-resolves each one now, against two things that may
have changed since it was written: whether the reader may still see the
Record (`visible_to(user)`), and whether the chunk it pointed at is still
live (re-chunking tombstones a chunk rather than deleting it, IR-115). A
citation into a Record the reader lost access to is dropped outright --
existence must not leak. A citation whose chunk was tombstoned degrades to a
record-level pointer instead: the Record is still there to link to, but the
text it once pointed at may no longer represent it.
"""
from __future__ import annotations

import logging
from typing import Optional


from apps.ai import public as public_protocol
from apps.ai.answers.citations import PARTIAL
from apps.ai.models import (
    Conversation,
    DocumentChunk,
    Turn,
)
from apps.ai.presentation import answer_body, answer_mode
from apps.ai.regions import normalized_regions, regions_wire
from apps.ai.grants.reads import research_records

logger = logging.getLogger(__name__)

def turns_for_reader(conversation: Conversation, user, *, public: bool = False) -> list[dict]:
    """The conversation's Turns, every citation re-resolved against ``user``.

    Two queries for the whole transcript, not one pair per citation: which
    cited Records the reader may still see, and which cited chunks are still
    live. Everything else -- dropping an invisible citation, degrading a
    tombstoned one -- is a lookup into those two results.
    """
    return _for_reader(
        list(conversation.turns.prefetch_related("citations")), user, public=public
    )


def turn_for_reader(turn: Turn, user, *, public: bool = False) -> dict:
    """One Turn, re-resolved exactly as a reopened transcript would show it.

    What a queued run's replayed `done` is built from (IR-544), so a reader
    who reconnects gets the permissions of now, not of when it was written.
    """
    turn = Turn.objects.prefetch_related("citations").get(pk=turn.pk)
    return _for_reader([turn], user, public=public)[0]


def _for_reader(turns: list, user, *, public: bool = False) -> list[dict]:
    """``public`` (IR-595) projects bodies through `apps.ai.public`; stored data is kept."""
    all_citations = [
        citation for turn in turns for citation in turn.citations.all()
    ]

    listed = {
        row["record_id"] for turn in turns
        for row in (*turn.listing.get("records", []), *turn.listing.get("candidates", []))
    }
    visible_titles = dict(
        research_records(user)
        .filter(pk__in={citation.record_id for citation in all_citations} | listed)
        .values_list("pk", "title")
    )
    # A candidate listing's quotes are checked against the text as it is now.
    listing_records = {
        record.pk: record
        for record in research_records(user).filter(pk__in=listed).only("title", "abstract")
    } if any("candidates" in turn.listing for turn in turns) else {}
    live_chunks = {
        chunk.pk: chunk
        for chunk in DocumentChunk.objects.filter(
            pk__in={
                citation.chunk_id
                for citation in all_citations
                if citation.chunk_id is not None
            },
            deleted_at__isnull=True,
            chunk_set__is_active=True,
        )
        # `page_sizes` lives on the chunk set, and regions are useless
        # without it (IR-334).
        .select_related("chunk_set")
        # Exactly the fields `_resolve_citation` reads. Deferred, not
        # excluded -- accessing anything else here fires a silent
        # per-instance query, so a field this helper starts reading must be
        # added here too.
        .only("content", "source_page", "context_path", "bboxes",
              "chunk_set__page_sizes")
    }

    bodies = [
        {
            **_listing_answer(
                answer_body(answer_mode(turn.state), turn.answer, preserve_no_results=bool(turn.routing)),
                turn, listing_records,
            ),
            "id": turn.pk,
            **_route_for_reader(turn, visible_titles, listing_records),
            "question": turn.question,
            "resolved_question": turn.resolved_question or None,
            "state": answer_mode(turn.state),
            "degraded": turn.degraded,
            "widened": turn.widened,
            "had_reasoning": turn.had_reasoning,
            # The working behind the answer (IR-381), for the collapsed panel
            # the transcript reopens with. `None` rather than `""` so a client
            # need not distinguish "no reasoning" from an empty string.
            "reasoning": turn.reasoning or None,
            # Kept alongside `state == "partial"` for clients that render the
            # fragment with a notice (IR-328/329, IR-458).
            "partial": turn.state == PARTIAL,
            "created_at": turn.created_at,
            "citations": [
                resolved
                for citation in turn.citations.all()
                if (
                    resolved := _resolve_citation(
                        citation, visible_titles, live_chunks
                    )
                )
                is not None
            ],
        }
        for turn in turns
    ]
    for turn, body in zip(turns, bodies):
        if not turn.comparison:
            continue
        from apps.ai.comparison.storage import reader_view

        comparison = reader_view(turn.comparison, user)
        if comparison is None:
            body.update(answer=None, message="The comparison sources changed or are no longer readable. Please compare again.",
                        citations=[], reasoning=None, state="unavailable", degraded=True)
        else:
            body["comparison"] = comparison
    if public:
        for turn, body in zip(turns, bodies):
            if any(c.record_id not in visible_titles for c in turn.citations.all()):
                # Removing the citation alone still exposes prose derived from it.
                body.update(answer=None, message="The answer sources are no longer readable.",
                            reasoning=None, state="unavailable", degraded=True,
                            question="", resolved_question=None)
                body.pop("comparison", None)
                body.pop("listing", None)
                continue
            # A degraded historical pointer proves access, not the version
            # that supported the analysis. Never revive its derived summary.
            current = all(c.chunk_id in live_chunks for c in turn.citations.all())
            summary = public_protocol.summary_for(turn, len(body["citations"])) if current else None
            if summary:
                body["reasoning_summary"] = summary
        return [public_protocol.project_turn(body) for body in bodies]
    return bodies


def _resolve_citation(citation, visible_titles, live_chunks) -> Optional[dict]:
    """One stored citation, re-resolved against what the reader may see now.

    ``None`` when the Record is no longer visible -- existence must not leak,
    so this is indistinguishable from a citation that was never stored at
    all. A record-level pointer (no ``text``, no ``record_title``) when the
    Record is visible but the chunk it pointed at was removed or superseded
    by a re-chunk: the text it once quoted may no longer represent the record, so
    showing it would be a stale quote rather than a re-resolved one.
    """
    if citation.record_id not in visible_titles:
        return None

    chunk = live_chunks.get(citation.chunk_id) if citation.chunk_id else None
    if chunk is None:
        return {
            "marker": citation.marker,
            "record_id": citation.record_id,
            "chunk_id": citation.chunk_id,
            "page": citation.page,
        }

    return {
        "marker": citation.marker,
        "chunk_id": citation.chunk_id,
        "record_id": citation.record_id,
        "record_title": visible_titles[citation.record_id],
        "page": chunk.source_page,
        "text": chunk.content,
        "context_path": list(chunk.context_path or ()),
        "regions": regions_wire(
            normalized_regions(chunk.bboxes, chunk.chunk_set.page_sizes)
        ),
    }


def _listing_answer(body: dict, turn, records) -> dict:
    """A candidate listing's answer is its wording, rebuilt so it counts only what this reader sees."""
    if "candidates" not in turn.listing:
        return body
    from apps.ai.stored_listing import reader_view

    wording = reader_view(turn.listing, records)["wording"]
    # The sentence is `answer` when something matched and `message` when not.
    return {key: wording if value == turn.answer else value for key, value in body.items()}


def _route_for_reader(turn, titles, records=None):
    metadata = {"routing": turn.routing} if turn.routing else {}
    if turn.research:
        # Steps and notes carry codes and counts only, so nothing to re-gate.
        metadata["research"] = turn.research
    if "candidates" in turn.listing:
        from apps.ai.stored_listing import reader_view

        metadata["listing"] = reader_view(turn.listing, records or {})
    elif turn.listing:
        metadata["listing"] = {**turn.listing, "records": [
            {"record_id": row["record_id"], "title": titles[row["record_id"]]}
            for row in turn.listing["records"] if row["record_id"] in titles
        ]}
    return metadata
