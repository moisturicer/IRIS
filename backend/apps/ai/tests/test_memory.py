"""Memory recall, isolated from HTTP (IR-297).

Needs real rows for `CosineDistance`, so unlike `test_resolution.py` this
isn't a pure unit test. `test_memory_http.py` covers the HTTP boundary.
"""

import logging

import pytest
from django.test import override_settings

from apps.ai.answers.citations import (
    GENERATED,
    NO_SOURCES,
    PARTIAL,
    UNAVAILABLE,
    GroundedAnswer,
)
from apps.ai.conversations import record_turn
from apps.ai.memory import (
    DEFAULT_MAX_RECALL_DISTANCE,
    MAX_RECALLED_TURNS,
    ConversationMemory,
)
from apps.ai.models import (
    TURN_ANSWER_VECTOR,
    TURN_QUESTION_VECTOR,
    Conversation,
    Turn,
    TurnEmbedding,
)
from apps.ai.models.embedding_space import EmbeddingSpace, EmbeddingSpaceState

from .corpus import FLOOD_QUESTION, POND_QUESTION, make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

#: `apps` sets `propagate: False`, so caplog needs the handler attached
#: directly -- mirrors `apps/ai/answers/tests/test_service.py`.
_MEMORY_LOGGER = "apps.ai.memory"


@pytest.fixture
def memory_logs(caplog):
    logger = logging.getLogger(_MEMORY_LOGGER)
    logger.addHandler(caplog.handler)
    caplog.set_level(logging.WARNING, logger=_MEMORY_LOGGER)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)


def _turn(
    conversation,
    question,
    answer="",
    space=None,
    embedder=None,
    answer_vector=True,
    state=GENERATED,
):
    """A stored Turn with the vectors `record_turn` would have given it.

    Two of them when there is an answer (IR-447), both through `embed_query`,
    which is what `conversations._store_answer_vector` does and why
    `ConversationMemory` can rank them in one list.

    ``answer_vector=False`` stores the question vector alone -- a Turn as it
    would have been written before IR-447. It is what makes the answer-recall
    tests below honest: the same question, the same answer and the same query,
    recalled with the second vector and missed without it.
    """
    turn = Turn.objects.create(
        conversation=conversation, question=question, answer=answer, state=state
    )
    if space is not None:
        TurnEmbedding.objects.create(
            turn=turn,
            space=space,
            kind=TURN_QUESTION_VECTOR,
            embedding=embedder.embed_query(question),
        )
        if answer and answer_vector:
            TurnEmbedding.objects.create(
                turn=turn,
                space=space,
                kind=TURN_ANSWER_VECTOR,
                embedding=embedder.embed_query(answer),
            )
    return turn


#: ADR-026 §7's own illustration, as a fixture pair. A generic question whose
#: answer carries the only distinctive words in it -- which is precisely the
#: Turn question-only indexing cannot reach.
_GENERIC_QUESTION = "what does the paper conclude?"
_SPECIFIC_ANSWER = (
    "The Jordan frame bound is 0.37 under the separate-universe approach."
)
#: Deliberately shares no word with `_GENERIC_QUESTION` -- not even "what"
#: or "the". The fake embedder is a hashed bag of words, so a stopword in
#: common is real similarity to it, and the first draft of this fixture
#: measured 0.9996 against the question either way: the control test passed
#: for the wrong reason. Overlapping the *answer* and nothing else is what
#: makes these tests about the answer vector.
_ASKING_ABOUT_THE_ANSWER = "which figure gave Jordan frame bound 0.37"


