"""Ask IRIS through the HTTP boundary (IR-283).

The primary seam for this work, and deliberately the highest one available:
what a caller observes is a *response*, so that is what these assert. Which
passages come back, whether one the asker may not read is ever among them,
what the citation carries, and whether the response admits to degrading.

Driven with the deterministic provider fakes, injected through the composition
root. No vendor account, no network — which is the point: these include the
security assertions, and a security test that only runs where a paid API key
is configured is a security test that does not run.

The corpus builders live in `corpus.py` and the fixtures in `conftest.py`, so
the conversation suite drives the same ones (IR-295).
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.ai.composition import use_composition_root
from apps.ai.providers.fakes import ScriptedLLM
from core.enums import PipelineStatus

from .corpus import (
    DIMENSIONS,
    FLOOD_QUESTION,
    FLOOD_TEXT,
    POND_TEXT,
    _BrokenEmbedder,
    _BrokenLLM,
    ask,
    make_record,
    make_user,
    root_with,
    search,
)

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


# -- answering from inside the papers -----------------------------------------


class AskTests:
    def test_an_answer_is_grounded_in_passages_from_the_matching_record(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        flood = make_record(title="Flood Prediction", text=FLOOD_TEXT,
                            embedder=embedder, space=space)
        make_record(title="Tilapia Ponds", text=POND_TEXT,
                    embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder)):
            response = ask(client_for(reader), FLOOD_QUESTION)

        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "generative"
        assert body["degraded"] is False
        assert body["answer"]
        assert [c["record_id"] for c in body["citations"]] == [flood.pk]
        assert [s["id"] for s in body["sources"]][0] == flood.pk
        assert body["sources"][0]["title"] == "Flood Prediction"

    def test_the_question_is_answered_from_text_no_abstract_mentions(
        self, embedder, space, client_for
    ):
        """The reason this ticket exists. The abstract says nothing about
        rainfall gauges; the passage does, and it is what gets found."""
        reader = make_user("reader@cit.edu")
        record = make_record(title="Catchment Study", text=FLOOD_TEXT,
                             embedder=embedder, space=space)
        assert "rainfall" not in record.abstract

        llm = ScriptedLLM()
        with use_composition_root(root_with(embedder=embedder, llm=llm)):
            ask(client_for(reader), FLOOD_QUESTION)

        (_system, prompt), = llm.calls
        assert "rainfall gauge data" in prompt

    def test_a_blank_question_is_rejected_before_any_retrieval(self, client_for):
        reader = make_user("reader@cit.edu")
        assert ask(client_for(reader), "   ").status_code == 400

    def test_an_anonymous_caller_is_refused(self):
        assert APIClient().post(reverse("ai-ask"), {"question": "x"},
                                format="json").status_code in (401, 403)

    def test_response_style_reaches_the_system_prompt(self, embedder, space, client_for):
        """IR-332 -- the wording asked for actually reaches the model, not
        only a request field nobody reads."""
        reader = make_user("reader@cit.edu")
        make_record(title="Catchment Study", text=FLOOD_TEXT, embedder=embedder, space=space)

        llm = ScriptedLLM()
        with use_composition_root(root_with(embedder=embedder, llm=llm)):
            response = ask(client_for(reader), FLOOD_QUESTION, response_style="thorough")

        assert response.status_code == 200
        (system, _prompt), = llm.calls
        assert "headings and bullet points" in system

    def test_an_unrecognized_response_style_is_rejected(self, client_for):
        reader = make_user("reader@cit.edu")
        response = ask(client_for(reader), "x", response_style="shouting")
        assert response.status_code == 400

    def test_omitting_response_style_still_answers(self, embedder, space, client_for):
        """The default (`balanced`), not a required field a pre-IR-332
        caller would now be broken by omitting."""
        reader = make_user("reader@cit.edu")
        make_record(title="Catchment Study", text=FLOOD_TEXT, embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder)):
            response = ask(client_for(reader), FLOOD_QUESTION)

        assert response.status_code == 200


class PassagesOnTheWireTests:
    """IR-284: a citation says which sentence, and which page.

    The point of chunk-level retrieval from a reader's side. Asserted on the
    response rather than on the domain object, because a citation that never
    reaches the wire verifies nothing for anybody.
    """

    def test_a_citation_carries_its_record_page_and_quoted_passage(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        flood = make_record(title="Flood Prediction", text=FLOOD_TEXT,
                            embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder)):
            body = ask(client_for(reader), FLOOD_QUESTION).json()

        citation, = body["citations"]
        assert citation["marker"] == 1
        assert citation["record_id"] == flood.pk
        assert citation["record_title"] == "Flood Prediction"
        assert citation["page"] == 4
        assert citation["text"] == FLOOD_TEXT
        # The trail the chunk carried, so a reader can see which section a
        # quote came from without opening the paper.
        assert citation["context_path"] == ["Flood Prediction", "Methods"]

    def test_the_record_card_is_returned_alongside_the_passage(
        self, embedder, space, client_for
    ):
        """So the interface renders its existing card without a second
        request — which is what it does today, one fetch per citation."""
        reader = make_user("reader@cit.edu")
        flood = make_record(title="Flood Prediction", text=FLOOD_TEXT,
                            embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder)):
            body = ask(client_for(reader), FLOOD_QUESTION).json()

        source, = body["sources"]
        assert source["id"] == flood.pk
        assert source["title"] == "Flood Prediction"
        assert source["abstract"]
        assert source["authors"]

    def test_search_returns_the_same_passage_shape(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        flood = make_record(title="Flood Prediction", text=FLOOD_TEXT,
                            embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder)):
            body = search(client_for(reader), FLOOD_QUESTION).json()

        passage, = body["results"]
        assert passage["record_id"] == flood.pk
        assert passage["page"] == 4
        assert passage["text"] == FLOOD_TEXT
        assert passage["context_path"] == ["Flood Prediction", "Methods"]
        assert body["count"] == 1
        # Ranked retrieval carries the cards too, for the same reason the
        # answer does.
        assert [s["id"] for s in body["sources"]] == [flood.pk]

    def test_a_passage_from_an_unreadable_record_is_never_on_the_wire(
        self, embedder, space, client_for
    ):
        """Asserted here and not inherited from IR-283: the shape changed, and
        a filter that was right about record ids can still be wrong about the
        text those ids carry. This is the assertion that would catch a
        citation quoting a draft it must never quote."""
        author = make_user("author@cit.edu")
        stranger = make_user("stranger@cit.edu")
        make_record(title="Unpublished Flood Draft", text=FLOOD_TEXT, owner=author,
                    status=PipelineStatus.DRAFT, embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder)):
            client = client_for(stranger)
            answered = ask(client, FLOOD_QUESTION).json()
            searched = search(client, FLOOD_QUESTION).json()

        assert answered["citations"] == []
        assert answered["sources"] == []
        assert searched["results"] == []
        assert searched["sources"] == []
        # The text itself, not just the id: a payload that leaked the quote
        # while withholding the record would still be a disclosure.
        assert "rainfall gauge" not in str(answered)
        assert "rainfall gauge" not in str(searched)


# -- the security property ----------------------------------------------------


class VisibilityTests:
    def test_a_passage_from_an_unreadable_record_is_never_returned(
        self, embedder, space, client_for
    ):
        author = make_user("author@cit.edu")
        stranger = make_user("stranger@cit.edu")
        make_record(title="Unpublished Flood Draft", text=FLOOD_TEXT, owner=author,
                    status=PipelineStatus.DRAFT, embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder)):
            client = client_for(stranger)
            answered = ask(client, FLOOD_QUESTION).json()
            searched = search(client, FLOOD_QUESTION).json()

        assert answered["sources"] == []
        assert answered["citations"] == []
        assert answered["mode"] == "no_results"
        assert searched["results"] == []

    def test_a_readable_record_does_not_carry_its_unreadable_neighbour(
        self, embedder, space, client_for
    ):
        """The case that catches filtering after scoring rather than before."""
        author = make_user("author@cit.edu")
        stranger = make_user("stranger@cit.edu")
        public = make_record(title="Public Flood Study", text=FLOOD_TEXT,
                             embedder=embedder, space=space)
        make_record(title="Private Flood Study", text=FLOOD_TEXT, owner=author,
                    status=PipelineStatus.DRAFT, embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder)):
            body = search(client_for(stranger), FLOOD_QUESTION).json()

        assert [r["record_id"] for r in body["results"]] == [public.pk]
        assert [s["id"] for s in body["sources"]] == [public.pk]

    def test_a_refusal_is_indistinguishable_from_a_missing_record(
        self, embedder, space, client_for
    ):
        """Not "refused politely" — *identical*. A stranger asking about a
        draft they cannot read must not be able to tell it apart from asking
        about something nobody ever wrote."""
        author = make_user("author@cit.edu")
        stranger = make_user("stranger@cit.edu")

        with use_composition_root(root_with(embedder=embedder)):
            client = client_for(stranger)
            over_empty_corpus = ask(client, FLOOD_QUESTION).json()

            make_record(title="Unpublished Flood Draft", text=FLOOD_TEXT,
                        owner=author, status=PipelineStatus.DRAFT,
                        embedder=embedder, space=space)
            over_hidden_record = ask(client, FLOOD_QUESTION).json()

        assert over_hidden_record == over_empty_corpus

    def test_the_owner_of_a_draft_can_ask_about_their_own_work(
        self, embedder, space, client_for
    ):
        author = make_user("author@cit.edu")
        draft = make_record(title="My Flood Draft", text=FLOOD_TEXT, owner=author,
                            status=PipelineStatus.DRAFT, embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder)):
            body = ask(client_for(author), FLOOD_QUESTION).json()

        assert [s["id"] for s in body["sources"]] == [draft.pk]


# -- telling the truth about how the answer was produced ----------------------


class DegradationTests:
    def test_a_failing_vendor_produces_a_response_that_says_it_degraded(
        self, embedder, space, client_for
    ):
        """The assertion IR-279 exists to make, made where a reader would see
        it: through the HTTP layer, with the whole decorator stack in the way."""
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=_BrokenEmbedder())):
            client = client_for(reader)
            answered = ask(client, FLOOD_QUESTION).json()
            searched = search(client, FLOOD_QUESTION).json()

        assert answered["degraded"] is True
        assert answered["sources"], "full-text search still found the passage"
        # IR-277 story 5: a reader is *told*. What crosses the wire is the
        # fact, not a sentence — the sentence is the client's, because "weigh
        # this answer" and "weigh this summary" are different screens saying
        # one thing (`components/PassageQuote.DegradedNotice`, asserted in
        # `ChatMessageBubble.test.tsx`). The answer was still written: the
        # model was fine, only retrieval degraded.
        assert answered["answer"]
        assert answered["mode"] == "generative"
        assert searched["degraded"] is True
        assert [r["record_title"] for r in searched["results"]] == ["Flood Prediction"]

    def test_a_healthy_vendor_is_never_reported_as_degraded(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder)):
            body = search(client_for(reader), FLOOD_QUESTION).json()

        assert body["degraded"] is False

    def test_a_vendor_failure_never_fabricates_an_answer(
        self, embedder, space, client_for
    ):
        """ADR-008: no model, no answer. The sources are still returned,
        because retrieval worked — a reader gets passages to read themselves
        rather than a sentence nobody wrote."""
        reader = make_user("reader@cit.edu")
        flood = make_record(title="Flood Prediction", text=FLOOD_TEXT,
                            embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder, llm=_BrokenLLM())):
            body = ask(client_for(reader), FLOOD_QUESTION).json()

        assert body["answer"] is None
        assert body["mode"] == "unavailable"
        assert body["degraded"] is True
        assert body["message"]
        assert [s["id"] for s in body["sources"]] == [flood.pk]


# -- what the interface is told before anyone asks anything -------------------


class StatusTests:
    def test_status_reports_the_active_space_and_that_generation_is_configured(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder)):
            body = client_for(reader).get(reverse("ai-status")).json()

        assert body["embedding_space"]["id"] == space.pk
        assert body["embedding_space"]["model_id"] == space.model_id
        assert body["embedding_space"]["dimensions"] == DIMENSIONS
        assert body["generative"] is True
        assert body["indexed_records"] == 1
        assert "retrieval" not in body, "the hardcoded mode string is gone"

    def test_status_counts_only_records_the_asker_may_read(
        self, embedder, space, client_for
    ):
        author = make_user("author@cit.edu")
        stranger = make_user("stranger@cit.edu")
        make_record(title="Hidden Draft", text=FLOOD_TEXT, owner=author,
                    status=PipelineStatus.DRAFT, embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder)):
            body = client_for(stranger).get(reverse("ai-status")).json()

        assert body["indexed_records"] == 0


class CompositionRootTests:
    def test_the_default_root_is_restored_after_an_override(self, embedder):
        from apps.ai.composition import composition_root

        with use_composition_root(root_with(embedder=embedder)) as fake:
            assert composition_root() is fake

        # Back to a root that is not the fake, so the next caller gets the
        # real adapters rather than whichever fake a test left behind.
        assert composition_root() is not fake

    def test_an_override_is_undone_even_when_the_block_raises(self, embedder):
        from apps.ai.composition import composition_root

        fake = root_with(embedder=embedder)
        with pytest.raises(RuntimeError):
            with use_composition_root(fake):
                raise RuntimeError("boom")

        assert composition_root() is not fake
