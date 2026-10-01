"""Conversation memory through the HTTP boundary (IR-297).

Same seam as `test_ask_http.py` and `test_resolution_http.py`: what a
caller observes is a response. Driven with the deterministic provider
fakes, no vendor account needed.
"""

import pytest
from django.test import override_settings
from django.urls import reverse

from apps.ai.composition import use_composition_root
from apps.ai.models import TurnEmbedding
from apps.ai.models.embedding_space import EmbeddingSpace, EmbeddingSpaceState
from apps.ai.providers.fakes import DeterministicEmbeddingProvider, ScriptedLLM
from apps.ai.resolution import MAX_HISTORY_TURNS, QuestionResolver

from .corpus import (
    DIMENSIONS,
    FLOOD_QUESTION,
    FLOOD_TEXT,
    POND_QUESTION,
    POND_TEXT,
    _BrokenEmbedder,
    ask,
    make_record,
    make_user,
    root_with,
)

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def conversation_url(pk):
    return reverse("ai-conversation-detail", args=[pk])


def start(client, **body):
    return client.post(reverse("ai-conversations"), body, format="json")


def _resolving_to_the_flood_question():
    """A resolver that rewrites a follow-up into a question about the flood
    paper, so the Turn recall finds is genuinely relevant to it.

    Needed since IR-446 put a distance floor under recall: with the default
    `ScriptedLLM` reply standing in for a resolved question, the follow-up
    searches for text about nothing in the Conversation, and a recall that
    returned Turn 1 anyway would be the defect the floor exists to stop.
    """
    return QuestionResolver(llm=ScriptedLLM(reply=FLOOD_QUESTION), cache={})


def _fill_past_the_recent_window(client, conversation_id):
    """Pushes the first Turn outside the verbatim window."""
    for i in range(MAX_HISTORY_TURNS):
        ask(client, f"filler question number {i}", conversation_id=conversation_id)


class _CountingEmbedder(DeterministicEmbeddingProvider):
    """Counts `embed_query` calls, to pin the zero-extra-cost guarantee."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.query_calls = 0

    def embed_query(self, text):
        self.query_calls += 1
        return super().embed_query(text)


class RemembersAcrossManyTurnsTests:
    def test_a_fact_established_early_is_retrieved_by_memory_many_turns_later(
        self, embedder, space, client_for
    ):
        """Turn 1 has aged out of the verbatim window by the time it is
        asked about again -- it can only reach the prompt via recall."""
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]
        llm = ScriptedLLM()
        root = root_with(
            embedder=embedder, llm=llm, resolver=_resolving_to_the_flood_question()
        )

        with use_composition_root(root):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
            _fill_past_the_recent_window(client, conversation_id)
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        _system, prompt = llm.calls[-1]
        assert "Relevant earlier in this conversation:" in prompt
        assert f"Q: {FLOOD_QUESTION}" in prompt

    def test_recent_turns_still_read_verbatim_alongside_a_recollection(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]
        llm = ScriptedLLM()
        root = root_with(
            embedder=embedder, llm=llm, resolver=_resolving_to_the_flood_question()
        )

        with use_composition_root(root):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
            _fill_past_the_recent_window(client, conversation_id)
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        _system, prompt = llm.calls[-1]
        assert "Conversation so far:" in prompt
        assert "Q: filler question number 0" in prompt

    def test_nothing_is_summarised_the_recalled_turn_reads_in_full(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]
        llm = ScriptedLLM(reply="The model rained on the catchment [1].")
        root = root_with(
            embedder=embedder, llm=llm, resolver=_resolving_to_the_flood_question()
        )

        with use_composition_root(root):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
            _fill_past_the_recent_window(client, conversation_id)
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        _system, prompt = llm.calls[-1]
        assert "The model rained on the catchment" in prompt

    def test_a_turn_still_within_the_recent_window_is_not_also_recalled(
        self, embedder, space, client_for
    ):
        """Must not be doubled into the recollection section too."""
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]
        llm = ScriptedLLM()

        with use_composition_root(root_with(embedder=embedder, llm=llm)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
            response = ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        assert response.status_code == 200
        _system, prompt = llm.calls[-1]
        assert "Relevant earlier" not in prompt


class RelevanceCutOffTests:
    """IR-446: recall offers Turns as relevant, so it must stop offering
    them when none are."""

    def _conversation_about_flooding_then_a_question_about_ponds(
        self, embedder, space, client_for, llm
    ):
        """Turn 1 is about flooding and has aged out; the follow-up resolves
        to a pond question, which is about nothing in the Conversation."""
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        make_record(title="Tilapia Ponds", text=POND_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]
        resolver = QuestionResolver(llm=ScriptedLLM(reply=POND_QUESTION), cache={})
        root = root_with(embedder=embedder, llm=llm, resolver=resolver)

        with use_composition_root(root):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
            _fill_past_the_recent_window(client, conversation_id)
            response = ask(client, POND_QUESTION, conversation_id=conversation_id)
        return response

    def test_no_turn_clearing_the_cut_off_leaves_the_heading_out_entirely(
        self, embedder, space, client_for
    ):
        llm = ScriptedLLM()

        response = self._conversation_about_flooding_then_a_question_about_ponds(
            embedder, space, client_for, llm
        )

        assert response.status_code == 200
        _system, prompt = llm.calls[-1]
        assert "Relevant earlier" not in prompt

    @override_settings(AI_MEMORY_RECALL_MAX_DISTANCE=2.0)
    def test_a_cut_off_loose_enough_to_admit_them_brings_the_heading_back(
        self, embedder, space, client_for
    ):
        """Pins the cause: the heading was absent above because of the
        cut-off, not because nothing was there to recall."""
        llm = ScriptedLLM()

        self._conversation_about_flooding_then_a_question_about_ponds(
            embedder, space, client_for, llm
        )

        _system, prompt = llm.calls[-1]
        assert "Relevant earlier in this conversation:" in prompt

    def test_no_distance_reaches_the_reader(self, embedder, space, client_for):
        """`apps/ai/presentation.py`'s rule: a score is never shown."""
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]
        root = root_with(embedder=embedder, resolver=_resolving_to_the_flood_question())

        with use_composition_root(root):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
            _fill_past_the_recent_window(client, conversation_id)
            response = ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        body = response.json()
        assert "distance" not in str(body)
        transcript = client.get(conversation_url(conversation_id)).json()
        assert "distance" not in str(transcript)