class RecallingRelevantTurnsTests:
    def test_the_turn_closest_to_the_query_vector_is_recalled(self, embedder, space):
        conversation = Conversation.objects.create(user=make_user("reader@cit.edu"))
        flood_turn = _turn(
            conversation, "neural network rainfall flooding catchment",
            space=space, embedder=embedder,
        )
        _turn(conversation, "tilapia pond stocking density", space=space, embedder=embedder)

        memory = ConversationMemory()
        recalled = memory.recall(
            conversation,
            embedder.embed_query("what did the flooding catchment study conclude?"),
            space.pk,
        )

        assert recalled[0].pk == flood_turn.pk

    def test_excluded_ids_are_never_recalled_even_when_closest(self, embedder, space):
        conversation = Conversation.objects.create(user=make_user("reader@cit.edu"))
        flood_turn = _turn(
            conversation, "neural network rainfall flooding catchment",
            space=space, embedder=embedder,
        )

        memory = ConversationMemory()
        recalled = memory.recall(
            conversation,
            embedder.embed_query("neural network rainfall flooding catchment"),
            space.pk,
            exclude_ids=[flood_turn.pk],
        )

        assert recalled == []

    def test_recall_is_bounded_by_the_configured_limit(self, embedder, space):
        conversation = Conversation.objects.create(user=make_user("reader@cit.edu"))
        for i in range(6):
            _turn(conversation, f"flooding catchment question {i}", space=space, embedder=embedder)

        memory = ConversationMemory(limit=3)
        recalled = memory.recall(
            conversation, embedder.embed_query("flooding catchment"), space.pk
        )

        assert len(recalled) == 3

    def test_a_turn_from_a_different_conversation_is_never_recalled(self, embedder, space):
        mine = Conversation.objects.create(user=make_user("me@cit.edu"))
        theirs = Conversation.objects.create(user=make_user("them@cit.edu"))
        _turn(
            theirs, "neural network rainfall flooding catchment",
            space=space, embedder=embedder,
        )

        memory = ConversationMemory()
        recalled = memory.recall(
            mine, embedder.embed_query("neural network rainfall flooding catchment"), space.pk
        )

        assert recalled == []


