"""Backfilling the answer vector onto Turns that predate IR-447.

IR-447 gives a Turn two vectors as it is written; a Conversation already in
the database keeps its question vectors alone until this command is run.
These tests pin the three properties that make it safe to run against real
history: it shows the bill before spending, it refuses past the ceiling, and
running it twice costs nothing the second time.
"""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.ai.models import (
    TURN_ANSWER_VECTOR,
    TURN_QUESTION_VECTOR,
    Conversation,
    Turn,
    TurnEmbedding,
)
from apps.ai.providers.fakes import DeterministicEmbeddingProvider
from apps.ai.turn_backfill import plan_turns, turns_to_consider

from .corpus import make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


class _CountingEmbedder(DeterministicEmbeddingProvider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.query_calls = 0
        self.document_calls = 0

    def embed_query(self, text):
        self.query_calls += 1
        return super().embed_query(text)

    def embed_documents(self, texts):
        self.document_calls += 1
        return super().embed_documents(texts)


def _old_turn(conversation, question, answer, state="generated", space=None, embedder=None):
    """A Turn as it was stored before IR-447: question vector only."""
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
    return turn


@pytest.fixture
def conversation():
    return Conversation.objects.create(user=make_user("reader@cit.edu"))


class PlanningTests:
    def test_an_answered_turn_with_no_answer_vector_is_planned(
        self, conversation, embedder, space
    ):
        _old_turn(conversation, "q", "a real answer", space=space, embedder=embedder)

        plan = plan_turns(
            turns_to_consider(), space_id=space.pk, space_model="m", cost_per_million=0.0
        )

        assert len(plan.to_embed) == 1
        assert plan.estimated_tokens > 0

    @pytest.mark.parametrize("state", ["no_sources", "unavailable", "partial"])
    def test_a_turn_that_is_not_an_answer_is_never_planned(
        self, conversation, embedder, space, state
    ):
        """The same exclusion `record_turn` applies, enforced in the backfill
        too -- otherwise a refusal nobody indexed live would become findable
        the first time an operator ran this."""
        _old_turn(
            conversation, "q", "an explanation, not an answer",
            state=state, space=space, embedder=embedder,
        )

        plan = plan_turns(
            turns_to_consider(), space_id=space.pk, space_model="m", cost_per_million=0.0
        )

        assert plan.to_embed == []
        assert any("not an answer" in reason for reason in plan.skipped)

    def test_a_turn_that_already_has_one_is_skipped(
        self, conversation, embedder, space
    ):
        """"Already has a vector in this space" *is* the resume, so it has to
        be the skip as well."""
        turn = _old_turn(conversation, "q", "a real answer", space=space, embedder=embedder)
        TurnEmbedding.objects.create(
            turn=turn, space=space, kind=TURN_ANSWER_VECTOR,
            embedding=embedder.embed_query("a real answer"),
        )

        plan = plan_turns(
            turns_to_consider(), space_id=space.pk, space_model="m", cost_per_million=0.0
        )

        assert plan.to_embed == []
        assert plan.skipped["already has an answer vector in this space"] == 1

    def test_a_turn_vector_in_another_space_does_not_count_as_done(
        self, conversation, embedder, space
    ):
        """The skip is per space. A vector under a retired space cannot be
        compared against a current one, so it is not a reason to skip."""
        from apps.ai.models.embedding_space import EmbeddingSpace, EmbeddingSpaceState

        other = EmbeddingSpace.objects.create(
            model_id="other-model", dimensions=embedder.dimensions,
            metric="cosine", state=EmbeddingSpaceState.RETIRED,
        )
        turn = _old_turn(conversation, "q", "a real answer", space=space, embedder=embedder)
        TurnEmbedding.objects.create(
            turn=turn, space=other, kind=TURN_ANSWER_VECTOR,
            embedding=embedder.embed_query("a real answer"),
        )

        plan = plan_turns(
            turns_to_consider(), space_id=space.pk, space_model="m", cost_per_million=0.0
        )

        assert len(plan.to_embed) == 1


class CommandTests:
    def test_dry_run_spends_nothing_and_writes_nothing(
        self, conversation, embedder, space, capsys
    ):
        _old_turn(conversation, "q", "a real answer", space=space, embedder=embedder)
        provider = _CountingEmbedder(dimensions=embedder.dimensions)

        with _root(provider):
            call_command("backfill_turn_vectors", "--dry-run")

        assert provider.query_calls == 0
        assert not TurnEmbedding.objects.filter(kind=TURN_ANSWER_VECTOR).exists()
        assert "Dry run" in capsys.readouterr().out

    def test_the_plan_is_printed_before_anything_is_sent(
        self, conversation, embedder, space, capsys
    ):
        _old_turn(conversation, "q", "a real answer", space=space, embedder=embedder)

        with _root(_CountingEmbedder(dimensions=embedder.dimensions)):
            call_command("backfill_turn_vectors", "--dry-run")

        out = capsys.readouterr().out
        assert "Turns to embed" in out
        assert "estimated tokens" in out

    def test_a_run_stores_the_answer_vector_through_embed_query(
        self, conversation, embedder, space
    ):
        turn = _old_turn(conversation, "q", "a real answer", space=space, embedder=embedder)
        provider = _CountingEmbedder(dimensions=embedder.dimensions)

        with _root(provider):
            call_command("backfill_turn_vectors")

        stored = TurnEmbedding.objects.get(turn=turn, kind=TURN_ANSWER_VECTOR)
        assert list(stored.embedding) == pytest.approx(
            provider.embed_query("a real answer")
        )
        assert provider.document_calls == 0

    def test_it_is_idempotent_a_second_run_sends_nothing(
        self, conversation, embedder, space
    ):
        _old_turn(conversation, "q", "a real answer", space=space, embedder=embedder)
        provider = _CountingEmbedder(dimensions=embedder.dimensions)

        with _root(provider):
            call_command("backfill_turn_vectors")
            after_first = provider.query_calls
            call_command("backfill_turn_vectors")

        assert after_first == 1
        assert provider.query_calls == after_first

    def test_it_is_resumable_only_the_missing_turn_is_embedded(
        self, conversation, embedder, space
    ):
        """What a run embeds is recomputed every time, so a crash halfway
        resumes at the halfway point with no checkpoint to have lost."""
        done = _old_turn(conversation, "q1", "first answer", space=space, embedder=embedder)
        _old_turn(conversation, "q2", "second answer", space=space, embedder=embedder)
        TurnEmbedding.objects.create(
            turn=done, space=space, kind=TURN_ANSWER_VECTOR,
            embedding=embedder.embed_query("first answer"),
        )
        provider = _CountingEmbedder(dimensions=embedder.dimensions)

        with _root(provider):
            call_command("backfill_turn_vectors")

        assert provider.query_calls == 1

    def test_it_refuses_past_the_token_ceiling_without_sending(
        self, conversation, embedder, space
    ):
        _old_turn(conversation, "q", "a real answer", space=space, embedder=embedder)
        provider = _CountingEmbedder(dimensions=embedder.dimensions)

        with _root(provider):
            with pytest.raises(CommandError, match="over the ceiling"):
                call_command("backfill_turn_vectors", "--token-ceiling", "1")

        assert provider.query_calls == 0
        assert not TurnEmbedding.objects.filter(kind=TURN_ANSWER_VECTOR).exists()

    def test_a_zero_ceiling_disables_the_guard(
        self, conversation, embedder, space
    ):
        _old_turn(conversation, "q", "a real answer", space=space, embedder=embedder)
        provider = _CountingEmbedder(dimensions=embedder.dimensions)

        with _root(provider):
            call_command("backfill_turn_vectors", "--token-ceiling", "0")

        assert provider.query_calls == 1

    def test_the_settings_ceiling_applies_when_none_is_passed(
        self, conversation, embedder, space
    ):
        _old_turn(conversation, "q", "a real answer", space=space, embedder=embedder)
        provider = _CountingEmbedder(dimensions=embedder.dimensions)

        with override_settings(AI_EMBEDDING_TOKEN_CEILING=1):
            with _root(provider):
                with pytest.raises(CommandError, match="over the ceiling"):
                    call_command("backfill_turn_vectors")

        assert provider.query_calls == 0

    def test_one_turn_failing_does_not_abandon_the_rest(
        self, conversation, embedder, space
    ):
        _old_turn(conversation, "q1", "poison", space=space, embedder=embedder)
        _old_turn(conversation, "q2", "a real answer", space=space, embedder=embedder)

        class _FailsOnPoison(DeterministicEmbeddingProvider):
            def embed_query(self, text):
                if text == "poison":
                    raise RuntimeError("vendor rejected it")
                return super().embed_query(text)

        with _root(_FailsOnPoison(dimensions=embedder.dimensions)):
            call_command("backfill_turn_vectors")

        assert TurnEmbedding.objects.filter(kind=TURN_ANSWER_VECTOR).count() == 1


def _root(embedder):
    """The composition root the command reaches for, with a fake embedder."""
    from apps.ai.composition import CompositionRoot, use_composition_root

    return use_composition_root(CompositionRoot(embedder=embedder))
