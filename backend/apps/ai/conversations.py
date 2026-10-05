"""Writing a Turn down, and reading one back safely (IR-295, IR-299).

A module, not a port: one implementation, fully exercisable through HTTP.

Writing a Turn is two steps since IR-447, deliberately not one. The Turn and
its citations go down in one transaction; the answer's memory vector is a
vendor call and happens *after* that transaction commits. A Turn that is
written and then fails to embed is a Turn with weaker recall. A Turn rolled
back because a vendor was down is a lost answer the reader already read.

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

from django.conf import settings
from django.db import transaction

from apps.ai.answers.citations import PARTIAL, GroundedAnswer
from apps.ai.models import (
    MODEL_HISTORY_STATES,
    TURN_ANSWER_VECTOR,
    TURN_QUESTION_VECTOR,
    Conversation,
    DocumentChunk,
    Turn,
    TurnCitation,
    TurnEmbedding,
)
from apps.ai.presentation import answer_body, answer_mode
from apps.ai.regions import normalized_regions, regions_wire
from apps.records.models import Record

logger = logging.getLogger(__name__)

#: An unnamed conversation takes its name from the question that started it.
TITLE_LENGTH = 200

#: The one state whose `text` is an answer somebody could later ask about,
#: and so the only one worth embedding (IR-447).
#:
#: `GroundedAnswer.text` is populated in every state, and in the other three
#: it is not content. `no_sources` and `unavailable` hold an *explanation* --
#: "nothing was found", "no model was reachable". `partial` holds a
#: fragment: the stream died before its `Done` (IR-328), so the text stops
#: mid-thought and a vector over it describes a sentence that was never
#: finished.
#:
#: Embedding any of them would spend a vendor call per failure to make
#: failures findable, which is the exact opposite of what IR-448 is for --
#: it exists to keep refused and failed Turns *out* of the model's history,
#: and indexing them here would be building the retrieval path that puts
#: them back.
#:
#: **It is that same predicate** as of IR-448, not a second set that happens
#: to agree: `MODEL_HISTORY_STATES` is the states a model may be shown, and
#: embedding a Turn exists only to let a model be shown it later. Two
#: independent frozensets would be free to drift into a state that is
#: embedded and then filtered out of every prompt -- a vendor call per
#: failure, buying nothing.
_EMBEDDABLE_STATES = MODEL_HISTORY_STATES


def record_turn(
    conversation: Conversation,
    question: str,
    answer: GroundedAnswer,
    resolved_question: Optional[str] = None,
    widened: bool = False,
    embedder=None,
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

    ``answer.reasoning`` (IR-381) is stored as its own column, never folded
    into ``answer``: the two arrived on separate channels and a reopened
    transcript must keep them apart. ``answer.had_reasoning`` (IR-327) is
    stored beside it, redundant and kept -- see `Turn`.

    ``embedder`` embeds the answer for memory recall (IR-447). It defaults to
    the composition root's, and is a parameter so a test can drive this path
    with a fake and count the calls. The call is made **after** the Turn is
    committed and its failure is logged rather than raised -- see the module
    docstring for why that order is not an accident.
    """
    turn = _write_turn(
        conversation, question, answer, resolved_question, widened
    )
    _store_answer_vector(turn, answer, embedder)
    return turn


@transaction.atomic
def _write_turn(
    conversation: Conversation,
    question: str,
    answer: GroundedAnswer,
    resolved_question: Optional[str],
    widened: bool,
) -> Turn:
    """The Turn, its citations and its free question vector, all or nothing.

    Everything here is local: no vendor call belongs inside this transaction.
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
        reasoning=answer.reasoning,
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
            kind=TURN_QUESTION_VECTOR,
        )

    fields = ["updated_at"]
    if not conversation.title:
        conversation.title = question[:TITLE_LENGTH]
        fields.append("title")
    conversation.save(update_fields=fields)
    return turn


def _answer_vector_enabled() -> bool:
    """Whether a Turn's answer is embedded at all.

    Read per call, not bound at import: a harness run flips it with
    `override_settings` between two otherwise identical configurations, which
    is the comparison ADR-023 requires before this stops being provisional.
    """
    return bool(getattr(settings, "AI_MEMORY_ANSWER_VECTOR_ENABLED", True))


def _store_answer_vector(turn: Turn, answer: GroundedAnswer, embedder) -> None:
    """Embed ``turn``'s answer and store it as a second memory vector.

    The vector that makes a Turn findable by what it *said* rather than only
    by what was asked (IR-447, ADR-026 §7 as amended). Indexing the question
    alone cannot recall a Turn whose answer states a fact the question never
    named.

    Four reasons to store nothing, all of them normal:

    * the switch is off;
    * there is no embedding space -- a degraded, full-text answer has no
      vector of any kind, exactly as the question vector above;
    * the state is not one whose text is an answer (see
      `_EMBEDDABLE_STATES`), or the text is blank;
    * the embedding call failed.

    Only the last is a problem, and it is still not this function's to
    raise. The Turn is committed by now and the reader has already read the
    answer; the cost of a failure here is that one Turn is recalled by its
    question alone, which is what every Turn written before IR-447 does. So
    it is logged at warning and swallowed. Letting it propagate would turn a
    vendor blip into a 500 on a request that had already succeeded.
    """
    if not _answer_vector_enabled():
        return
    if answer.embedding_space_id is None:
        return
    if answer.state not in _EMBEDDABLE_STATES:
        return

    text = (answer.text or "").strip()
    if not text:
        return

    if embedder is None:
        from apps.ai.composition import composition_root

        embedder = composition_root().embedder()

    try:
        # `embed_query`, not `embed_documents`, for stored answer text. This
        # is ADR-015 rule 3's documented exception, not an oversight -- see
        # `TurnEmbedding`.
        vector = embedder.embed_query(text)
    except Exception:
        logger.warning(
            "could not embed the answer of turn=%s for conversation=%s; it "
            "will be recalled by its question alone",
            turn.pk,
            turn.conversation_id,
            exc_info=True,
        )
        return

    # `update_or_create`, not `create`: a collision on
    # `unique_turn_vector_per_space_and_kind` here would raise *after* the
    # reader has already been served their answer, turning a duplicate write
    # into a 500 on a request that succeeded. Idempotent is the safer shape
    # for a step that runs outside the transaction above.
    TurnEmbedding.objects.update_or_create(
        turn=turn,
        space_id=answer.embedding_space_id,
        kind=TURN_ANSWER_VECTOR,
        defaults={"embedding": vector},
    )


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
        "regions": regions_wire(
            normalized_regions(chunk.bboxes, chunk.chunk_set.page_sizes)
        ),
    }
