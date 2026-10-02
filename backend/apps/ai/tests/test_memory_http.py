"""Conversation memory through the HTTP boundary (IR-297).

Same seam as `test_ask_http.py` and `test_resolution_http.py`: what a
caller observes is a response. Driven with the deterministic provider
fakes, no vendor account needed.
"""

import pytest
from django.test import override_settings
from django.urls import reverse

from apps.ai.answers.citations import NO_SOURCES
from apps.ai.composition import use_composition_root
from apps.ai.models import (
    TURN_ANSWER_VECTOR,
    TURN_QUESTION_VECTOR,
    VECTORS_PER_TURN,
    Turn,
    TurnEmbedding,
)
from apps.ai.models.embedding_space import EmbeddingSpace, EmbeddingSpaceState
from apps.ai.providers.fakes import DeterministicEmbeddingProvider, ScriptedLLM
from apps.ai.resilience.circuit import CircuitOpen
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


#: A fact that exists only in an answer. Shares no word with any question
#: asked in these tests -- see `test_memory.py` for why that matters to a
#: hashed-bag-of-words fake. Measured against this suite's other text with
#: the deterministic provider: 0.58 to the question below, ~1.00 to every
#: filler question, every filler answer and the Turn's own question.
_DISTINCTIVE_ANSWER = (
    "The Jordan frame bound is 0.37 under the separate-universe approach [1]."
)
_ASKING_ABOUT_IT = "which figure gave Jordan frame bound 0.37"


class _LLMWithOneDistinctiveAnswer(ScriptedLLM):
    """Answers the first question with `_DISTINCTIVE_ANSWER`, the rest blandly.

    `ScriptedLLM` replies with the same text every time, which cannot express
    the situation these tests are about: one Turn holding a fact, the rest of
    the Conversation holding nothing like it. With one reply for all of them
    every Turn would be equally recallable and the assertion would pass
    without meaning anything.
    """

    def __init__(self):
        super().__init__(reply="Nothing further to add [1].")
        self._answered_once = False

    def generate(self, system, user):
        if not self._answered_once:
            self._answered_once = True
            self.calls.append((system, user))
            return _DISTINCTIVE_ANSWER
        return super().generate(system, user)


def _resolving_to_the_question_about_the_answer():
    """Resolution runs on every follow-up since IR-445, so it has to be
    injected here rather than left to fall through.

    Without this the default resolver borrows the suite's `ScriptedLLM` and
    the *resolved* question becomes whatever that fake replies -- so
    retrieval and recall search for "Nothing further to add" instead of the
    question under test, and the test fails for a reason that is nothing to
    do with answer vectors. Resolving to the question as typed is the
    no-op this test wants.
    """
    return QuestionResolver(llm=ScriptedLLM(reply=_ASKING_ABOUT_IT), cache={})


