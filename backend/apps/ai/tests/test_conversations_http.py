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
from apps.ai.answers.citations import GENERATED, NO_SOURCES, PARTIAL, UNAVAILABLE
from apps.ai.models import Conversation, Turn
from apps.records.models import Record
from core.permissions import ROLE_ADVISER, ROLE_IERC, ROLE_KTTO

from .corpus import (
    FLOOD_QUESTION,
    FLOOD_TEXT,
    POND_TEXT,
    make_record,
    make_user,
    root_with,
)

#: A question that only matches the pond corpus -- used to tell "this answer
#: came from the scoped record" apart from "this answer came from anywhere".
POND_QUESTION = "tilapia pond sampling procedure brackish water"

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def conversations_url():
    return reverse("ai-conversations")


def conversation_url(pk):
    return reverse("ai-conversation-detail", args=[pk])


class _Reply:
    """What the retired endpoints used to answer, built from stored rows (IR-957)."""

    def __init__(self, status_code, body):
        self.status_code, self._body = status_code, body

    def json(self):
        return self._body


def start(client, **body):
    """A Conversation for the signed-in caller. `POST /ai/conversations/` is gone,
    so this writes the row the way the old endpoint did."""
    user = client.handler._force_user
    record = Record.objects.filter(pk=body["record"]).first() if body.get("record") else None
    conversation = Conversation.objects.create(
        user=user, record=record, title=body.get("title", ""))
    return _Reply(201, {"id": conversation.pk, "title": conversation.title,
                        "record": conversation.record_id})


def ask(client, question, conversation_id, **_):
    """One answered Turn citing the first live chunk, as Django's answer path stored it."""
    from apps.ai.models import DocumentChunk, TurnCitation

    conversation = Conversation.objects.get(pk=conversation_id)
    chunk = DocumentChunk.objects.filter(deleted_at__isnull=True).order_by("pk").first()
    turn = Turn.objects.create(conversation=conversation, question=question,
                               answer="Rainfall gauges [1].", state="generated")
    TurnCitation.objects.create(turn=turn, marker=1, record_id=chunk.record_id,
                                chunk=chunk, page=chunk.source_page)
    return _Reply(200, {})


def _without_pk(response, pk):
    """A refusal with the caller's own id masked out, so two can be compared."""
    return str(response.json()).replace(str(pk), "<pk>")


# -- a Conversation that exists on the server ---------------------------------


class StartingAConversationTests:

    def test_listing_can_be_filtered_to_the_conversation_for_one_record(
        self, embedder, space, client_for
    ):
        """How Paper Chat finds the Conversation it already has for a paper,
        rather than starting a new one every time the panel opens (IR-298)."""
        reader = make_user("reader@cit.edu")
        flood = make_record(title="Flood Prediction", text=FLOOD_TEXT,
                            embedder=embedder, space=space)
        pond = make_record(title="Tilapia Ponds", text=POND_TEXT,
                           embedder=embedder, space=space)
        client = client_for(reader)
        for_flood = start(client, record=flood.pk).json()["id"]
        start(client, record=pond.pk)
        start(client)

        listed = client.get(conversations_url(), {"record": flood.pk}).json()

        assert [c["id"] for c in listed] == [for_flood]

    def test_the_record_filter_only_ever_narrows_the_callers_own_list(
        self, embedder, space, client_for
    ):
        owner = make_user("owner@cit.edu")
        other = make_user("other@cit.edu")
        flood = make_record(title="Flood Prediction", text=FLOOD_TEXT,
                            embedder=embedder, space=space)
        start(client_for(owner), record=flood.pk)

        listed = client_for(other).get(
            conversations_url(), {"record": flood.pk}
        ).json()

        assert listed == []

    def test_an_anonymous_caller_cannot_list_or_start_one(self):
        from rest_framework.test import APIClient

        client = APIClient()
        assert client.get(conversations_url()).status_code in (401, 403)
        assert client.post(conversations_url(), {}, format="json").status_code in (
            401,
            403,
        )


# -- asking inside a conversation ---------------------------------------------


