"""Memory: retrieval over a Conversation's own Turns (IR-297, ADR-026 Decision 6).

Recent Turns go into the answering prompt verbatim. Older ones are searched
rather than summarised or dropped, so a fact from Turn 2 is still usable at
Turn 50. A module, not a port, like `apps.ai.resolution` -- one
implementation, no vendor call, fully exercisable through HTTP.
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

        from apps.ai.models import TurnEmbedding

        rows = (
            TurnEmbedding.objects.filter(turn__conversation=conversation, space_id=space_id)
            .exclude(turn_id__in=list(exclude_ids))
            .select_related("turn")
            .annotate(distance=CosineDistance("embedding", query_vector))
        )
        cut_off = _max_distance()
        if cut_off > 0:
            rows = rows.filter(distance__lt=cut_off)
        return [row.turn for row in rows.order_by("distance")[: self._limit]]
