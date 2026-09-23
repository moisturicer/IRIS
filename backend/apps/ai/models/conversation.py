"""Conversations and the Turns they hold (IR-295, ADR-019).

Three tables replacing two field-less `pass` classes from migration 0001.
One Conversation model serves both chat surfaces (ADR-019); the divergences
from that ADR - `Turn` rather than `ChatMessage`, and `visible_to(user)`
rather than `publicly_visible()` - are recorded in ADR-019 itself.

A `TurnCitation` is a pointer: record, chunk, page, and no passage text.
Text frozen into a transcript outlives the permission that allowed it.
`chunk` is nullable because re-chunking replaces a record's chunk set.

No retention field and no expiry - a Conversation lives until its owner
deletes it (IR-294 Privacy).

`TurnEmbedding` (IR-297) stores the vector already computed to search the
corpus for a Turn's question. Keyed by turn and space together, like
`ChunkEmbedding`.
"""
from django.conf import settings
from django.db import models
from pgvector.django import HnswIndex, VectorField

from apps.ai.answers.citations import GENERATED, NO_SOURCES, PARTIAL, UNAVAILABLE

from .embedding_space import VECTOR_COLUMN_DIMENSIONS

#: `Turn.state`'s allowed values, from the same constants `record_turn`
#: already writes (migration 0013).
_STATE_CHOICES = [
    (GENERATED, "Generated"),
    (NO_SOURCES, "No sources"),
    (UNAVAILABLE, "Unavailable"),
    (PARTIAL, "Partial"),
]


class ConversationManager(models.Manager):
    def owned_by(self, user):
        """Every conversation query starts here - the whole privacy rule."""
        return (
            self.select_related("record")
            .filter(user=user)
            .annotate(turn_count=models.Count("turns"))
        )


class Conversation(models.Model):
    """One person's line of enquiry, optionally about one Record.

    `record` is what makes it a Paper Chat conversation, and it cascades:
    nothing about a withdrawn paper outlives the paper.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_conversations",
    )
    record = models.ForeignKey(
        "records.Record",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ai_conversations",
    )
    title = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ConversationManager()

    class Meta:
        ordering = ["-updated_at", "-id"]
        indexes = [models.Index(fields=["user", "-updated_at"])]

    def __str__(self) -> str:
        return f"Conversation({self.pk}, user={self.user_id}, record={self.record_id})"


class Turn(models.Model):
    """One question and the answer it produced.

    `state` is the wire's name for how the answer came out — generative, no
    results, the model was unreachable, or `partial` (IR-328, the stream
    never reached a `Done`) — stored rather than re-derived, because "no
    answer was written" and "the answer was empty" are different facts and
    a reopened transcript must not present the second as the first.

    `resolved_question` is blank unless resolution actually ran and changed
    something (IR-296, ADR-026) — skipped on the first Turn, skipped when the
    question carries no back-reference, and left blank on a failed model call,
    all three of which retrieve on `question` as written. Stored rather than
    re-derived because a wrong resolution silently changed what was asked, so
    it must be inspectable on replay rather than mysterious.

    `widened` is true only when this Turn belonged to a Record-scoped
    Conversation and the caller explicitly asked to search all papers instead
    (IR-298, ADR-026 §9). False for every Turn in an unscoped Conversation,
    since there was never a narrower scope to widen from. Stored rather than
    inferred from the citations a Turn happens to carry, because a widened
    question that still matched nothing outside its own paper would otherwise
    look identical to one that was never widened at all.

    `had_reasoning` is a structural fact, never the reasoning text itself
    (IR-327): whether the model produced any reasoning while answering this
    Turn, over the streaming path's dedicated channel or leaked into the text
    channel and caught there. Reasoning content is never stored -- only
    `answer_stream`'s narration ever sees it, and it is discarded once the
    stream ends.
    """

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="turns"
    )
    question = models.TextField()
    resolved_question = models.TextField(blank=True)
    answer = models.TextField(blank=True)
    state = models.CharField(max_length=20, choices=_STATE_CHOICES)
    degraded = models.BooleanField(default=False)
    widened = models.BooleanField(default=False)
    had_reasoning = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["conversation", "id"])]

    def __str__(self) -> str:
        return f"Turn({self.pk}, conversation={self.conversation_id})"


class TurnCitation(models.Model):
    """Where one citation in a stored answer pointed. No text, deliberately.

    `marker` is the number the answer text cites by.
    """

    turn = models.ForeignKey(
        Turn, on_delete=models.CASCADE, related_name="citations"
    )
    marker = models.PositiveSmallIntegerField()
    record = models.ForeignKey(
        "records.Record", on_delete=models.CASCADE, related_name="+"
    )
    chunk = models.ForeignKey(
        "ai.DocumentChunk",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    page = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["marker", "id"]

    def __str__(self) -> str:
        return f"TurnCitation(turn={self.turn_id}, marker={self.marker})"


class TurnEmbedding(models.Model):
    """A Turn's question, embedded under one embedding space.

    The vector `TwoStageRetriever` already computed to search the corpus,
    stored rather than discarded. Read by `apps.ai.memory`.
    """

    turn = models.ForeignKey(Turn, on_delete=models.CASCADE, related_name="embeddings")
    space = models.ForeignKey(
        "ai.EmbeddingSpace", on_delete=models.CASCADE, related_name="turn_embeddings"
    )
    embedding = VectorField(dimensions=VECTOR_COLUMN_DIMENSIONS)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["turn", "space"], name="unique_turn_embedding_per_space"
            ),
        ]
        indexes = [
            HnswIndex(
                name="turn_embedding_hnsw_idx",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self) -> str:
        return f"TurnEmbedding(turn={self.turn_id}, space={self.space_id})"
