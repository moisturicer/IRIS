"""EmbeddingSpace: the single source of truth for what produced a vector.

Before this model existed, the embedding dimension was declared in two
places that could silently disagree: ``settings.AI_EMBEDDING_DIMENSIONS``
(read by the model) and a literal ``1536`` hardcoded in migration 0002. A
mismatch there does not raise — it returns rows, ranked plausibly, and
wrong.

ADR-015 calls the hardcoded dimension a one-way door: retrofitting this
model after real vectors exist is exactly the destructive migration this
model exists to make unnecessary. After this, both the indexing path and
the (not yet built) query path read the active space from one place —
``get_active_embedding_space()`` — instead of each trusting its own copy of
the model id and dimension.
"""

from django.core.exceptions import ImproperlyConfigured
from django.db import models


class EmbeddingSpaceState(models.TextChoices):
    ACTIVE = "active", "Active"
    RETIRED = "retired", "Retired"
    PENDING = "pending", "Pending"


class EmbeddingSpace(models.Model):
    """One (model_id, dimensions, metric) combination a vector can belong to.

    Changing embedding model is a data change — insert a new space, flip
    which one is active — rather than a destructive re-index. The state
    machine is intentionally small: a space is ``pending`` while a backfill
    is in flight, becomes ``active`` when it is the one live queries read,
    and ``retired`` once superseded. Nothing here promotes a space
    automatically; that is an operational decision, not a migration.
    """

    model_id = models.CharField(max_length=200)
    dimensions = models.PositiveIntegerField()
    metric = models.CharField(max_length=20, default="cosine")
    state = models.CharField(
        max_length=10,
        choices=EmbeddingSpaceState.choices,
        default=EmbeddingSpaceState.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Enforced by the database, not by application code that can be
            # bypassed: at most one row may carry state="active" at a time.
            models.UniqueConstraint(
                fields=["state"],
                condition=models.Q(state=EmbeddingSpaceState.ACTIVE),
                name="one_active_embedding_space",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.model_id} ({self.dimensions}d, {self.metric}, {self.state})"


def get_active_embedding_space() -> EmbeddingSpace:
    """The one active ``EmbeddingSpace``, or a loud, specific failure.

    Raises rather than falling back to a default: an indexing or query path
    that cannot name its embedding space must not proceed as if nothing
    were wrong — that is exactly the class of silent-disagreement bug this
    model exists to close off.
    """
    try:
        return EmbeddingSpace.objects.get(state=EmbeddingSpaceState.ACTIVE)
    except EmbeddingSpace.DoesNotExist:
        raise ImproperlyConfigured(
            "No active EmbeddingSpace is configured. Indexing and query "
            "both need exactly one active row to know what model produced "
            "a vector and at what dimension."
        ) from None
    except EmbeddingSpace.MultipleObjectsReturned:
        # Guarded against by the partial unique constraint above; this is a
        # defensive backstop, not an expected path.
        raise ImproperlyConfigured(
            "More than one EmbeddingSpace is active. The database "
            "constraint that should prevent this has been bypassed."
        ) from None


def assert_embedding_space_consistent(dimensions: int, *, context: str) -> None:
    """Fail loudly when a caller's own dimension disagrees with the active
    space's.

    ``dimensions`` is the value a caller is *about* to act on — the
    dimension baked into a ``VectorField`` it is writing through, or one it
    is about to construct a query against. ``context`` names which path is
    calling (``"indexing"`` or ``"query"``), so the error identifies which
    side drifted rather than just that something, somewhere, disagreed.

    This is the startup assertion ADR-015 asks for: called once by each
    path before it does real work, so a drift between the active space and
    what a path actually writes or queries is a startup failure, not wrong
    answers ranked plausibly.
    """
    active = get_active_embedding_space()
    if active.dimensions != dimensions:
        raise ImproperlyConfigured(
            f"EmbeddingSpace mismatch in the {context} path: the active "
            f"space {active.model_id!r} is {active.dimensions} dimensions, "
            f"but this path is configured for {dimensions}. Indexing and "
            f"query must agree on the active space."
        )
