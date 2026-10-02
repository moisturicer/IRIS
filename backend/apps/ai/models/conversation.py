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

`TurnEmbedding` (IR-297) stores a Turn's vectors. Keyed by turn, space and
`kind` together -- two rows per Turn per space since IR-447: the question's
vector, which is the one retrieval already computed, and the answer's, which
is a real vendor call. ADR-026 §7 as amended.
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


#: What a `TurnEmbedding` is a vector *of* (IR-447, ADR-026 §7 as amended).
#:
#: Strings rather than an enum for the reason `_STATE_CHOICES` takes the same
#: shape: these are stored values, and a name is what is wanted when reading a
#: row back.
TURN_QUESTION_VECTOR = "question"
TURN_ANSWER_VECTOR = "answer"

_VECTOR_KIND_CHOICES = [
    (TURN_QUESTION_VECTOR, "Question"),
    (TURN_ANSWER_VECTOR, "Answer"),
]

#: How many vectors one Turn can hold in one space. `apps.ai.memory` reads
#: this to bound the rows it must scan to find N *distinct* Turns, so a third
#: kind added above widens that scan instead of silently truncating recall.
VECTORS_PER_TURN = len(_VECTOR_KIND_CHOICES)


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

    `reasoning` is the model's working, stored (IR-381) with the same
    lifetime as the Turn: no expiry of its own, gone when the Conversation is
    deleted. A separate column from `answer` because the two are separate
    channels and must stay that way -- nothing here was scanned for citation
    markers, and nothing here is an answer a reader may quote. Blank whenever
    no reasoning arrived, which includes every Turn from the non-streaming
    path and every task whose Profile has reasoning off.

    `had_reasoning` is the structural fact IR-327 stored while the text was
    still discarded: whether the model produced any reasoning at all, over
    the streaming path's dedicated channel or leaked into the text channel
    and caught there. Redundant now, and kept: a Turn written before IR-381
    has the flag and no text, so the flag is what keeps those apart from a
    Turn that never reasoned.
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
    reasoning = models.TextField(blank=True)
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
    """One vector of one Turn, under one embedding space.

    Two rows per Turn per space since IR-447 (ADR-026 §7 as amended), and
    `kind` is which is which:

    * ``question`` -- the vector `TwoStageRetriever` already computed to
      search the corpus, stored rather than discarded. Free.
    * ``answer`` -- the Turn's answer text, embedded on its own. A real
      vendor call on every Turn that has an answer.

    The second exists because indexing the question alone cannot find a Turn
    whose *answer* states a fact its question never named. The Turn is still
    returned whole; `apps.ai.memory` ranks both kinds in one list and either
    one can reach it.

    **Both kinds are embedded with `embed_query`**, answers included. That
    looks like an ADR-015 rule 3 violation and is not: recall is a single
    ``ORDER BY distance``, and storing answers as documents would put two
    non-comparable distance scales in it. The note under rule 3 records the
    choice, and ADR-026 names the two-ranked-list fallback should it measure
    badly.
    """

    turn = models.ForeignKey(Turn, on_delete=models.CASCADE, related_name="embeddings")
    space = models.ForeignKey(
        "ai.EmbeddingSpace", on_delete=models.CASCADE, related_name="turn_embeddings"
    )
    #: Defaults to ``question`` so every row written before IR-447 -- all of
    #: which were question vectors -- keeps its meaning without a data
    #: migration.
    kind = models.CharField(
        max_length=20, choices=_VECTOR_KIND_CHOICES, default=TURN_QUESTION_VECTOR
    )
    embedding = VectorField(dimensions=VECTOR_COLUMN_DIMENSIONS)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["turn", "space", "kind"],
                name="unique_turn_vector_per_space_and_kind",
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
        return (
            f"TurnEmbedding(turn={self.turn_id}, space={self.space_id}, "
            f"kind={self.kind})"
        )