class RecallingByTheAnswerTests:
    """IR-447, ADR-026 §7 as amended -- a Turn is findable by what it said.

    The pair of tests at the top is the whole acceptance criterion: identical
    Turns, identical query, recalled with the answer vector and missed
    without it. Written as a pair deliberately, because the positive test
    alone would still pass if the fake embedder happened to put the query
    near the *question* too, and would then be proving nothing.
    """

    def test_a_turn_is_recalled_by_its_answer_when_its_question_never_said_the_words(
        self, embedder, space
    ):
        conversation = Conversation.objects.create(user=make_user("reader@cit.edu"))
        conclusion = _turn(
            conversation,
            _GENERIC_QUESTION,
            answer=_SPECIFIC_ANSWER,
            space=space,
            embedder=embedder,
        )
        _turn(
            conversation,
            POND_QUESTION,
            answer="Four fingerlings per square metre.",
            space=space,
            embedder=embedder,
        )

        recalled = ConversationMemory().recall(
            conversation, embedder.embed_query(_ASKING_ABOUT_THE_ANSWER), space.pk
        )

        assert [turn.pk for turn in recalled] == [conclusion.pk]

    def test_the_same_turn_is_missed_when_only_its_question_is_indexed(
        self, embedder, space
    ):
        """The control. This is what the bug looked like before IR-447."""
        conversation = Conversation.objects.create(user=make_user("reader@cit.edu"))
        _turn(
            conversation,
            _GENERIC_QUESTION,
            answer=_SPECIFIC_ANSWER,
            space=space,
            embedder=embedder,
            answer_vector=False,
        )

        recalled = ConversationMemory().recall(
            conversation, embedder.embed_query(_ASKING_ABOUT_THE_ANSWER), space.pk
        )

        assert recalled == []

    def test_a_turn_reached_by_its_answer_is_returned_whole(self, embedder, space):
        """ADR-026 §7: "The Turn is still returned whole; either vector can
        now reach it." So the question comes back too, not just the half that
        matched."""
        conversation = Conversation.objects.create(user=make_user("reader@cit.edu"))
        _turn(
            conversation,
            _GENERIC_QUESTION,
            answer=_SPECIFIC_ANSWER,
            space=space,
            embedder=embedder,
        )

        recalled = ConversationMemory().recall(
            conversation, embedder.embed_query(_ASKING_ABOUT_THE_ANSWER), space.pk
        )

        assert recalled[0].question == _GENERIC_QUESTION
        assert recalled[0].answer == _SPECIFIC_ANSWER

    def test_a_turn_matching_on_both_vectors_is_recalled_once(self, embedder, space):
        """The de-duplication. Ranking is over vectors, the result is over
        Turns, and a Turn that matches twice is still one Turn."""
        conversation = Conversation.objects.create(user=make_user("reader@cit.edu"))
        both = _turn(
            conversation,
            FLOOD_QUESTION,
            answer=FLOOD_QUESTION,
            space=space,
            embedder=embedder,
        )

        recalled = ConversationMemory().recall(
            conversation, embedder.embed_query(FLOOD_QUESTION), space.pk
        )

        assert [turn.pk for turn in recalled] == [both.pk]

    def test_a_turn_matching_twice_does_not_crowd_out_other_turns(
        self, embedder, space
    ):
        """The reason de-duplication had to happen before the slice, not
        after it: two rows of one Turn must not consume two of the four slots
        and shrink the recall to three Turns."""
        conversation = Conversation.objects.create(user=make_user("reader@cit.edu"))
        # Question and answer identical, so both of its vectors sit at the
        # very top of the ranking.
        _turn(
            conversation, FLOOD_QUESTION, answer=FLOOD_QUESTION,
            space=space, embedder=embedder,
        )
        for i in range(4):
            _turn(
                conversation,
                f"{FLOOD_QUESTION} variation {i}",
                answer=f"{FLOOD_QUESTION} answer {i}",
                space=space, embedder=embedder,
            )

        recalled = ConversationMemory().recall(
            conversation, embedder.embed_query(FLOOD_QUESTION), space.pk,
        )

        assert len(recalled) == MAX_RECALLED_TURNS
        assert len({turn.pk for turn in recalled}) == MAX_RECALLED_TURNS

    def test_an_excluded_turn_stays_excluded_through_its_answer_vector(
        self, embedder, space
    ):
        """`exclude_ids` is how the caller keeps the verbatim window from
        being recalled a second time. A second vector per Turn must not be a
        second way around it."""
        conversation = Conversation.objects.create(user=make_user("reader@cit.edu"))
        turn = _turn(
            conversation,
            _GENERIC_QUESTION,
            answer=_SPECIFIC_ANSWER,
            space=space,
            embedder=embedder,
        )

        recalled = ConversationMemory().recall(
            conversation,
            embedder.embed_query(_ASKING_ABOUT_THE_ANSWER),
            space.pk,
            exclude_ids=[turn.pk],
        )

        assert recalled == []

    def test_an_answer_vector_from_a_retired_space_is_never_compared_against_a_current_one(
        self, embedder, space
    ):
        """The space rule holds per vector, not per Turn (ADR-026
        §Consequences). A Turn can hold one vector in each."""
        conversation = Conversation.objects.create(user=make_user("reader@cit.edu"))
        retired = EmbeddingSpace.objects.create(
            model_id="retired-model",
            dimensions=embedder.dimensions,
            metric="cosine",
            state=EmbeddingSpaceState.RETIRED,
        )
        turn = _turn(
            conversation,
            _GENERIC_QUESTION,
            answer=_SPECIFIC_ANSWER,
            space=space,
            embedder=embedder,
        )
        turn.embeddings.filter(kind=TURN_ANSWER_VECTOR).update(space=retired)

        recalled = ConversationMemory().recall(
            conversation, embedder.embed_query(_ASKING_ABOUT_THE_ANSWER), space.pk
        )

        assert recalled == []


