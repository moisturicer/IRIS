"""Conversations through the HTTP boundary (IR-295).

The primary seam, the same one `test_ask_http.py` uses and for the same
reason: what a caller observes is a response. Whether a Turn was stored,
whether it comes back tomorrow, and — the part that matters most here —
whether anybody but the owner can reach it.

**The privacy assertions are the point of this file.** A Conversation is
private to its owner *including staff*, which is the opposite of the default
everywhere else in IRIS, so it is asserted against a staff caller explicitly
rather than left to follow from "scoped to request.user".

Driven with the deterministic provider fakes through the composition root, so
none of it needs a vendor account.
"""

import pytest
from django.urls import reverse

from apps.ai.composition import use_composition_root
from apps.ai.models import Conversation, Turn
from apps.records.models import Record
from core.enums import PipelineStatus
from core.permissions import ROLE_ADVISER, ROLE_IERC, ROLE_KTTO

from .corpus import (
    FLOOD_QUESTION,
    FLOOD_TEXT,
    _BrokenLLM,
    ask,
    make_record,
    make_user,
    root_with,
)

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def conversations_url():
    return reverse("ai-conversations")


def conversation_url(pk):
    return reverse("ai-conversation-detail", args=[pk])


def start(client, **body):
    return client.post(conversations_url(), body, format="json")


def _without_pk(response, pk):
    """A refusal with the caller's own id masked out, so two can be compared."""
    return str(response.json()).replace(str(pk), "<pk>")


# -- a Conversation that exists on the server ---------------------------------


