"""Failed and refused Turns leave the model's history (IR-448, ADR-026 §13).

The transcript recorded in IR-443 is the specification here, and it is driven
end to end rather than asserted a layer down: a good answer, then a refusal,
then a third question. Before this ticket the refusal became an ordinary ``A:``
line in both the resolution prompt and the answering prompt, so the model was
shown, verbatim, that it had already declined the subject -- which is exactly
how a Retry of the same question gets biased toward refusing again.

The seam is HTTP, like `test_memory_http.py` and `test_ask_http.py`, because
both filtered paths meet there and nowhere else: `_recent_turns` feeds the
rewriter *and* the answering prompt, and recall is reached through the answer
service. Driven with the deterministic provider fakes, no vendor account.

**Where the asymmetry is asserted.** Every exclusion test here is paired with
a read of the reopened transcript. ADR-026 §13's decision is not "drop failed
Turns", it is "the reader keeps them and the model does not", and a change
that quietly dropped them from the transcript too would satisfy half of these
assertions.
"""

import pytest
from django.urls import reverse

from apps.ai.answers.citations import (
    GENERATED,
    NO_SOURCES,
    PARTIAL,
    UNAVAILABLE,
)
from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.models import MODEL_HISTORY_STATES, Turn
from apps.ai.providers.fakes import ScriptedLLM, ScriptedReranker
from apps.ai.resolution import QuestionResolver

from .corpus import (
    FLOOD_QUESTION,
    FLOOD_TEXT,
    _BrokenLLM,
    _CutOffLLM,
    ask,
    ask_stream,
    make_record,
    make_user,
    root_with,
)

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

#: The sentence from the IR-443 transcript, shortened to what matters. The
#: real one is produced by the model, so what the tests below actually look
#: for is each failed Turn's *stored* `answer` -- this is here to say what
#: the stored text looks like, and is never asserted against directly.
_THE_OBSERVED_REFUSAL = (
    "The supplied sources do not contain any information about the "
    "separate-universe approach"
)

#: A third question with no topic of its own, like the one in IR-443. It is
#: the rewriter's job to give it one, which is why a refusal sitting in the
#: rewriter's history is not merely noise.
_FOLLOW_UP = "give me a longer explanation"


def start(client):
    return client.post(reverse("ai-conversations"), {}, format="json")


def transcript(client, conversation_id):
    return client.get(reverse("ai-conversation-detail", args=[conversation_id]))


def _recording_resolver():
    """A resolver whose model records what it was asked.

    It rewrites every follow-up to `FLOOD_QUESTION` so retrieval keeps
    working; `calls` is what the tests read.
    """
    return QuestionResolver(llm=ScriptedLLM(reply=FLOOD_QUESTION), cache={})


def _refusing_gate_root(embedder, llm=None):
    """A root whose disclosure gate permits nothing, so retrieval finds no
    readable sources and the answer is a refusal.

    `root_with` hardcodes a permitting gate -- deliberately, since every other
    suite needs one -- so this is built directly rather than widening a shared
    helper for one ticket. The gate is a realistic producer of `no_sources`:
    it is what refuses every record on a live deployment today (IR-250).
    """
    return CompositionRoot(
        embedder=embedder,
        reranker=ScriptedReranker(),
        llm=llm or ScriptedLLM(),
        resolver=None,
        permits=lambda record: False,
    )


def _states(conversation_id):
    return list(
        Turn.objects.filter(conversation_id=conversation_id)
        .order_by("id")
        .values_list("state", flat=True)
    )


