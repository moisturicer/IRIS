"""Memory recall, isolated from HTTP (IR-297).

Needs real rows for `CosineDistance`, so unlike `test_resolution.py` this
isn't a pure unit test. `test_memory_http.py` covers the HTTP boundary.
"""

import logging

import pytest

from apps.ai.memory import ConversationMemory
from apps.ai.models import Conversation, Turn, TurnEmbedding
from apps.ai.models.embedding_space import EmbeddingSpace, EmbeddingSpaceState

from .corpus import make_user

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


def _turn(conversation, question, answer="", space=None, embedder=None):
    turn = Turn.objects.create(
        conversation=conversation, question=question, answer=answer, state="generated"
    )
    if space is not None:
        TurnEmbedding.objects.create(
            turn=turn, space=space, embedding=embedder.embed_query(question)
        )
    return turn


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
