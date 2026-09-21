"""Follow-up resolution through the HTTP boundary (IR-296, ADR-026).

The same seam as `test_ask_http.py` and `test_conversations_http.py`, for the
same reason: what a caller observes is a response, and the cost guarantees
this ticket exists for — "the first Turn made no resolution call" — are
guarantees about what a caller pays, not about what a domain object does
internally.

Driven with the deterministic provider fakes through the composition root, so
none of it needs a vendor account. The resolver is a fresh `QuestionResolver`
over a `ScriptedLLM` in almost every test here, injected explicitly, so a
call count is asserted against a double built for that one test rather than
a shared fixture two tests could accidentally race on.
"""

import pytest
from django.test import override_settings
from django.urls import reverse

from apps.ai.composition import use_composition_root
from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.resolution import QuestionResolver

from .corpus import FLOOD_QUESTION, FLOOD_TEXT, _BrokenLLM, ask, make_record, make_user, root_with

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def conversation_url(pk):
    return reverse("ai-conversation-detail", args=[pk])


def start(client, **body):
    return client.post(reverse("ai-conversations"), body, format="json")

#: The pond record's own text carries the literal word a naive, unresolved
#: follow-up would search for — so a test that finds the *flood* record for
#: "what about its limitations?" is proof the resolved subject won, not a
#: coincidence of which record happened to rank first.
POND_TEXT_WITH_LIMITATIONS = (
    "sampling procedure for tilapia ponds stocked in brackish water, noting "
    "known limitations in oxygen control"
)


class ResolvingAFollowUpTests:
    def test_a_follow_up_retrieves_on_the_resolved_subject_not_the_literal_word(
        self, embedder, space, client_for
    ):
        """The reason this ticket exists. "limitations" is a word only the
        *other* paper's text contains; resolving to the flood paper's
        subject is what finds the right one anyway."""
        reader = make_user("reader@cit.edu")
        flood = make_record(
            title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space
        )
        make_record(
            title="Tilapia Ponds",
            text=POND_TEXT_WITH_LIMITATIONS,
            embedder=embedder,
            space=space,
        )
        client = client_for(reader)
        conversation_id = start(client).json()["id"]
        reply = (
            "What are the limitations of the neural network rainfall "
            "flooding catchment study?"
        )
        resolver = QuestionResolver(llm=ScriptedLLM(reply=reply), cache={})

        with use_composition_root(root_with(embedder=embedder, resolver=resolver)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
            follow_up = ask(
                client, "what about its limitations?", conversation_id=conversation_id
            )

        body = follow_up.json()
        assert body["resolved_question"] == reply
        assert [c["record_id"] for c in body["citations"]] == [flood.pk]

    def test_the_resolved_question_is_stored_on_the_turn_and_returned_on_replay(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]
        reply = "What are the limitations of the flood prediction study?"
        resolver = QuestionResolver(llm=ScriptedLLM(reply=reply), cache={})

        with use_composition_root(root_with(embedder=embedder, resolver=resolver)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
            ask(client, "what about its limitations?", conversation_id=conversation_id)

        turns = client.get(conversation_url(conversation_id)).json()["turns"]
        first_turn, follow_up_turn = turns
        assert first_turn["resolved_question"] is None
        assert follow_up_turn["question"] == "what about its limitations?"
        assert follow_up_turn["resolved_question"] == reply

    def test_a_failed_resolution_falls_back_to_the_raw_question_and_does_not_error(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]
        resolver = QuestionResolver(llm=_BrokenLLM(), cache={})

        with use_composition_root(root_with(embedder=embedder, resolver=resolver)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
            response = ask(
                client, "what about its limitations?", conversation_id=conversation_id
            )

        assert response.status_code == 200
        assert response.json()["resolved_question"] is None

        turns = client.get(conversation_url(conversation_id)).json()["turns"]
        assert turns[-1]["question"] == "what about its limitations?"
        assert turns[-1]["resolved_question"] is None


class NoUnnecessaryCallTests:
    """The cost guarantees ADR-026 Decision 8 exists for, pinned by call
    count rather than only by output — a resolver that happened to return
    `None` for the wrong reason would still pass an output-only assertion."""

    def test_the_first_turn_of_a_conversation_makes_no_resolution_call(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]
        resolver_llm = ScriptedLLM()
        resolver = QuestionResolver(llm=resolver_llm, cache={})

        with use_composition_root(root_with(embedder=embedder, resolver=resolver)):
            response = ask(
                client, "what about its limitations?", conversation_id=conversation_id
            )

        assert response.status_code == 200
        assert response.json()["resolved_question"] is None
        assert resolver_llm.calls == []

    def test_a_self_contained_follow_up_makes_no_resolution_call(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]
        resolver_llm = ScriptedLLM()
        resolver = QuestionResolver(llm=resolver_llm, cache={})

        with use_composition_root(root_with(embedder=embedder, resolver=resolver)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
            response = ask(
                client,
                "does the tilapia pond study mention oxygen control?",
                conversation_id=conversation_id,
            )

        assert response.status_code == 200
        assert response.json()["resolved_question"] is None
        assert resolver_llm.calls == []

    def test_omitting_the_conversation_id_never_calls_the_resolver(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        resolver_llm = ScriptedLLM()
        resolver = QuestionResolver(llm=resolver_llm, cache={})

        with use_composition_root(root_with(embedder=embedder, resolver=resolver)):
            body = ask(client_for(reader), "what about its limitations?").json()

        assert body["resolved_question"] is None
        assert resolver_llm.calls == []


class SwitchedOffTests:
    @override_settings(AI_QUESTION_RESOLUTION_ENABLED=False)
    def test_resolution_can_be_switched_off_independently(
        self, embedder, space, client_for
    ):
        """No resolver is injected here — the composition root must read
        the setting itself and skip resolution before it ever tries to
        build a real adapter, which would otherwise fail for want of a key."""
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(root_with(embedder=embedder)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
            response = ask(
                client, "what about its limitations?", conversation_id=conversation_id
            )

        assert response.status_code == 200
        assert response.json()["resolved_question"] is None