class AnswerVectorStateTests:
    """Which Turns get an answer vector, driven through `record_turn` itself.

    `GroundedAnswer.text` is populated in every state, so "has text" is not
    the question -- "is that text an answer" is. A `no_sources` or
    `unavailable` Turn holds an explanation and a `partial` one holds a
    fragment from a stream that died mid-sentence, and embedding any of them
    would make refusals and failures findable, which is the thing IR-448
    exists to prevent.
    """

    @pytest.mark.parametrize(
        "state", [NO_SOURCES, UNAVAILABLE, PARTIAL]
    )
    def test_a_turn_that_is_not_an_answer_stores_no_answer_vector(
        self, embedder, space, state
    ):
        conversation = Conversation.objects.create(user=make_user("reader@cit.edu"))

        turn = record_turn(
            conversation,
            "what does this paper conclude?",
            _answer("an explanation, or half a sentence", state, embedder, space),
            embedder=embedder,
        )

        kinds = set(turn.embeddings.values_list("kind", flat=True))
        assert kinds == {TURN_QUESTION_VECTOR}

    def test_a_generated_turn_stores_both(self, embedder, space):
        conversation = Conversation.objects.create(user=make_user("reader@cit.edu"))

        turn = record_turn(
            conversation,
            "what does this paper conclude?",
            _answer(_SPECIFIC_ANSWER, GENERATED, embedder, space),
            embedder=embedder,
        )

        kinds = set(turn.embeddings.values_list("kind", flat=True))
        assert kinds == {TURN_QUESTION_VECTOR, TURN_ANSWER_VECTOR}

    def test_a_generated_turn_with_an_empty_answer_stores_no_answer_vector(
        self, embedder, space
    ):
        """Nothing to embed is not the same as something to embed badly."""
        conversation = Conversation.objects.create(user=make_user("reader@cit.edu"))

        turn = record_turn(
            conversation,
            "what does this paper conclude?",
            _answer("   ", GENERATED, embedder, space),
            embedder=embedder,
        )

        kinds = set(turn.embeddings.values_list("kind", flat=True))
        assert kinds == {TURN_QUESTION_VECTOR}

    def test_a_degraded_answer_with_no_space_stores_neither(self, embedder, space):
        """The degraded, full-text path carries no vector of any kind, and
        IR-447 does not give it one -- there is no space to store it under."""
        conversation = Conversation.objects.create(user=make_user("reader@cit.edu"))

        turn = record_turn(
            conversation,
            "what does this paper conclude?",
            GroundedAnswer(
                text=_SPECIFIC_ANSWER, citations=(), state=GENERATED, degraded=True
            ),
            embedder=embedder,
        )

        assert list(turn.embeddings.all()) == []


class OneRankedListTests:
    """ADR-026 §7: both vectors go in under the same input type, so
    `recall`'s single `ORDER BY distance` compares like with like.

    The fake embedder reproduces Voyage's asymmetry -- `embed_documents(x)`
    and `embed_query(x)` differ for identical text -- which is what makes
    this assertable without a vendor account: a vector can be attributed to
    the method that produced it.
    """

    def test_every_vector_in_the_ranked_list_is_a_query_vector(
        self, embedder, space
    ):
        conversation = Conversation.objects.create(user=make_user("reader@cit.edu"))
        turn = record_turn(
            conversation,
            _GENERIC_QUESTION,
            _answer(_SPECIFIC_ANSWER, GENERATED, embedder, space),
            embedder=embedder,
        )

        texts = {
            TURN_QUESTION_VECTOR: _GENERIC_QUESTION,
            TURN_ANSWER_VECTOR: _SPECIFIC_ANSWER,
        }
        rows = list(turn.embeddings.all())
        assert len(rows) == 2

        for row in rows:
            text = texts[row.kind]
            # Each stored vector matches the query method and not the
            # document method, so the two kinds sit in one comparable space.
            assert list(row.embedding) == pytest.approx(embedder.embed_query(text))
            assert list(row.embedding) != pytest.approx(
                embedder.embed_documents([text])[0]
            )

    def test_recall_does_not_filter_by_kind(self, embedder, space):
        """One list, not one query per kind. If recall ever narrowed to a
        single kind, the answer vector would be stored and never read -- a
        silent no-op that every other test here would still pass."""
        conversation = Conversation.objects.create(user=make_user("reader@cit.edu"))
        answer_only = _turn(
            conversation,
            _GENERIC_QUESTION,
            answer=_SPECIFIC_ANSWER,
            space=space,
            embedder=embedder,
        )
        answer_only.embeddings.filter(kind=TURN_QUESTION_VECTOR).delete()

        recalled = ConversationMemory().recall(
            conversation, embedder.embed_query(_ASKING_ABOUT_THE_ANSWER), space.pk
        )

        assert [turn.pk for turn in recalled] == [answer_only.pk]


def _answer(text, state, embedder, space):
    """A `GroundedAnswer` carrying the question vector retrieval would have
    produced, so `record_turn` behaves as it does in the real path."""
    return GroundedAnswer(
        text=text,
        citations=(),
        state=state,
        query_vector=embedder.embed_query(_GENERIC_QUESTION),
        embedding_space_id=space.pk,
    )


