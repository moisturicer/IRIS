"""Memory: retrieval over a Conversation's own Turns (IR-297, ADR-026 Decision 6).

Recent Turns go into the answering prompt verbatim. Older ones are searched
rather than summarised or dropped, so a fact from Turn 2 is still usable at
Turn 50. A module, not a port, like `apps.ai.resolution` -- one
implementation, no vendor call, fully exercisable through HTTP.

**A Turn has two vectors since IR-447** -- its question and its answer, both
stored under the query input type precisely so this module stays one
``ORDER BY distance`` over one list (ADR-026 §7 as amended). What that costs
here is a de-duplication step: the ranking is over *vectors*, the result is
over *Turns*, and the two closest vectors in a Conversation can belong to the
same Turn.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Iterable, Optional, Sequence

from django.conf import settings
from pgvector.django import CosineDistance

if TYPE_CHECKING:
    from apps.ai.models import Conversation, Turn

logger = logging.getLogger(__name__)

#: How many older Turns a recall pulls in alongside the verbatim window.
MAX_RECALLED_TURNS = 4

#: Cosine distance beyond which a Turn is not relevant enough to recall
#: (IR-446). **Provisional**; the observed numbers it comes from, and the
#: setting that overrides it, are in `config/settings/base.py`.
DEFAULT_MAX_RECALL_DISTANCE = 0.80


def _max_distance() -> float:
    """The cut-off for this request. Non-positive disables it."""
    return float(
        getattr(settings, "AI_MEMORY_RECALL_MAX_DISTANCE", DEFAULT_MAX_RECALL_DISTANCE)
    )


class ConversationMemory:
    """Finds Turns from earlier in a Conversation relevant to the question
    just asked, using the vector already computed to search the corpus.

    Relevant, not merely closest: a Turn beyond the configured cosine
    distance is dropped, so the prompt never asserts relevance over the best
    of a bad set (IR-446).

    Found by question or by answer, whichever is closer (IR-447). A Turn is
    returned whole either way -- which vector reached it is a retrieval
    detail and never travels any further than this method.
    """

    def __init__(self, limit: int = MAX_RECALLED_TURNS) -> None:
        self._limit = limit

    def recall(
        self,
        conversation: "Conversation",
        query_vector: Optional[Sequence[float]],
        space_id: Optional[int],
        exclude_ids: Iterable[int] = (),
    ) -> list["Turn"]:
        """Older Turns from ``conversation``, ranked by relevance to
        ``query_vector``, and no further away than the cut-off. Returns
        ``[]`` -- degrading to the recent window the caller already has --
        when nothing is relevant enough, and likewise when there is no vector
        to compare against, logged rather than raised.
        """
        if query_vector is None or space_id is None:
            logger.warning(
                "conversation memory unavailable for conversation=%s: no "
                "query vector to recall against; degrading to recent Turns "
                "only",
                conversation.pk,
            )
            return []

        from apps.ai.models import VECTORS_PER_TURN, TurnEmbedding

        rows = (
            TurnEmbedding.objects.in_model_history()
            .filter(turn__conversation=conversation, space_id=space_id)
            .exclude(turn_id__in=list(exclude_ids))
            .select_related("turn")
            .annotate(distance=CosineDistance("embedding", query_vector))
        )
        cut_off = _max_distance()
        if cut_off > 0:
            rows = rows.filter(distance__lt=cut_off)

        # Slicing at `self._limit` would be the bug IR-447 introduces if it
        # were left alone: a Turn whose question *and* answer both rank well
        # would occupy two of the slots and silently shrink the recall to
        # three Turns. Taking `VECTORS_PER_TURN` times as many rows is enough
        # to guarantee `self._limit` distinct Turns whenever that many exist,
        # because that is the most rows any one Turn can contribute.
        ranked = rows.order_by("distance")[: self._limit * VECTORS_PER_TURN]

        # First occurrence wins, and the rows arrive nearest-first, so each
        # Turn is held at its *best* vector and the Turns come out ranked by
        # it. A dict because it preserves insertion order -- the ranking is
        # the return value, not an incidental property of it.
        best: dict[int, "Turn"] = {}
        for row in ranked:
            best.setdefault(row.turn_id, row.turn)
            if len(best) == self._limit:
                break
        return list(best.values())