class StartingAConversationTests:
    def test_a_conversation_is_created_for_the_caller_and_listed_back(
        self, client_for
    ):
        reader = make_user("reader@cit.edu")
        client = client_for(reader)

        created = start(client, title="Flooding")
        assert created.status_code == 201
        assert created.json()["title"] == "Flooding"
        assert created.json()["record"] is None

        listed = client.get(conversations_url()).json()
        assert [c["id"] for c in listed] == [created.json()["id"]]

    def test_a_conversation_can_be_scoped_to_a_record(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        flood = make_record(title="Flood Prediction", text=FLOOD_TEXT,
                            embedder=embedder, space=space)

        body = start(client_for(reader), record=flood.pk).json()

        assert body["record"] == flood.pk
        assert body["record_title"] == "Flood Prediction"

    def test_a_record_the_caller_cannot_read_cannot_be_scoped_to(
        self, embedder, space, client_for
    ):
        """Scoping to a hidden draft would confirm it exists, so the refusal
        is the same one a missing record gets."""
        author = make_user("author@cit.edu")
        stranger = make_user("stranger@cit.edu")
        hidden = make_record(title="Hidden Draft", text=FLOOD_TEXT, owner=author,
                             status=PipelineStatus.DRAFT, embedder=embedder,
                             space=space)

        refused = start(client_for(stranger), record=hidden.pk)
        missing = start(client_for(stranger), record=hidden.pk + 10_000)

        assert refused.status_code == missing.status_code == 400
        # Identical but for the id the caller supplied, which it already knew.
        # Anything else in the wording would be the existence check this
        # refusal exists to withhold.
        assert _without_pk(refused, hidden.pk) == _without_pk(
            missing, hidden.pk + 10_000
        )

    def test_an_anonymous_caller_cannot_list_or_start_one(self):
        from rest_framework.test import APIClient

        client = APIClient()
        assert client.get(conversations_url()).status_code in (401, 403)
        assert client.post(conversations_url(), {}, format="json").status_code in (
            401,
            403,
        )


# -- asking inside a conversation ---------------------------------------------


class AppendingTurnsTests:
    def test_asking_with_a_conversation_id_stores_the_question_and_answer(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(root_with(embedder=embedder)):
            answered = ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        assert answered.status_code == 200
        assert answered.json()["conversation_id"] == conversation_id

        turn, = client.get(conversation_url(conversation_id)).json()["turns"]
        assert turn["question"] == FLOOD_QUESTION
        assert turn["answer"] == answered.json()["answer"]
        assert turn["state"] == "generative"

    def test_a_stored_turn_keeps_the_citations_the_answer_used(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        flood = make_record(title="Flood Prediction", text=FLOOD_TEXT,
                            embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(root_with(embedder=embedder)):
            live = ask(client, FLOOD_QUESTION,
                       conversation_id=conversation_id).json()

        turn, = client.get(conversation_url(conversation_id)).json()["turns"]
        stored, = turn["citations"]
        live_citation, = live["citations"]
        assert stored["record_id"] == flood.pk
        assert stored["chunk_id"] == live_citation["chunk_id"]
        assert stored["page"] == 4
        assert stored["marker"] == 1

    def test_a_stored_citation_holds_no_passage_text(
        self, embedder, space, client_for
    ):
        """A stored citation is a pointer, never text (IR-294). Text frozen
        into history outlives the permission that allowed it."""
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(root_with(embedder=embedder)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        from apps.ai.models import TurnCitation

        stored, = TurnCitation.objects.all()
        assert "rainfall gauge" not in str(stored.__dict__)

    def test_a_citation_to_a_record_the_reader_can_no_longer_see_is_dropped(
        self, embedder, space, client_for
    ):
        """History cannot outlive permission. The Turn stays — the question
        was still asked — but the pointer into a now-unreadable Record does
        not come back."""
        reader = make_user("reader@cit.edu")
        flood = make_record(title="Flood Prediction", text=FLOOD_TEXT,
                            embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(root_with(embedder=embedder)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        Record.objects.filter(pk=flood.pk).update(
            pipeline_status=PipelineStatus.DRAFT
        )

        turn, = client.get(conversation_url(conversation_id)).json()["turns"]
        assert turn["citations"] == []
        assert turn["question"] == FLOOD_QUESTION

    def test_omitting_the_conversation_id_still_answers_and_stores_nothing(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder)):
            body = ask(client_for(reader), FLOOD_QUESTION).json()

        assert body["answer"]
        assert body["conversation_id"] is None
        assert Conversation.objects.count() == 0
        assert Turn.objects.count() == 0

    def test_asking_into_someone_elses_conversation_is_a_404(
        self, embedder, space, client_for
    ):
        owner = make_user("owner@cit.edu")
        stranger = make_user("stranger@cit.edu")
        conversation_id = start(client_for(owner)).json()["id"]

        with use_composition_root(root_with(embedder=embedder)):
            refused = ask(client_for(stranger), FLOOD_QUESTION,
                          conversation_id=conversation_id)

        assert refused.status_code == 404
        assert Turn.objects.count() == 0

    def test_asking_into_a_conversation_that_never_existed_is_the_same_404(
        self, embedder, space, client_for
    ):
        owner = make_user("owner@cit.edu")
        stranger = make_user("stranger@cit.edu")
        conversation_id = start(client_for(owner)).json()["id"]

        with use_composition_root(root_with(embedder=embedder)):
            client = client_for(stranger)
            refused = ask(client, FLOOD_QUESTION, conversation_id=conversation_id)
            missing = ask(client, FLOOD_QUESTION, conversation_id=conversation_id + 999)

        assert refused.status_code == missing.status_code == 404
        assert refused.json() == missing.json()

    def test_a_conversation_id_that_is_not_a_number_is_refused_not_a_500(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        with use_composition_root(root_with(embedder=embedder)):
            response = ask(client_for(reader), FLOOD_QUESTION,
                           conversation_id="not-an-id")
        assert response.status_code in (400, 404)

    def test_the_first_question_names_an_untitled_conversation(
        self, embedder, space, client_for
    ):
        """So a sidebar of conversations is findable without anyone naming
        each one by hand."""
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(root_with(embedder=embedder)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        assert client.get(
            conversation_url(conversation_id)
        ).json()["title"] == FLOOD_QUESTION


class ReplayingATurnTests:
    def test_a_turn_written_when_no_model_was_reachable_replays_as_unavailable(
        self, embedder, space, client_for
    ):
        """The stored state is the domain's, mapped to the wire on the way
        out — so a reopened transcript can never present "no model was
        reachable" as an answer somebody wrote."""
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(
            root_with(embedder=embedder, llm=_BrokenLLM())
        ):
            live = ask(client, FLOOD_QUESTION,
                       conversation_id=conversation_id).json()

        turn, = client.get(conversation_url(conversation_id)).json()["turns"]
        assert live["mode"] == turn["state"] == "unavailable"
        assert turn["answer"] is None
        assert turn["message"] == live["message"]

    def test_a_turn_that_found_nothing_replays_as_no_results(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(root_with(embedder=embedder)):
            live = ask(client, FLOOD_QUESTION,
                       conversation_id=conversation_id).json()

        turn, = client.get(conversation_url(conversation_id)).json()["turns"]
        assert live["mode"] == turn["state"] == "no_results"
        assert turn["answer"] is None
        assert turn["message"] == live["message"]


class LongConversationTests:
    def test_a_conversation_well_past_five_turns_succeeds(
        self, embedder, space, client_for
    ):
        """The live bug this ticket fixes as a side effect. The frontend sent
        the whole transcript as the question and the endpoint caps a question
        at 2,000 characters, so conversations died at roughly six turns. With
        history behind a conversation id, a question is just a question."""
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        # Each question is the length a real one is, so the *transcript* —
        # what the old client sent as the question — passes 2,000 characters
        # around turn six. That is the condition that used to fail, and
        # asserting on twelve short questions would not reproduce it.
        questions = [
            f"{FLOOD_QUESTION} {'detail ' * 40} follow-up {turn}"
            for turn in range(12)
        ]
        assert len(questions[0]) > 300

        with use_composition_root(root_with(embedder=embedder)):
            for turn, question in enumerate(questions):
                response = ask(client, question, conversation_id=conversation_id)
                assert response.status_code == 200, f"turn {turn} failed"

        body = client.get(conversation_url(conversation_id)).json()
        assert len(body["turns"]) == 12
        transcript = "".join(t["question"] + (t["answer"] or "")
                             for t in body["turns"])
        assert len(transcript) > 2 * 2000, (
            "the transcript must exceed the cap that used to be applied to it"
        )
        # In the order they were asked, so a reopened transcript reads as the
        # conversation that happened.
        assert [t["question"] for t in body["turns"]] == questions

    def test_the_question_length_guard_still_applies(self, client_for):
        """Kept as a plain abuse guard, which is all it was ever supposed to
        be — it stopped being load-bearing when history left the question."""
        reader = make_user("reader@cit.edu")
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        response = ask(client, "x" * 2001, conversation_id=conversation_id)
        assert response.status_code == 400


# -- the privacy property ------------------------------------------------------


class PrivacyTests:
    def test_a_conversation_is_unreachable_by_another_user(self, client_for):
        owner = make_user("owner@cit.edu")
        stranger = make_user("stranger@cit.edu")
        conversation_id = start(client_for(owner)).json()["id"]

        client = client_for(stranger)
        assert client.get(conversation_url(conversation_id)).status_code == 404
        assert client.patch(conversation_url(conversation_id), {"title": "mine"},
                            format="json").status_code == 404
        assert client.delete(conversation_url(conversation_id)).status_code == 404

    @pytest.mark.parametrize("role", [ROLE_KTTO, ROLE_IERC, ROLE_ADVISER])
    def test_staff_cannot_read_someone_elses_conversation(self, client_for, role):
        """Deliberately the opposite of the rest of IRIS. A transcript records
        what someone asked about confidential IP; staff seeing the Records is
        not staff seeing the questions."""
        owner = make_user("owner@cit.edu")
        staff = make_user(f"{role}@cit.edu", role_name=role)
        conversation_id = start(client_for(owner)).json()["id"]

        client = client_for(staff)
        assert client.get(conversation_url(conversation_id)).status_code == 404
        assert client.get(conversations_url()).json() == []

    def test_a_django_superuser_cannot_read_someone_elses_conversation(
        self, client_for
    ):
        """The other meaning of "staff". `is_superuser` opens the Django admin;
        it does not open a transcript."""
        owner = make_user("owner@cit.edu")
        superuser = make_user("root@cit.edu", role_name=None)
        superuser.is_staff = superuser.is_superuser = True
        superuser.save(update_fields=["is_staff", "is_superuser"])
        conversation_id = start(client_for(owner)).json()["id"]

        client = client_for(superuser)
        assert client.get(conversation_url(conversation_id)).status_code == 404
        assert client.get(conversations_url()).json() == []

    def test_a_refusal_does_not_confirm_the_conversation_exists(self, client_for):
        owner = make_user("owner@cit.edu")
        stranger = make_user("stranger@cit.edu")
        conversation_id = start(client_for(owner)).json()["id"]

        client = client_for(stranger)
        refused = client.get(conversation_url(conversation_id))
        missing = client.get(conversation_url(conversation_id + 999))

        assert refused.status_code == missing.status_code == 404
        assert refused.json() == missing.json()

    def test_a_listing_shows_only_the_callers_own_conversations(self, client_for):
        owner = make_user("owner@cit.edu")
        other = make_user("other@cit.edu")
        mine = start(client_for(owner), title="Mine").json()["id"]
        start(client_for(other), title="Theirs")

        listed = client_for(owner).get(conversations_url()).json()
        assert [c["id"] for c in listed] == [mine]


# -- keeping and discarding ----------------------------------------------------


class LifecycleTests:
    def test_a_conversation_can_be_renamed(self, client_for):
        reader = make_user("reader@cit.edu")
        client = client_for(reader)
        conversation_id = start(client, title="Untitled").json()["id"]

        renamed = client.patch(conversation_url(conversation_id),
                               {"title": "Flood work"}, format="json")

        assert renamed.status_code == 200
        assert renamed.json()["title"] == "Flood work"
        assert client.get(
            conversation_url(conversation_id)
        ).json()["title"] == "Flood work"

    def test_a_conversation_cannot_be_re_scoped_to_another_record(
        self, embedder, space, client_for
    ):
        """Rename is what IR-295 asks for. Re-scoping would change which
        Record's deletion takes the transcript with it."""
        reader = make_user("reader@cit.edu")
        first = make_record(title="Flood Prediction", text=FLOOD_TEXT,
                            embedder=embedder, space=space)
        second = make_record(title="Tilapia Ponds", text="pond sampling",
                             embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client, record=first.pk).json()["id"]

        client.patch(conversation_url(conversation_id),
                     {"record": second.pk}, format="json")

        assert Conversation.objects.get(pk=conversation_id).record_id == first.pk

    def test_the_owner_cannot_be_reassigned_by_renaming(self, client_for):
        """`user` is not a writable field — a PATCH carrying one must not be
        able to hand a transcript to somebody else."""
        owner = make_user("owner@cit.edu")
        stranger = make_user("stranger@cit.edu")
        client = client_for(owner)
        conversation_id = start(client).json()["id"]

        client.patch(conversation_url(conversation_id),
                     {"title": "t", "user": stranger.pk}, format="json")

        assert Conversation.objects.get(pk=conversation_id).user_id == owner.pk

    def test_deleting_a_conversation_removes_it_and_its_turns(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]
        with use_composition_root(root_with(embedder=embedder)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        assert client.delete(conversation_url(conversation_id)).status_code == 204
        assert client.get(conversation_url(conversation_id)).status_code == 404
        assert Turn.objects.count() == 0

    def test_deleting_a_record_deletes_the_conversations_scoped_to_it(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        flood = make_record(title="Flood Prediction", text=FLOOD_TEXT,
                            embedder=embedder, space=space)
        client = client_for(reader)
        scoped = start(client, record=flood.pk).json()["id"]
        unscoped = start(client).json()["id"]

        flood.delete()

        assert not Conversation.objects.filter(pk=scoped).exists()
        assert Conversation.objects.filter(pk=unscoped).exists()

    def test_a_two_year_old_conversation_is_still_there(self, client_for):
        """There is no automatic expiry and nothing may add one (IR-294
        §Privacy). Asserted against the clock rather than against the source,
        because what a user is promised is that it is still there — not that
        no module mentions retention."""
        from datetime import timedelta

        from django.utils import timezone

        reader = make_user("reader@cit.edu")
        client = client_for(reader)
        conversation_id = start(client, title="Old work").json()["id"]

        two_years_ago = timezone.now() - timedelta(days=730)
        Conversation.objects.filter(pk=conversation_id).update(
            created_at=two_years_ago, updated_at=two_years_ago
        )

        assert client.get(conversation_url(conversation_id)).status_code == 200
        assert [c["id"] for c in client.get(conversations_url()).json()] == [
            conversation_id
        ]