# -- re-resolving a stored citation's quote (IR-299) ---------------------------


class CitationReResolutionTests:
    """A stored citation is a pointer (record, chunk, page). Reopening a
    transcript re-resolves it against the reader's *current* visibility and
    the chunk's *current* liveness, rather than replaying whatever was true
    when the Turn was written."""

    def test_a_citation_whose_chunk_was_tombstoned_by_rechunking_degrades_to_a_record_level_link(
        self, embedder, space, client_for
    ):
        """Re-chunking tombstones a chunk (`deleted_at`) rather than deleting
        the row (IR-115) -- so the pointer still resolves, but to content that
        no longer represents the record. Showing a reader that stale text
        would be worse than showing them nothing to quote at all."""
        from django.utils import timezone

        from apps.ai.models import DocumentChunk, TurnCitation

        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(root_with(embedder=embedder)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        citation = TurnCitation.objects.get()
        DocumentChunk.objects.filter(pk=citation.chunk_id).update(
            deleted_at=timezone.now()
        )

        turn, = client.get(conversation_url(conversation_id)).json()["turns"]
        stored, = turn["citations"]

        assert stored["record_id"] == citation.record_id
        assert stored["chunk_id"] == citation.chunk_id
        assert "text" not in stored
        assert "record_title" not in stored

    def test_rereading_a_conversation_costs_the_same_regardless_of_citation_count(
        self, embedder, space, client_for
    ):
        """Re-resolution reads two batched queries for the whole transcript
        (which records are visible, which chunks are live) -- never one pair
        per citation. Asserted by comparing query counts across a growing
        transcript rather than pinning an exact number, so this stays
        meaningful however many queries auth/session middleware happens to
        cost on a given day."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = start(client).json()["id"]

        with use_composition_root(root_with(embedder=embedder)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        with CaptureQueriesContext(connection) as one_turn:
            assert client.get(conversation_url(conversation_id)).status_code == 200

        with use_composition_root(root_with(embedder=embedder)):
            for _ in range(7):
                ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        with CaptureQueriesContext(connection) as eight_turns:
            body = client.get(conversation_url(conversation_id)).json()

        assert len(body["turns"]) == 8
        assert len(eight_turns.captured_queries) == len(one_turn.captured_queries)


class ReplayingATurnTests:
    """A Turn Django stored before IR-957 replays under its own state, never as an answer it was not.

    Django no longer writes Turns, so each is stored the way its answer path left it.
    """

    def _replayed(self, client_for, state, answer):
        client = client_for(make_user("reader@cit.edu"))
        conversation_id = start(client).json()["id"]
        stored = Turn.objects.create(conversation_id=conversation_id, question=FLOOD_QUESTION,
                                     answer=answer, state=state)
        turn, = client.get(conversation_url(conversation_id)).json()["turns"]
        return turn, stored

    def test_a_turn_written_when_no_model_was_reachable_replays_as_unavailable(self, client_for):
        turn, stored = self._replayed(client_for, UNAVAILABLE, "No answering model was reachable.")
        assert turn["state"] == "unavailable"
        assert turn["answer"] is None
        assert turn["message"] == stored.answer

    def test_a_turn_that_found_nothing_replays_as_no_results(self, client_for):
        turn, _ = self._replayed(client_for, NO_SOURCES, "")
        assert turn["state"] == "no_results"
        assert turn["answer"] is None
        assert turn["message"]

    def test_a_partial_turn_replays_with_its_partial_flag_set(self, client_for):
        """The fragment rides in `message`, never `answer` (IR-328, IR-458)."""
        turn, stored = self._replayed(client_for, PARTIAL, "Rainfall gauges were")
        assert turn["state"] == "partial"
        assert turn["partial"] is True
        assert turn["answer"] is None
        assert turn["message"] == stored.answer

    def test_a_complete_turn_replays_with_no_partial_flag(self, client_for):
        turn, stored = self._replayed(client_for, GENERATED, "Rainfall gauges.")
        assert turn["partial"] is False
        assert turn["answer"] == stored.answer


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
