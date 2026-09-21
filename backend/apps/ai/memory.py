"""Memory: retrieval over a Conversation's own Turns (IR-297, ADR-026 Decision 6).

Recent Turns go into the answering prompt verbatim. Older ones are searched
rather than summarised or dropped, so a fact from Turn 2 is still usable at
Turn 50. A module, not a port, like `apps.ai.resolution` -- one
implementation, no vendor call, fully exercisable through HTTP.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Iterable, Optional, Sequence

from pgvector.django import CosineDistance

if TYPE_CHECKING:
    from apps.ai.models import Conversation, Turn

logger = logging.getLogger(__name__)

#: How many older Turns a recall pulls in alongside the verbatim window.
MAX_RECALLED_TURNS = 4


class ConversationMemory:
    """Finds Turns from earlier in a Conversation relevant to the question
    just asked, using the vector already computed to search the corpus.
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
        ``query_vector``. Returns ``[]`` -- degrading to the recent window
        the caller already has -- when there is no vector to compare
        against, logged rather than raised.
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
            .order_by("distance")[: self._limit]
        )
        return [row.turn for row in rows]
