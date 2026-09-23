"""Writing a Turn down, and reading one back safely (IR-295, IR-299).

A module, not a port: one implementation, fully exercisable through HTTP.

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

from typing import Optional

from django.db import transaction

from apps.ai.answers.citations import PARTIAL, GroundedAnswer
from apps.ai.models import Conversation, DocumentChunk, Turn, TurnCitation, TurnEmbedding
from apps.ai.presentation import answer_body, answer_mode
from apps.records.models import Record

#: An unnamed conversation takes its name from the question that started it.
TITLE_LENGTH = 200


@transaction.atomic
def record_turn(
    conversation: Conversation,
    question: str,
    answer: GroundedAnswer,
    resolved_question: Optional[str] = None,
    widened: bool = False,
) -> Turn:
    """Append one Turn to ``conversation`` and return it.

    ``answer.text`` is stored whatever the state: in the unavailable case it
    is the explanation, not an answer, and ``state`` is what keeps the two
    apart on the way back out.

    The stored ``state`` is the **domain** one, not the wire's name for it.
    Persisting the wire string would mean renaming an API constant silently
    reinterprets rows written years earlier.

    ``resolved_question`` is ``None`` unless resolution ran and produced a
    standalone question (IR-296) — stored blank in every other case, which is
    the same fallback retrieval already took for that Turn.

    ``widened`` is true only when this Turn's Conversation is scoped to a
    Record and the caller asked to search all papers instead (IR-298). It is
    the caller's decision to record, not something re-derived from citations:
    a widened question that still matched nothing outside its own paper must
    still say it was widened.

    ``answer.had_reasoning`` (IR-327) is stored as the structural flag it is
    -- never the reasoning text, which `answer_stream` already discarded.
    """
    turn = Turn.objects.create(
        conversation=conversation,
        question=question,
        resolved_question=resolved_question or "",
        answer=answer.text or "",
        state=answer.state,
        degraded=answer.degraded,
        widened=widened,
        had_reasoning=answer.had_reasoning,
    )
    TurnCitation.objects.bulk_create(
        TurnCitation(
            turn=turn,
            marker=citation.marker,
            record_id=citation.record_id,
            chunk_id=citation.chunk_id,
            page=citation.source_page,
        )
        for citation in answer.citations
    )

    # The vector already computed to search the corpus (IR-297) -- no
    # second embedding call. `None` on a degraded, full-text answer.
    if answer.query_vector is not None and answer.embedding_space_id is not None:
        TurnEmbedding.objects.create(
            turn=turn,
            space_id=answer.embedding_space_id,
            embedding=answer.query_vector,
        )

    fields = ["updated_at"]
    if not conversation.title:
        conversation.title = question[:TITLE_LENGTH]
        fields.append("title")
    conversation.save(update_fields=fields)
    return turn


def turns_for_reader(conversation: Conversation, user) -> list[dict]:
    """The conversation's Turns, every citation re-resolved against ``user``.

    Two queries for the whole transcript, not one pair per citation: which
    cited Records the reader may still see, and which cited chunks are still
    live. Everything else -- dropping an invisible citation, degrading a
    tombstoned one -- is a lookup into those two results.
    """
    turns = list(conversation.turns.prefetch_related("citations"))
    all_citations = [
        citation for turn in turns for citation in turn.citations.all()
    ]

    visible_titles = dict(
        Record.objects.visible_to(user)
        .filter(pk__in={citation.record_id for citation in all_citations})
        .values_list("pk", "title")
    )
    live_chunks = {
        chunk.pk: chunk
        for chunk in DocumentChunk.objects.filter(
            pk__in={
                citation.chunk_id
                for citation in all_citations
                if citation.chunk_id is not None
            },
            deleted_at__isnull=True,
        # Exactly the fields `_resolve_citation` reads. Deferred, not
        # excluded -- accessing anything else here fires a silent
        # per-instance query, so a field this helper starts reading must be
        # added here too.
        ).only("content", "source_page", "context_path")
    }

    return [
        {
            **answer_body(answer_mode(turn.state), turn.answer),
            "id": turn.pk,
            "question": turn.question,
            "resolved_question": turn.resolved_question or None,
            "state": answer_mode(turn.state),
            "degraded": turn.degraded,
            "widened": turn.widened,
            "had_reasoning": turn.had_reasoning,
            # Orthogonal to `state` (stays "generative") -- a cut-off
            # stream is still an answer, not `unavailable` (IR-328/329).
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


def _resolve_citation(citation, visible_titles, live_chunks) -> Optional[dict]:
    """One stored citation, re-resolved against what the reader may see now.

    ``None`` when the Record is no longer visible -- existence must not leak,
    so this is indistinguishable from a citation that was never stored at
    all. A record-level pointer (no ``text``, no ``record_title``) when the
    Record is visible but the chunk it pointed at was tombstoned by a
    re-chunk: the text it once quoted may no longer represent the record, so
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
    }