class TheIR443TranscriptTests:
    """Good answer, refusal, third question -- the observed failure itself."""

    def test_the_refusal_reaches_neither_prompt(self, embedder, space, client_for):
        reader = make_user("reader@cit.edu")
        make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space
        )
        client = client_for(reader)
        conversation_id = start(client).json()["id"]
        answering_llm = ScriptedLLM()
        resolver = _recording_resolver()

        with use_composition_root(
            root_with(embedder=embedder, llm=answering_llm, resolver=resolver)
        ):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
        # Turn 2: the same question, nothing readable -- the refusal.
        with use_composition_root(_refusing_gate_root(embedder)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
        with use_composition_root(
            root_with(embedder=embedder, llm=answering_llm, resolver=resolver)
        ):
            ask(client, _FOLLOW_UP, conversation_id=conversation_id)

        assert _states(conversation_id) == [GENERATED, NO_SOURCES, GENERATED]
        refusal = Turn.objects.filter(
            conversation_id=conversation_id, state=NO_SOURCES
        ).get()
        assert refusal.answer, "the refusal must be stored, not merely absent"

        _system, answering_prompt = answering_llm.calls[-1]
        _system, resolution_prompt = resolver._llm.calls[-1]
        assert refusal.answer not in answering_prompt
        assert refusal.answer not in resolution_prompt
        # The good answer is still there -- this is a filter, not a reset.
        first = Turn.objects.filter(conversation_id=conversation_id).order_by("id")[0]
        assert f"Q: {first.question}" in answering_prompt
        assert f"Q: {first.question}" in resolution_prompt

    def test_the_reader_still_sees_the_refusal_in_the_reopened_transcript(
        self, embedder, space, client_for
    ):
        """The other half of §13. A reader who could not see their own failed
        question would be more confused, not less."""
        reader = make_user("reader@cit.edu")
        make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space
        )
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(root_with(embedder=embedder)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
        with use_composition_root(_refusing_gate_root(embedder)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        body = transcript(client, conversation_id).json()
        refusal = Turn.objects.filter(
            conversation_id=conversation_id, state=NO_SOURCES
        ).get()
        assert len(body["turns"]) == 2
        # A refused Turn replays as `answer: null` with the explanation in
        # `message` -- `presentation.answer_body`'s shape, unchanged by this
        # ticket, and the reason the reader's copy is not the stored text.
        replayed = [t for t in body["turns"] if t["id"] == refusal.pk]
        assert len(replayed) == 1
        assert replayed[0]["state"] == "no_results"
        assert replayed[0]["question"] == refusal.question
        assert replayed[0]["message"]


class EveryExcludedStateTests:
    """`no_sources`, `unavailable` and `partial`, each from its real producer.

    Writing the Turn straight through the ORM would pass against a `state`
    nothing ever writes. Each test here makes the state happen the way a
    reader does, then asks a further question and reads the prompt.
    """

    def _third_question_prompt(self, client, conversation_id, embedder):
        llm = ScriptedLLM()
        with use_composition_root(
            root_with(embedder=embedder, llm=llm, resolver=_recording_resolver())
        ):
            ask(client, _FOLLOW_UP, conversation_id=conversation_id)
        _system, prompt = llm.calls[-1]
        return prompt

    def test_an_unavailable_turn_leaves_the_history(
        self, embedder, space, client_for
    ):
        """No model was reachable (ADR-008), so `answer` holds the
        explanation IRIS wrote, not an answer anybody asked for."""
        reader = make_user("reader@cit.edu")
        make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space
        )
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(root_with(embedder=embedder, llm=_BrokenLLM())):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        assert _states(conversation_id) == [UNAVAILABLE]
        failed = Turn.objects.get(conversation_id=conversation_id)
        prompt = self._third_question_prompt(client, conversation_id, embedder)
        assert failed.answer not in prompt
        assert len(transcript(client, conversation_id).json()["turns"]) == 2

    def test_a_partial_turn_leaves_the_history(self, embedder, space, client_for):
        """**The judgement call this ticket names** (IR-448): `partial` is an
        interrupted stream, so unlike the other two it holds real content --
        it just stops mid-sentence (IR-328).

        It is excluded with them. A truncated answer shown as a prior answer
        teaches truncation: the model is given an example of stopping
        mid-thought and nothing in the prompt says the stop was a transport
        failure rather than a choice. The fragment is also the part of an
        answer least likely to carry what a follow-up needs, since what the
        stream never reached is exactly what is missing. The reader still has
        it, and Retry (ADR-026 §12, IR-398) is the path back to a whole answer.
        """
        reader = make_user("reader@cit.edu")
        make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space
        )
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(root_with(embedder=embedder, llm=_CutOffLLM())):
            response = ask_stream(
                client, FLOOD_QUESTION, conversation_id=conversation_id
            )
            # The cut-off propagates out of the iterator once the partial Turn
            # has been persisted -- the IR-328 shape, asserted in
            # `test_ask_stream_http.py` and only consumed here.
            with pytest.raises(RuntimeError):
                b"".join(response.streaming_content)

        assert _states(conversation_id) == [PARTIAL]
        cut_off = Turn.objects.get(conversation_id=conversation_id)
        assert cut_off.answer, "the fragment is stored -- that is the point"
        prompt = self._third_question_prompt(client, conversation_id, embedder)
        assert cut_off.answer not in prompt
        assert len(transcript(client, conversation_id).json()["turns"]) == 2


