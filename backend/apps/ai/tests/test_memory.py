"""Memory recall, isolated from HTTP (IR-297).

Needs real rows for `CosineDistance`, so unlike `test_resolution.py` this
isn't a pure unit test. `test_memory_http.py` covers the HTTP boundary.
"""

import logging

import pytest
from django.test import override_settings

from apps.ai.memory import DEFAULT_MAX_RECALL_DISTANCE, ConversationMemory
from apps.ai.models import Conversation, Turn, TurnEmbedding
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
