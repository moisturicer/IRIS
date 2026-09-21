"""Writing a Turn down, and reading one back safely (IR-295).

A module, not a port: one implementation, fully exercisable through HTTP.

Reading is where the security lives. A stored citation is a pointer, so
reopening a transcript resolves those pointers now, against
`visible_to(user)`. One into a Record the reader lost access to is dropped.
IR-299 turns the dropped case into a record-level link with a re-resolved
quote; dropping is the fail-closed version of the same rule.
"""
from __future__ import annotations

from django.db import transaction

from apps.ai.answers.citations import GroundedAnswer
from apps.ai.models import Conversation, Turn, TurnCitation
from apps.ai.presentation import answer_body, answer_mode
from apps.records.models import Record

#: An unnamed conversation takes its name from the question that started it.
TITLE_LENGTH = 200


@transaction.atomic
def record_turn(
    conversation: Conversation, question: str, answer: GroundedAnswer
) -> Turn:
    """Append one Turn to ``conversation`` and return it.

    ``answer.text`` is stored whatever the state: in the unavailable case it
    is the explanation, not an answer, and ``state`` is what keeps the two
    apart on the way back out.

    The stored ``state`` is the **domain** one, not the wire's name for it.
    Persisting the wire string would mean renaming an API constant silently
    reinterprets rows written years earlier.
    """
    turn = Turn.objects.create(
        conversation=conversation,
        question=question,
        answer=answer.text or "",
        state=answer.state,
        degraded=answer.degraded,
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

    fields = ["updated_at"]
    if not conversation.title:
        conversation.title = question[:TITLE_LENGTH]
        fields.append("title")
    conversation.save(update_fields=fields)
    return turn


def turns_for_reader(conversation: Conversation, user) -> list[dict]:
    """The conversation's Turns, every citation re-checked against ``user``.

    One visibility query for the whole transcript, not one per citation.
    """
    turns = list(conversation.turns.prefetch_related("citations"))
    cited_record_ids = {
        citation.record_id for turn in turns for citation in turn.citations.all()
    }
    visible = set(
        Record.objects.visible_to(user)
        .filter(pk__in=cited_record_ids)
        .values_list("pk", flat=True)
    )

    return [
        {
            **answer_body(answer_mode(turn.state), turn.answer),
            "id": turn.pk,
            "question": turn.question,
            "state": answer_mode(turn.state),
            "degraded": turn.degraded,
            "created_at": turn.created_at,
            "citations": [
                {
                    "marker": citation.marker,
                    "record_id": citation.record_id,
                    "chunk_id": citation.chunk_id,
                    "page": citation.page,
                }
                for citation in turn.citations.all()
                if citation.record_id in visible
            ],
        }
        for turn in turns
    ]