class BoundedPromptSizeTests:
    def test_the_prompt_does_not_grow_without_bound_over_a_long_conversation(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]
        llm = ScriptedLLM()

        with use_composition_root(root_with(embedder=embedder, llm=llm)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
            for i in range(20):
                ask(client, f"filler question number {i}", conversation_id=conversation_id)
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        _system, prompt = llm.calls[-1]
        from apps.ai.memory import MAX_RECALLED_TURNS

        assert prompt.count("\nQ: ") + (1 if prompt.startswith("Q: ") else 0) <= (
            MAX_HISTORY_TURNS + MAX_RECALLED_TURNS
        )


class NoExtraVendorCallTests:
    def test_storing_a_turns_memory_vector_costs_no_extra_embed_call(
        self, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        provider = _CountingEmbedder(dimensions=DIMENSIONS)
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=provider, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(root_with(embedder=provider)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        assert provider.query_calls == 1

    def test_recall_itself_makes_no_embedding_call(self, space, client_for):
        reader = make_user("reader@cit.edu")
        provider = _CountingEmbedder(dimensions=DIMENSIONS)
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=provider, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(root_with(embedder=provider)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
            _fill_past_the_recent_window(client, conversation_id)
            provider.query_calls = 0
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        assert provider.query_calls == 1


class EmbeddingSpaceOwnershipTests:
    def test_a_turns_stored_vector_belongs_to_the_active_embedding_space(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(root_with(embedder=embedder)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        stored = TurnEmbedding.objects.get(turn__conversation_id=conversation_id)
        assert stored.space_id == space.pk

    def test_a_turn_vector_from_a_retired_space_is_never_recalled_against_a_current_one(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]
        llm = ScriptedLLM()

        with use_composition_root(root_with(embedder=embedder, llm=llm)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
            _fill_past_the_recent_window(client, conversation_id)

        retired = EmbeddingSpace.objects.create(
            model_id="retired-model", dimensions=embedder.dimensions,
            metric="cosine", state=EmbeddingSpaceState.RETIRED,
        )
        oldest = TurnEmbedding.objects.filter(
            turn__conversation_id=conversation_id
        ).order_by("turn_id").first()
        oldest.space = retired
        oldest.save(update_fields=["space"])

        with use_composition_root(root_with(embedder=embedder, llm=llm)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        _system, prompt = llm.calls[-1]
        assert "Relevant earlier" not in prompt


class DegradingWhenVectorsAreUnavailableTests:
    def test_a_vendor_outage_degrades_to_recent_turns_only_without_erroring(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(root_with(embedder=embedder)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
            _fill_past_the_recent_window(client, conversation_id)

        with use_composition_root(root_with(embedder=_BrokenEmbedder())):
            response = ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        assert response.status_code == 200


class SwitchedOffTests:
    @override_settings(AI_CONVERSATION_MEMORY_ENABLED=False)
    def test_memory_can_be_switched_off_independently(self, embedder, space, client_for):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]
        llm = ScriptedLLM()

        with use_composition_root(root_with(embedder=embedder, llm=llm)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
            _fill_past_the_recent_window(client, conversation_id)
            response = ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        assert response.status_code == 200
        _system, prompt = llm.calls[-1]
        assert "Relevant earlier" not in prompt
