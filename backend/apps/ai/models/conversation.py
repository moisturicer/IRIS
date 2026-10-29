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


#: The only `Turn.state` whose text a model may be shown (IR-448, ADR-026 §13).
#:
#: A Turn that failed (`unavailable` -- no model was reachable, ADR-008) or
#: that refused (`no_sources` -- nothing readable was found) holds an
#: *explanation* in `answer`, not an answer. `partial` holds a fragment: the
#: stream died before its `Done` (IR-328), so the text stops mid-sentence.
#:
#: None of the three carries content a later question could need, and leaving
#: one in the prompt is actively harmful: a refusal shown as a prior answer is
#: a demonstration of refusing, and the rewriter of ADR-026 §1 is asked to
#: resolve a follow-up against text that says nothing about the subject.
#: ADR-026 §13 rejected mitigating that, because excluding it is cheaper.
#:
#: **This filters the model's view only.** `conversations.turns_for_reader` is
#: deliberately not filtered -- a reader who could not see their own failed
#: question would be more confused, not less. The asymmetry is the decision.
MODEL_HISTORY_STATES = frozenset({GENERATED})


def model_history_q(prefix: str = "") -> models.Q:
    """The IR-448 predicate itself, once, for any path reaching a `Turn`.

    ``prefix`` is the relation to traverse first -- ``""`` on a `Turn`
    queryset, ``"turn__"`` on a `TurnEmbedding` one. A `Q` rather than a
    second `filter(state__in=...)` per call site because the two paths this
    gates (`views.chatbot._recent_turns` and
    `memory.ConversationMemory.recall`) must not be able to drift: adding a
    state here changes both or neither.

    A `Q` rather than a subquery on purpose, too. ``turn__in=Turn.objects
    .in_model_history()`` would read as the stronger reuse and would make
    Postgres semi-join the whole `Turn` table to answer a question about one
    Conversation's rows.
    """
    # Missing JSON keys must be admitted explicitly: SQL NOT(NULL) is NULL.
    # Aggregate Turns lack full permission provenance for model-history reuse.
    return models.Q(**{f"{prefix}state__in": MODEL_HISTORY_STATES}) & (
        models.Q(**{f"{prefix}routing__lane__isnull": True})
        | ~models.Q(**{f"{prefix}routing__lane__in": ["listing", "count", "comparison"]})
    )


class TurnQuerySet(models.QuerySet):
    """Turns, with the IR-448 predicate reachable.

    A queryset method rather than a free function because both callers reach
    Turns through the ORM, so the predicate rides on the query.
    """

    def in_model_history(self):
        """Turns whose text may go into a prompt. See `MODEL_HISTORY_STATES`."""
        return self.filter(model_history_q())


class TurnEmbeddingQuerySet(models.QuerySet):
    """Vectors of Turns, with the same one predicate reachable (IR-448)."""

    def in_model_history(self):
        """Rows whose Turn may be recalled into a prompt."""
        return self.filter(model_history_q("turn__"))


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
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ConversationManager()

    class Meta:
        ordering = ["-updated_at", "-id"]
        indexes = [models.Index(fields=["user", "-updated_at"])]
        constraints = [
            models.UniqueConstraint(fields=["user", "record"], condition=models.Q(is_default=True),
                                    name="unique_default_paper_conversation"),
            models.CheckConstraint(condition=models.Q(is_default=False) | models.Q(record__isnull=False),
                                   name="default_conversation_has_record"),
        ]

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
    #: The validated display summary (IR-595): never evidence, never raw
    #: reasoning. Same lifetime as the Turn; blank when none was safe.
    reasoning_summary = models.TextField(blank=True)
    #: Where it came from: "<engine>/<answer prompt version>".
    reasoning_summary_source = models.CharField(max_length=60, blank=True)
    routing = models.JSONField(default=dict, blank=True)
    listing = models.JSONField(default=dict, blank=True)
    comparison = models.JSONField(default=dict, blank=True)
    #: The research planner's steps and coverage notes (IR-504), never content.
    research = models.JSONField(default=dict, blank=True)
    #: The `ConversationState` revision this Turn committed; null when it
    #: was not delivered or predates IR-592.
    context_revision = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TurnQuerySet.as_manager()

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["conversation", "id"])]

    def __str__(self) -> str:
        return f"Turn({self.pk}, conversation={self.conversation_id})"


class ChatSubmission(models.Model):
    """A committed claim before any paid work (IR-561). Never auto-reclaimed.

    An interrupted process may already have called a vendor. Keeping the claim
    prevents a transport retry from paying twice, even when no Turn was saved.
    """

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="submissions")
    request_id = models.UUIDField()
    fingerprint = models.CharField(max_length=64)
    turn = models.OneToOneField(Turn, on_delete=models.CASCADE, null=True, blank=True, related_name="submission")
    run = models.OneToOneField("ai.AskRun", on_delete=models.CASCADE, null=True, blank=True, related_name="submission")
    finished = models.BooleanField(default=False)
    source_refs = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["conversation", "request_id"],
                                               name="unique_chat_submission_request")]


class ConversationState(models.Model):
    """What the reader was shown and chose, one revision per delivered Turn (IR-592).

    Record ids only, never titles or text; every read rechecks visibility.
    Cascades with its Conversation, so it has no lifetime of its own.
    """

    RECORDED = "recorded"
    CONFLICT = "conflict"
    _BASIS_CHOICES = [(RECORDED, "Recorded"), (CONFLICT, "Conflict")]

    conversation = models.OneToOneField(
        Conversation, on_delete=models.CASCADE, primary_key=True, related_name="context_state"
    )
    revision = models.PositiveIntegerField(default=0)
    basis = models.CharField(max_length=20, choices=_BASIS_CHOICES, default=RECORDED)
    answer_turn = models.ForeignKey(
        Turn, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    request = models.TextField(blank=True)
    retrieval_query = models.TextField(blank=True)
    topic = models.CharField(max_length=200, blank=True)
    filters = models.JSONField(default=dict, blank=True)
    presented = models.JSONField(default=list, blank=True)
    selected = models.JSONField(default=list, blank=True)
    excluded = models.JSONField(default=list, blank=True)
    pending_clarification = models.JSONField(null=True, blank=True)
    #: Record id (as a string) to the active ChunkSet content hash at commit.
    source_versions = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"ConversationState({self.conversation_id}, revision={self.revision})"


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

    objects = TurnEmbeddingQuerySet.as_manager()

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