class AConversationOfNothingButFailuresTests:
    def test_a_follow_up_after_only_a_refusal_behaves_as_a_first_turn(
        self, embedder, space, client_for
    ):
        """With the one prior Turn excluded there is no history, and no
        history is the case resolution already skips (ADR-026 §8's first-Turn
        skip). So the rewriter is never called -- asserted as **zero** model
        calls, not as an unchanged question, because a resolver that ran and
        returned the question unchanged would look identical on the wire and
        would have spent the call this path exists to avoid.
        """
        reader = make_user("reader@cit.edu")
        make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space
        )
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(_refusing_gate_root(embedder)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        resolver = _recording_resolver()
        with use_composition_root(
            root_with(embedder=embedder, resolver=resolver)
        ):
            response = ask(client, _FOLLOW_UP, conversation_id=conversation_id)

        assert response.status_code == 200
        assert resolver._llm.calls == []
        assert response.json()["resolved_question"] is None

    def test_the_answering_prompt_carries_no_conversation_scaffolding(
        self, embedder, space, client_for
    ):
        """A first Turn's prompt has no `Conversation so far:` block at all,
        and a Conversation whose only Turn is a refusal must look the same --
        an empty block under that heading would be a worse prompt than none.
        """
        reader = make_user("reader@cit.edu")
        make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space
        )
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(_refusing_gate_root(embedder)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        llm = ScriptedLLM()
        with use_composition_root(root_with(embedder=embedder, llm=llm)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        _system, prompt = llm.calls[-1]
        assert "Conversation so far:" not in prompt


class OnePredicateTests:
    """The exclusion is one predicate, not two filters that can drift.

    The acceptance criterion is structural, so the test is too: it reads the
    one set and asserts both paths move with it. A test that only checked
    behaviour under today's set would pass a refactor that split the rule in
    two.
    """

    def test_both_paths_read_the_same_set_of_states(self):
        from apps.ai.models.conversation import model_history_q
        from apps.ai.models import Turn as TurnModel, TurnEmbedding

        turn_sql = str(TurnModel.objects.in_model_history().query)
        vector_sql = str(TurnEmbedding.objects.in_model_history().query)
        for state in MODEL_HISTORY_STATES:
            assert state in turn_sql
            assert state in vector_sql
        for state in (NO_SOURCES, UNAVAILABLE, PARTIAL):
            assert state not in turn_sql
            assert state not in vector_sql
        # The `Q` both queryset methods are built from, so a third caller
        # gets the rule rather than a third copy of it.
        assert model_history_q().children == [
            ("state__in", MODEL_HISTORY_STATES)
        ]
        assert model_history_q("turn__").children == [
            ("turn__state__in", MODEL_HISTORY_STATES)
        ]

    def test_the_embedding_exclusion_is_the_same_rule(self):
        """IR-447 skips the same states when embedding an answer, and since
        this ticket the two are literally one set: a state that is embedded
        and then filtered out of every prompt is a vendor call per failure
        buying nothing.
        """
        from apps.ai.conversations import _EMBEDDABLE_STATES

        assert _EMBEDDABLE_STATES is MODEL_HISTORY_STATES