class RelevanceCutOffTests:
    """IR-446: the four closest Turns are not automatically the relevant ones."""

    def _a_pond_turn_and_a_flood_question(self, embedder, space):
        """One Turn the question is not about, which a cut-off must drop."""
        conversation = Conversation.objects.create(user=make_user("reader@cit.edu"))
        _turn(conversation, POND_QUESTION, space=space, embedder=embedder)
        return conversation, embedder.embed_query(FLOOD_QUESTION)

    @override_settings(AI_MEMORY_RECALL_MAX_DISTANCE=0.8)
    def test_a_turn_beyond_the_cut_off_is_not_recalled(self, embedder, space):
        conversation, query = self._a_pond_turn_and_a_flood_question(embedder, space)

        assert ConversationMemory().recall(conversation, query, space.pk) == []

    @override_settings(AI_MEMORY_RECALL_MAX_DISTANCE=0.8)
    def test_a_turn_within_the_cut_off_is_recalled_unaffected(self, embedder, space):
        conversation, query = self._a_pond_turn_and_a_flood_question(embedder, space)
        flood_turn = _turn(conversation, FLOOD_QUESTION, space=space, embedder=embedder)

        recalled = ConversationMemory().recall(conversation, query, space.pk)

        assert [turn.pk for turn in recalled] == [flood_turn.pk]

    def test_the_cut_off_is_read_per_request_not_bound_at_construction(
        self, embedder, space
    ):
        conversation, query = self._a_pond_turn_and_a_flood_question(embedder, space)
        memory = ConversationMemory()

        with override_settings(AI_MEMORY_RECALL_MAX_DISTANCE=0.8):
            assert memory.recall(conversation, query, space.pk) == []
        with override_settings(AI_MEMORY_RECALL_MAX_DISTANCE=2.0):
            assert len(memory.recall(conversation, query, space.pk)) == 1

    @override_settings(AI_MEMORY_RECALL_MAX_DISTANCE=0)
    def test_a_non_positive_cut_off_disables_it(self, embedder, space):
        conversation, query = self._a_pond_turn_and_a_flood_question(embedder, space)

        assert len(ConversationMemory().recall(conversation, query, space.pk)) == 1

    def test_the_module_default_and_the_settings_default_do_not_drift(self):
        """Two places hold 0.80 -- the code's fallback and the setting. The
        setting is the one a deployment reads, so they must agree."""
        from django.conf import settings

        assert settings.AI_MEMORY_RECALL_MAX_DISTANCE == DEFAULT_MAX_RECALL_DISTANCE


class SpaceIsolationTests:
    def test_a_turn_vector_from_a_retired_space_is_never_compared_against_the_current_one(
        self, embedder, space
    ):
        conversation = Conversation.objects.create(user=make_user("reader@cit.edu"))
        retired = EmbeddingSpace.objects.create(
            model_id="retired-model", dimensions=embedder.dimensions,
            metric="cosine", state=EmbeddingSpaceState.RETIRED,
        )
        _turn(
            conversation, "neural network rainfall flooding catchment",
            space=retired, embedder=embedder,
        )

        memory = ConversationMemory()
        recalled = memory.recall(
            conversation,
            embedder.embed_query("neural network rainfall flooding catchment"),
            space.pk,
        )

        assert recalled == []


class DegradingWhenVectorsAreUnavailableTests:
    def test_no_query_vector_degrades_to_an_empty_recall_rather_than_raising(
        self, embedder, space
    ):
        conversation = Conversation.objects.create(user=make_user("reader@cit.edu"))
        _turn(
            conversation, "neural network rainfall flooding catchment",
            space=space, embedder=embedder,
        )

        memory = ConversationMemory()
        assert memory.recall(conversation, None, space.pk) == []

    def test_no_active_space_degrades_to_an_empty_recall_rather_than_raising(
        self, embedder, space
    ):
        conversation = Conversation.objects.create(user=make_user("reader@cit.edu"))
        _turn(
            conversation, "neural network rainfall flooding catchment",
            space=space, embedder=embedder,
        )

        memory = ConversationMemory()
        recalled = memory.recall(
            conversation, embedder.embed_query("flooding catchment"), None
        )

        assert recalled == []

    def test_unavailable_vectors_are_logged_rather_than_silent(
        self, embedder, space, memory_logs
    ):
        conversation = Conversation.objects.create(user=make_user("reader@cit.edu"))
        memory = ConversationMemory()

        memory.recall(conversation, None, space.pk)

        assert "conversation memory unavailable" in memory_logs.text


