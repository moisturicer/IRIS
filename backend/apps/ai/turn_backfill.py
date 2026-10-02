"""Planning a backfill of Turn answer vectors (IR-447).

IR-447 gives a Turn a second vector, but only as it is written. Every Turn
already in the database keeps the one question vector it was stored with, so
a Conversation that predates the change is recalled by its questions alone --
correct, and worse than it needs to be. This module decides what filling that
gap would cost.

Separate from `apps/ai/backfill.py` on purpose, though it is shaped like it.
That module's unit is a Record and its question is "which active chunks have
no vector in this space"; this one's unit is a Turn and its question is
"which answered Turns have no *answer* vector in this space". Sharing a
planner would mean one function branching on which of two unrelated things it
was counting.

**Resumable and idempotent by construction, not by a checkpoint.** What a run
embeds is "Turns in this space's reach with an answer and no answer vector",
recomputed every time. A crash halfway resumes where it stopped, and a second
run over a finished set costs one query and no vendor call. There is
deliberately no bookkeeping that could itself be lost in the crash that made
it necessary -- the same reasoning `backfill_embeddings` records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

#: Only a `generated` Turn is worth a vector, for the reasons
#: `conversations._EMBEDDABLE_STATES` gives: the other states hold an
#: explanation or a half-written fragment, not an answer. Imported from there
#: rather than restated, so a state added to one is not missed by the other.
from apps.ai.conversations import _EMBEDDABLE_STATES


@dataclass(frozen=True)
class TurnPlan:
    """One Turn a run would embed, and what it would cost to."""

    turn_id: int
    conversation_id: int
    tokens: int


@dataclass
class TurnBackfillPlan:
    """What a backfill would do, before it does any of it."""

    space_id: int
    space_model: str
    cost_per_million: float
    considered: int = 0
    to_embed: list[TurnPlan] = field(default_factory=list)
    #: Turn counts by why they were passed over, for the report. A run that
    #: embeds nothing because everything already has a vector and a run that
    #: embeds nothing because every Turn was a refusal are different
    #: outcomes, and an operator has to be able to tell them apart.
    skipped: dict[str, int] = field(default_factory=dict)

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1

    @property
    def estimated_tokens(self) -> int:
        return sum(plan.tokens for plan in self.to_embed)

    @property
    def estimated_cost(self) -> float:
        return self.estimated_tokens / 1_000_000 * self.cost_per_million

    def exceeds(self, ceiling: int) -> bool:
        """Whether this plan is refused. A ceiling of 0 or less disables the
        guard, the same escape hatch `AI_EMBEDDING_TOKEN_CEILING` gives."""
        return ceiling > 0 and self.estimated_tokens > ceiling


def turns_to_consider(conversation_ids: Optional[Sequence[int]] = None):
    """The Turns a run walks, oldest first.

    Deterministic ordering is what makes ``--limit`` mean anything across two
    invocations -- an unordered queryset would hand the second run a
    different slice and call it a resume.
    """
    from apps.ai.models import Turn

    queryset = Turn.objects.all().order_by("pk")
    if conversation_ids:
        queryset = queryset.filter(conversation_id__in=list(conversation_ids))
    return queryset


def plan_turns(turns, *, space_id: int, space_model: str, cost_per_million: float):
    """Cost a backfill without sending anything.

    The token count is the same estimator the chunker uses, so the number an
    operator is shown and the number a run actually spends cannot drift apart.
    """
    from apps.ai.chunking.tokens import count_tokens
    from apps.ai.models import TURN_ANSWER_VECTOR, TurnEmbedding

    plan = TurnBackfillPlan(
        space_id=space_id, space_model=space_model, cost_per_million=cost_per_million
    )

    # One query for the whole set rather than one per Turn: the "already has
    # a vector" test is what makes a re-run cheap, and doing it per Turn would
    # make the resume itself the expensive part.
    already = set(
        TurnEmbedding.objects.filter(
            space_id=space_id, kind=TURN_ANSWER_VECTOR
        ).values_list("turn_id", flat=True)
    )

    for turn in turns:
        plan.considered += 1
        if turn.state not in _EMBEDDABLE_STATES:
            plan.skip(f"state is {turn.state}, not an answer")
        elif not (turn.answer or "").strip():
            plan.skip("no answer text")
        elif turn.pk in already:
            plan.skip("already has an answer vector in this space")
        else:
            plan.to_embed.append(
                TurnPlan(
                    turn_id=turn.pk,
                    conversation_id=turn.conversation_id,
                    tokens=count_tokens(turn.answer),
                )
            )
    return plan


@dataclass
class TurnRunReport:
    """What a run actually did, accumulated as it goes.

    Mutable and appended to per Turn, because a resumable run has to be
    meaningful when it stops halfway -- a value assembled at the end would
    exist only on the path where nothing went wrong.
    """

    embedded: int = 0
    failed: list[tuple[int, str]] = field(default_factory=list)

    def record_failure(self, turn_id: int, error: Exception) -> None:
        self.failed.append((turn_id, str(error)))


def embed_turn_answer(turn, *, space_id: int, embedder) -> None:
    """Store one Turn's answer vector, overwriting any row already there.

    `embed_query`, not `embed_documents`, for the reason ADR-015 rule 3's note
    records and `TurnEmbedding` restates: recall is one ranked list, and an
    answer stored as a document would put a second, non-comparable distance
    scale into it.
    """
    from apps.ai.models import TURN_ANSWER_VECTOR, TurnEmbedding

    vector = embedder.embed_query(turn.answer)
    TurnEmbedding.objects.update_or_create(
        turn=turn,
        space_id=space_id,
        kind=TURN_ANSWER_VECTOR,
        defaults={"embedding": vector},
    )
