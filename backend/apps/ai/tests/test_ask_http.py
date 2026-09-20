"""Ask IRIS through the HTTP boundary (IR-283).

The primary seam for this work, and deliberately the highest one available:
what a caller observes is a *response*, so that is what these assert. Which
passages come back, whether one the asker may not read is ever among them,
what the citation carries, and whether the response admits to degrading.

Driven with the deterministic provider fakes, injected through the composition
root. No vendor account, no network — which is the point: these include the
security assertions, and a security test that only runs where a paid API key
is configured is a security test that does not run.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.models import VECTOR_COLUMN_DIMENSIONS
from apps.ai.models.chunk import ChunkEmbedding, ChunkSet, DocumentChunk
from apps.ai.models.embedding import RecordEmbedding
from apps.ai.models.embedding_space import EmbeddingSpace
from apps.ai.providers.fakes import (
    DeterministicEmbeddingProvider,
    ScriptedLLM,
    ScriptedReranker,
)
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.providers.ports import EmbeddingProvider, LLMProvider
from apps.ai.resilience.circuit import CircuitOpen
from apps.ai.views.chatbot import DEGRADED_MESSAGE
from apps.records.models import Record, RecordOwner
from core.enums import PipelineStatus
from core.permissions import ROLE_STUDENT

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

User = get_user_model()

DIMENSIONS = VECTOR_COLUMN_DIMENSIONS

FLOOD_TEXT = (
    "we trained a convolutional neural network on rainfall gauge data to "
    "predict flooding in the Mananga catchment"
)
POND_TEXT = "sampling procedure for tilapia ponds stocked in brackish water"

FLOOD_QUESTION = "neural network rainfall flooding catchment"


# -- the corpus ---------------------------------------------------------------


@pytest.fixture
def space(db):
    """The one active space. A test may not create a second — the database
    constraint forbids it, and so does the property it exists to protect."""
    existing = EmbeddingSpace.objects.filter(state="active").first()
    if existing is not None:
        return existing
    return EmbeddingSpace.objects.create(
        model_id="fake-test", dimensions=DIMENSIONS, metric="cosine", state="active"
    )


@pytest.fixture
def embedder():
    return DeterministicEmbeddingProvider(dimensions=DIMENSIONS)


def make_user(email, role_name=ROLE_STUDENT):
    from apps.accounts.models import Role

    role = Role.objects.get_or_create(name=role_name)[0] if role_name else None
    return User.objects.create_user(
        email=email, password="x", role=role, is_verified=True
    )


def make_record(*, title, text, embedder, space, status=PipelineStatus.PUBLISHED,
                owner=None):
    """A record with one active chunk set, one chunk, and both vectors.

    Both, because retrieval is two-stage: the record vector is what stage 1
    ranks a record on, and without it the record is not a candidate and its
    chunks are never reached.
    """
    record = Record.objects.create(
        title=title, abstract=f"An abstract for {title}.", pipeline_status=status
    )
    if owner is not None:
        RecordOwner.objects.create(record=record, user=owner, is_primary=True)

    RecordEmbedding.objects.create(
        record=record,
        embedding=embedder.embed_documents([f"{title}. {text}"])[0],
        model_name="fake-test",
    )
    chunk_set = ChunkSet.objects.create(
        record=record, extraction_hash=f"e{title}", strategy_id="s",
        options={}, content_hash=f"c{title}", is_active=True,
    )
    chunk = DocumentChunk.objects.create(
        chunk_set=chunk_set, record=record, sequence=0, max_sequence=0,
        text=text, content=text, context_path=[title, "Methods"],
        token_count=len(text.split()), text_hash=f"t{record.pk}",
        source_page=4, element_kinds=["paragraph"], bboxes=[],
    )
    ChunkEmbedding.objects.create(
        chunk=chunk, space=space, embedding=embedder.embed_documents([text])[0]
    )
    return record


# -- the composition root, with fakes in it -----------------------------------


class _BrokenEmbedder(EmbeddingProvider):
    """A vendor that is down, not a vendor that is wrong.

    Raises `CircuitOpen`, which is what the breaker in front of a real adapter
    raises once it has given up — the case ADR-008 says must degrade rather
    than fail.
    """

    @property
    def dimensions(self):
        return DIMENSIONS

    def embed_documents(self, texts):
        raise CircuitOpen("vendor down")

    def embed_document_chunks(self, documents):
        raise CircuitOpen("vendor down")

    def embed_query(self, text):
        raise CircuitOpen("vendor down")


class _BrokenLLM(LLMProvider):
    def generate(self, system, user):
        raise LLMUnavailable("429 rate limited")


def root_with(embedder=None, llm=None):
    """A root whose vendors are fakes and whose disclosure gate allows.

    The gate is opened deliberately and explicitly. `Record` carries no
    embargo field yet (IR-250), so the real predicate refuses everything, and
    a test running under it would pass while asserting nothing — every
    assertion about what comes back would be satisfied by an empty list. The
    gate's own refusing behaviour is asserted in `apps/ai/policy/tests/`.
    """
    return CompositionRoot(
        embedder=embedder,
        reranker=ScriptedReranker(),
        llm=llm or ScriptedLLM(),
        permits=lambda record: True,
    )


@pytest.fixture
def client_for():
    def _client(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    return _client


def ask(client, question, **body):
    return client.post(reverse("ai-ask"), {"question": question, **body}, format="json")


def search(client, query, **body):
    return client.post(reverse("ai-search"), {"query": query, **body}, format="json")


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
        assert body["citations"] == [flood.pk]
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

        assert [r["id"] for r in body["results"]] == [public.pk]

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
        # IR-277 story 5: a reader is *told*, not just a flag a client may
        # ignore. The answer was still written — the model was fine, only
        # retrieval degraded — so the note has to ride alongside it.
        assert answered["answer"]
        assert answered["message"] == DEGRADED_MESSAGE
        assert searched["degraded"] is True
        assert searched["message"]
        assert [r["title"] for r in searched["results"]] == ["Flood Prediction"]

    def test_a_healthy_vendor_is_never_reported_as_degraded(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder)):
            body = search(client_for(reader), FLOOD_QUESTION).json()

        assert body["degraded"] is False
        assert body["message"] is None

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