class FailedTurnsLeaveRecallTests:
    """A failed or refused Turn is unreachable by vector (IR-448, ADR-026 §13).

    Keeping one out of the verbatim window and leaving it recallable would be
    the same bug with a longer fuse: memory exists precisely to reach a Turn
    the window has dropped, so recall is the second door into the prompt and
    has to be shut too.

    These are written as *pairs* against `GENERATED`: the same Conversation,
    the same text and the same query, recalled in one state and missed in the
    other. Without the control a filter that excluded everything would pass.
    """

    @pytest.mark.parametrize("state", [NO_SOURCES, UNAVAILABLE, PARTIAL])
    def test_a_failed_turn_is_not_recalled_even_when_it_is_the_closest(
        self, embedder, space, state
    ):
        reader = make_user("reader@cit.edu")
        conversation = Conversation.objects.create(user=reader)
        # The only Turn there is, and an exact match on both its vectors.
        _turn(
            conversation,
            FLOOD_QUESTION,
            answer=FLOOD_QUESTION,
            space=space,
            embedder=embedder,
            state=state,
        )

        recalled = ConversationMemory().recall(
            conversation, embedder.embed_query(FLOOD_QUESTION), space.pk
        )

        assert recalled == []

    @pytest.mark.parametrize("state", [NO_SOURCES, UNAVAILABLE, PARTIAL])
    def test_the_same_turn_generated_is_recalled(self, embedder, space, state):
        """The control for the test above -- the pair, not a second case.

        `state` is parametrised identically and deliberately unused in the
        body: it makes the two tests one table, so a state added to one list
        cannot be left out of the other.
        """
        reader = make_user("reader@cit.edu")
        conversation = Conversation.objects.create(user=reader)
        turn = _turn(
            conversation,
            FLOOD_QUESTION,
            answer=FLOOD_QUESTION,
            space=space,
            embedder=embedder,
            state=GENERATED,
        )

        recalled = ConversationMemory().recall(
            conversation, embedder.embed_query(FLOOD_QUESTION), space.pk
        )

        assert [t.pk for t in recalled] == [turn.pk]

    def test_a_failed_turn_does_not_consume_a_recall_slot(self, embedder, space):
        """Excluded before the ranking is cut to `MAX_RECALLED_TURNS`, not
        after -- otherwise a run of refusals would crowd out the real Turns
        it was meant to make room for."""
        reader = make_user("reader@cit.edu")
        conversation = Conversation.objects.create(user=reader)
        for _ in range(MAX_RECALLED_TURNS):
            _turn(
                conversation,
                FLOOD_QUESTION,
                answer=FLOOD_QUESTION,
                space=space,
                embedder=embedder,
                state=NO_SOURCES,
            )
        wanted = [
            _turn(
                conversation,
                FLOOD_QUESTION,
                answer=FLOOD_QUESTION,
                space=space,
                embedder=embedder,
            ).pk
            for _ in range(MAX_RECALLED_TURNS)
        ]

        recalled = ConversationMemory().recall(
            conversation, embedder.embed_query(FLOOD_QUESTION), space.pk
        )

        assert sorted(t.pk for t in recalled) == sorted(wanted)

    def test_the_exclusion_is_by_state_not_by_answer_text(self, embedder, space):
        """A reader may legitimately ask about refusals, and an answer that
        happens to read like one is still an answer. `state` is the fact;
        matching on the text would be a phrase list, which is what ADR-026
        §13 chose a stored state over."""
        reader = make_user("reader@cit.edu")
        conversation = Conversation.objects.create(user=reader)
        turn = _turn(
            conversation,
            FLOOD_QUESTION,
            answer="The supplied sources do not contain any information about this.",
            space=space,
            embedder=embedder,
            state=GENERATED,
        )

        recalled = ConversationMemory().recall(
            conversation, embedder.embed_query(FLOOD_QUESTION), space.pk
        )

        assert [t.pk for t in recalled] == [turn.pk]