class RecallingByTheAnswerTests:
    """IR-447 through HTTP: a reader gets back a fact only an answer stated.

    The acceptance criterion as a reader meets it, and a pair for the same
    reason the unit tests are a pair -- the switch is the only difference
    between the two tests, so what the second one misses is exactly what the
    answer vector contributes.
    """

    def _conversation_holding_the_fact(self, client, llm):
        """Turn 1 holds `_DISTINCTIVE_ANSWER`, then is pushed out of the
        verbatim window so only recall can reach it."""
        conversation_id = start(client).json()["id"]
        ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
        _fill_past_the_recent_window(client, conversation_id)
        return conversation_id

    def test_a_turn_whose_answer_holds_the_fact_is_recalled_by_it(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        llm = _LLMWithOneDistinctiveAnswer()

        root = root_with(
            embedder=embedder,
            llm=llm,
            resolver=_resolving_to_the_question_about_the_answer(),
        )

        with use_composition_root(root):
            conversation_id = self._conversation_holding_the_fact(client, llm)
            ask(client, _ASKING_ABOUT_IT, conversation_id=conversation_id)

        _system, prompt = llm.calls[-1]
        assert "Relevant earlier" in prompt
        assert "Jordan frame bound is 0.37" in prompt

    def test_the_same_fact_is_unreachable_with_the_answer_vector_off(
        self, embedder, space, client_for
    ):
        """The control: identical Conversation, identical question, question
        vectors only. This is what a reader got before IR-447 -- the Turn
        exists, holds the answer, and nothing can find it."""
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        llm = _LLMWithOneDistinctiveAnswer()

        root = root_with(
            embedder=embedder,
            llm=llm,
            resolver=_resolving_to_the_question_about_the_answer(),
        )

        with override_settings(AI_MEMORY_ANSWER_VECTOR_ENABLED=False):
            with use_composition_root(root):
                conversation_id = self._conversation_holding_the_fact(client, llm)
                ask(client, _ASKING_ABOUT_IT, conversation_id=conversation_id)

        _system, prompt = llm.calls[-1]
        assert "Jordan frame bound is 0.37" not in prompt


class AnswerVectorStorageTests:
    def test_the_stored_vector_is_the_answer_text_embedded_as_a_query(
        self, embedder, space, client_for
    ):
        """ADR-015 rule 3's documented exception, pinned where it is actually
        made: stored answer text goes through `embed_query`, so recall stays
        one ranked list. A future "fix" to `embed_documents` fails here."""
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]
        llm = ScriptedLLM()

        with use_composition_root(root_with(embedder=embedder, llm=llm)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        turn = Turn.objects.get(conversation_id=conversation_id)
        stored = TurnEmbedding.objects.get(turn=turn, kind=TURN_ANSWER_VECTOR)
        assert list(stored.embedding) == pytest.approx(
            embedder.embed_query(turn.answer)
        )
        assert list(stored.embedding) != pytest.approx(
            embedder.embed_documents([turn.answer])[0]
        )

    def test_the_switch_leaves_no_answer_vector_behind(
        self, embedder, space, client_for
    ):
        """Off restores pre-IR-447 storage exactly, not a null row."""
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with override_settings(AI_MEMORY_ANSWER_VECTOR_ENABLED=False):
            with use_composition_root(root_with(embedder=embedder)):
                ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        kinds = TurnEmbedding.objects.filter(
            turn__conversation_id=conversation_id
        ).values_list("kind", flat=True)
        assert list(kinds) == [TURN_QUESTION_VECTOR]

    def test_a_turn_that_found_nothing_is_not_embedded(
        self, embedder, space, client_for
    ):
        """`no_sources` puts an *explanation* in `answer`, not an answer.

        Embedding it would spend a vendor call per failure to make failures
        findable, and would offer text nobody wrote to a later prompt under
        the heading "Relevant earlier in this conversation".
        """
        reader = make_user("reader@cit.edu")
        # No record at all, so retrieval returns nothing and no model runs.
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(root_with(embedder=embedder)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        turn = Turn.objects.get(conversation_id=conversation_id)
        assert turn.state == NO_SOURCES
        assert not TurnEmbedding.objects.filter(
            turn=turn, kind=TURN_ANSWER_VECTOR
        ).exists()


class AnswerVectorFailureTests:
    """A vendor failure on the answer vector costs recall, never the Turn.

    The Turn is committed before the call is made, so there is nothing a
    failure here could roll back -- and the reader has already read the
    answer by the time it happens. ADR-008's degradation rule.
    """

    def test_a_failed_answer_embedding_still_answers_the_request(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(
            root_with(embedder=_FailsOnTheAnswerEmbedder(dimensions=DIMENSIONS))
        ):
            response = ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        assert response.status_code == 200
        assert response.json()["mode"] == "generative"

    def test_the_turn_is_still_stored_with_its_free_question_vector(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(
            root_with(embedder=_FailsOnTheAnswerEmbedder(dimensions=DIMENSIONS))
        ):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        turn = Turn.objects.get(conversation_id=conversation_id)
        assert turn.answer
        kinds = set(turn.embeddings.values_list("kind", flat=True))
        assert kinds == {TURN_QUESTION_VECTOR}


class _FailsOnTheAnswerEmbedder(DeterministicEmbeddingProvider):
    """Embeds the question, then breaks.

    Retrieval's call must succeed or the test would be about a degraded
    answer rather than about a lost memory vector -- so it is the *second*
    `embed_query`, the answer's, that raises.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._calls = 0

    def embed_query(self, text):
        self._calls += 1
        if self._calls > 1:
            raise CircuitOpen("vendor down")
        return super().embed_query(text)


class PerTurnEmbeddingCostTests:
    """What a Turn costs to store, now that it is not nothing (IR-447).

    **This class asserted the opposite until IR-447, and the change is
    deliberate.** It was written to ADR-026 §7's original claim -- that
    answer recall came for free because a question and its answer are a pair
    -- and pinned exactly one `embed_query` call per Turn. IR-444 reversed
    that decision after finding the claim was never measured, so the old
    assertion now describes a behaviour the ADR no longer asks for. The
    half of §7 that survived is the half still asserted below: the
    *question* vector is free, being retrieval's own vector stored rather
    than recomputed. Only the answer's is a new call.
    """

    def test_the_answer_vector_costs_exactly_one_extra_call(self, space, client_for):
        """One call, not two and not none -- measured as the difference the
        switch makes, so the question vector's own call cannot be mistaken
        for the answer's."""
        reader = make_user("reader@cit.edu")
        provider = _CountingEmbedder(dimensions=DIMENSIONS)
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=provider, space=space)
        client = client_for(reader)

        with use_composition_root(root_with(embedder=provider)):
            without = start(client).json()["id"]
            with override_settings(AI_MEMORY_ANSWER_VECTOR_ENABLED=False):
                ask(client, FLOOD_QUESTION, conversation_id=without)
            baseline = provider.query_calls

            provider.query_calls = 0
            with_vector = start(client).json()["id"]
            ask(client, FLOOD_QUESTION, conversation_id=with_vector)

        assert baseline == 1
        assert provider.query_calls == baseline + 1

    def test_the_question_vector_is_still_retrievals_own_and_not_re_embedded(
        self, space, client_for
    ):
        """§7's surviving half. Two calls for a Turn, never three: one to
        search the corpus and one for the answer. A third would mean the
        question had been embedded a second time to store it."""
        reader = make_user("reader@cit.edu")
        provider = _CountingEmbedder(dimensions=DIMENSIONS)
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=provider, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(root_with(embedder=provider)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        assert provider.query_calls == 2
        stored = TurnEmbedding.objects.get(
            turn__conversation_id=conversation_id, kind=TURN_QUESTION_VECTOR
        )
        assert list(stored.embedding) == pytest.approx(
            provider.embed_query(FLOOD_QUESTION)
        )

    def test_recall_itself_makes_no_embedding_call(self, space, client_for):
        """Unchanged in intent, and the number it pins moved from 1 to 2 for
        the reason above: a Turn now embeds its question (for retrieval) and
        its answer. Recall still contributes nothing, which is what a third
        call would have revealed."""
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

        assert provider.query_calls == 2


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

        # Every vector a Turn holds, not "the" one: a Turn carries two since
        # IR-447 and `get()` raised `MultipleObjectsReturned` here. Asserting
        # over all of them is also the stronger claim -- the answer vector is
        # subject to the same space rule as the question vector, and a `get()`
        # filtered to one kind would have stopped checking the other.
        stored = TurnEmbedding.objects.filter(turn__conversation_id=conversation_id)
        assert stored.count() == VECTORS_PER_TURN
        assert {row.kind for row in stored} == {TURN_QUESTION_VECTOR, TURN_ANSWER_VECTOR}
        assert {row.space_id for row in stored} == {space.pk}

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
        # Retire *every* vector of the oldest Turn, not the first row found.
        # Before IR-447 those were the same thing; now a Turn holds two, and
        # moving one left the other in the active space still recalling the
        # Turn -- so the test failed for a reason that had nothing to do with
        # what it asserts. The assertion itself is untouched.
        oldest_turn_id = (
            TurnEmbedding.objects.filter(turn__conversation_id=conversation_id)
            .order_by("turn_id")
            .values_list("turn_id", flat=True)
            .first()
        )
        TurnEmbedding.objects.filter(turn_id=oldest_turn_id).update(space=retired)

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
