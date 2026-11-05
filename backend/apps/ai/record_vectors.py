"""The one way a reader reaches Record-level summary vectors (IR-739, ADR-049 §23).

``RecordEmbedding`` holds one vector per Record with no space key, so it cannot
say which Embedding Space a vector belongs to; once a second space can go live
that is exactly the mixing ADR-049 §23 forbids. Every reader therefore asks for
``(record, space)`` rows by naming a space, through here, and the passage side
already does (``ChunkEmbedding.space``). Promotion changes which space is
active; it never rewrites a vector, so flipping that one row moves Record and
Passage readers together and a rollback is the same flip back.

A reader resolves the space **once per request** and uses that same space for
its Record stage and its Passage stage, so a promotion committing in the middle
of a request cannot give it a Record vector from one space and a Passage vector
from another.
"""

from __future__ import annotations

from typing import Optional

from apps.ai.models.embedding import RecordSpaceEmbedding
from apps.ai.models.embedding_space import EmbeddingSpace, EmbeddingSpaceState


def active_space() -> Optional[EmbeddingSpace]:
    """The active space, or ``None`` when nothing was ever indexed under one."""
    return EmbeddingSpace.objects.filter(state=EmbeddingSpaceState.ACTIVE).first()


def record_vectors(space: Optional[EmbeddingSpace]):
    """Summary vectors stored under ``space``; an empty queryset without one."""
    if space is None:
        return RecordSpaceEmbedding.objects.none()
    return RecordSpaceEmbedding.objects.filter(space_id=space.pk)
