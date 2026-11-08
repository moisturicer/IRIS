"""
The embargo decides what leaves, on every path to a vendor (ADR-052, IR-811).

These run the shipped gate on real rows: no test here injects `permits`, because
one that did could pass with the gate disconnected. A fake vendor stands at each
exit and records what reached it, so "refused" means the text never arrived.

Paths: indexing, the reranker, the answering model and the AI Overview. Later
classes hold test data to the same gate, now IR-317's bypass is gone (IR-815), and
the acts that change an embargo after submission, old chat answers included (IR-812).
"""

import importlib.util
from datetime import timedelta
from io import StringIO

import pytest
from django.apps import apps as django_apps
from django.conf import settings as django_settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.ai.composition import CompositionRoot, composition_root, use_composition_root
from apps.ai.answers.citations import GENERATED, Citation, GroundedAnswer
from apps.ai.conversations import record_turn
from apps.ai.history import recent_window, sendable_turns
from apps.ai.indexing import embed_active_chunk_set, embed_record_summary
from apps.ai.memory import ConversationMemory
from apps.ai.models import TURN_ANSWER_VECTOR, ChunkSet, Turn, TurnCitation, TurnEmbedding
from apps.ai.models.chunk import ChunkEmbedding
from apps.ai.models.embedding import RecordEmbedding, RecordSpaceEmbedding
from apps.ai.overview.service import PROMPT_VERSION, generate_overview
from apps.ai.providers.fakes import DeterministicEmbeddingProvider, ScriptedLLM
from apps.ai.providers.ports import RerankedCandidate, Reranker
from apps.ai.tasks import index_record
from apps.ai.turn_backfill import embed_turn_answer, plan_turns, turns_to_consider
from apps.records.management.commands.load_corpus import DEFAULT_OWNER_EMAIL
from apps.records.management.commands.seed_demo import AT_RDCO_TITLE, PROPOSAL_AT_ADVISER_TITLE
from apps.accounts.models import User
from apps.records.models import Record, RecordOwner
from core.enums import RoleName

from .corpus import (
    DIMENSIONS,
    FLOOD_QUESTION,
    FLOOD_TEXT,
    POND_QUESTION,
    POND_TEXT,
    ask,
    make_record,
    make_user,
)

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def _stamps(*, until_days=None, released=False):
    """A paper's embargo stamps. With nothing asked, it is embargoed with no date,
    which is how every paper starts (IR-882)."""
    now = timezone.now()
    stamps = {}
    if until_days is not None:
        stamps["embargoed_until"] = timezone.localdate() + timedelta(days=until_days)
        stamps["embargo_date_set_at"] = now
    if released:
        stamps.update(is_embargoed=False, embargo_released_at=now)
    return stamps


BLOCKED = {
    "never released": lambda: _stamps(),
    "under embargo": lambda: _stamps(until_days=30),
    "its date is today": lambda: _stamps(until_days=0),
    "its date has passed": lambda: _stamps(until_days=-30),
}
ALLOWED = {
    "released with no date": lambda: _stamps(released=True),
    "released before its date": lambda: _stamps(until_days=30, released=True),
    "released after its date": lambda: _stamps(until_days=-30, released=True),
}


@pytest.fixture(params=BLOCKED, ids=str)
def blocked(request):
    return BLOCKED[request.param]()


@pytest.fixture(params=ALLOWED, ids=str)
def allowed(request):
    return ALLOWED[request.param]()


class _RecordingEmbedder(DeterministicEmbeddingProvider):
    """Stands in for Voyage's embedding endpoints and records what reached them."""

    def __init__(self):
        super().__init__(dimensions=DIMENSIONS)
        self.sent = []

    def embed_documents(self, texts):
        self.sent.extend(texts)
        return super().embed_documents(texts)

    def embed_query(self, text):
        self.sent.append(text)
        return super().embed_query(text)

    def embed_document_chunks(self, documents):
        self.sent.extend(text for document in documents for text in document)
        return super().embed_document_chunks(documents)


class _TransmittingReranker(Reranker):
    """Stands in for Voyage's reranker. Declaring that it transmits is what makes
    reranking ask the gate at all."""

    transmits_externally = True

    def __init__(self):
        self.sent = []

    def rerank(self, query, candidates):
        self.sent.extend(candidates)
        return [
            RerankedCandidate(index=i, text=text, score=float(len(candidates) - i))
            for i, text in enumerate(candidates)
        ]


@pytest.fixture(autouse=True)
def _no_task_publish(monkeypatch):
    monkeypatch.setattr("apps.ai.overview.service._enqueue_overview", lambda *args: None)


@pytest.fixture
def reader(db):
    return make_user("way-out-reader@cit.edu")


def _paper(embedder, space, stamps) -> Record:
    """A published, consented paper with no IP mark: only its embargo decides."""
    record = make_record(title="Flood Study", text=FLOOD_TEXT, embedder=embedder, space=space)
    Record.objects.filter(pk=record.pk).update(ai_consent=True, **stamps)
    record.refresh_from_db()
    return record


def _unindexed(record) -> Record:
    """As it stands after chunking, with its vectors still owed."""
    ChunkEmbedding.objects.filter(chunk__record=record).delete()
    RecordEmbedding.objects.filter(record=record).delete()
    RecordSpaceEmbedding.objects.filter(record=record).delete()
    return record


def _llm_received(llm, text) -> bool:
    return any(text in prompt for _, prompt in llm.calls)


def _ask_recording_vendors(embedder, reader, client_for, question=FLOOD_QUESTION, **body):
    reranker, llm = _TransmittingReranker(), ScriptedLLM(reply="Rainfall gauges [1].")
    root = CompositionRoot(embedder=embedder, reranker=reranker, llm=llm)
    with use_composition_root(root):
        response = ask(client_for(reader), question, **body)
    assert response.status_code == 200, response.content
    return reranker, llm


class TestIndexing:
    def test_a_blocked_paper_sends_no_chunk(self, embedder, space, blocked):
        record = _unindexed(_paper(embedder, space, blocked))
        vendor = _RecordingEmbedder()

        outcome = embed_active_chunk_set(record.pk, provider=vendor)

        assert outcome.refused
        assert "embargo" in outcome.reason
        assert vendor.sent == []
        assert not ChunkEmbedding.objects.filter(chunk__record=record).exists()

    def test_a_blocked_paper_sends_no_title_or_abstract(self, embedder, space, blocked):
        record = _unindexed(_paper(embedder, space, blocked))
        vendor = _RecordingEmbedder()

        outcome = embed_record_summary(record.pk, provider=vendor)

        assert outcome.refused
        assert vendor.sent == []

    def test_an_allowed_paper_is_indexed(self, embedder, space, allowed):
        record = _unindexed(_paper(embedder, space, allowed))
        vendor = _RecordingEmbedder()

        chunks = embed_active_chunk_set(record.pk, provider=vendor)
        summary = embed_record_summary(record.pk, provider=vendor)

        assert not chunks.refused and not summary.refused
        assert FLOOD_TEXT in vendor.sent
        assert ChunkEmbedding.objects.filter(chunk__record=record).exists()


class TestAskIris:
    """The reranker and the model are asserted apart: each asks the gate for
    itself, and one refusing would otherwise hide the other letting text out."""

    def test_a_blocked_paper_reaches_neither_vendor(self, embedder, space, reader, client_for, blocked):
        _paper(embedder, space, blocked)

        reranker, llm = _ask_recording_vendors(embedder, reader, client_for)

        assert FLOOD_TEXT not in reranker.sent
        assert not _llm_received(llm, FLOOD_TEXT)

    def test_an_allowed_paper_reaches_both(self, embedder, space, reader, client_for, allowed):
        _paper(embedder, space, allowed)

        reranker, llm = _ask_recording_vendors(embedder, reader, client_for)

        assert FLOOD_TEXT in reranker.sent
        assert _llm_received(llm, FLOOD_TEXT)


class TestAiOverview:
    def _root(self, embedder, llm):
        return CompositionRoot(embedder=embedder, llm=llm)

    def _read(self, client, record):
        return client.get(reverse("ai-record-overview", args=[record.pk])).json()

    def test_a_blocked_paper_gets_no_overview(self, embedder, space, reader, client_for, blocked):
        record = _paper(embedder, space, blocked)
        llm = ScriptedLLM(reply="The study uses rainfall gauges [p. 4].")

        with use_composition_root(self._root(embedder, llm)):
            body = self._read(client_for(reader), record)

        assert body["state"] == "unavailable"
        assert llm.calls == []

    def test_the_worker_rechecks_a_paper_embargoed_after_it_was_queued(
        self, embedder, space, reader, client_for, allowed,
    ):
        """The gate is asked again in the worker, because it can change between
        a reader's request and the generation it queued."""
        record = _paper(embedder, space, allowed)
        llm = ScriptedLLM(reply="The study uses rainfall gauges [p. 4].")

        with use_composition_root(self._root(embedder, llm)):
            assert self._read(client_for(reader), record)["state"] == "generating"
            Record.objects.filter(pk=record.pk).update(
                is_embargoed=True, embargo_released_at=None,
                embargoed_until=timezone.localdate() + timedelta(days=30),
                embargo_date_set_at=timezone.now(),
            )
            chunk_set = ChunkSet.objects.get(record=record, is_active=True)
            generate_overview(record.pk, chunk_set.pk, chunk_set.content_hash, PROMPT_VERSION)

        assert llm.calls == []

    def test_an_allowed_paper_gets_one(self, embedder, space, reader, client_for, allowed):
        record = _paper(embedder, space, allowed)
        llm = ScriptedLLM(reply="The study uses rainfall gauges [p. 4].")
        client = client_for(reader)

        with use_composition_root(self._root(embedder, llm)):
            assert self._read(client, record)["state"] == "generating"
            chunk_set = ChunkSet.objects.get(record=record, is_active=True)
            generate_overview(record.pk, chunk_set.pk, chunk_set.content_hash, PROMPT_VERSION)
            body = self._read(client, record)

        assert body["state"] == "ready"
        assert _llm_received(llm, FLOOD_TEXT)


class TestTestData:
    """The answers that replaced IR-317's bypass, through the real gate (IR-815)."""

    @pytest.fixture
    def loaded(self, embedder, space):
        """A paper as `load_corpus` leaves it: nobody has answered for it."""
        record = make_record(title="Flood Study", text=FLOOD_TEXT, embedder=embedder, space=space)
        Record.objects.filter(pk=record.pk).update(added_by=make_user(DEFAULT_OWNER_EMAIL))
        return record

    def _mark(self):
        # Only around the command: with DEBUG on, a request wakes the debug toolbar.
        with override_settings(DEBUG=True):
            call_command("mark_corpus_cleared", stdout=StringIO())

    def test_a_loaded_paper_reaches_no_vendor_until_it_is_marked(
        self, loaded, embedder, reader, client_for,
    ):
        reranker, llm = _ask_recording_vendors(embedder, reader, client_for)
        assert FLOOD_TEXT not in reranker.sent
        assert not _llm_received(llm, FLOOD_TEXT)

        self._mark()

        reranker, llm = _ask_recording_vendors(embedder, reader, client_for)
        assert FLOOD_TEXT in reranker.sent
        assert _llm_received(llm, FLOOD_TEXT)

    def test_a_marked_paper_is_indexed(self, loaded):
        record = _unindexed(loaded)
        vendor = _RecordingEmbedder()
        self._mark()

        chunks = embed_active_chunk_set(record.pk, provider=vendor)
        summary = embed_record_summary(record.pk, provider=vendor)

        assert not chunks.refused and not summary.refused
        assert FLOOD_TEXT in vendor.sent

    def test_a_seeded_paper_is_indexed_and_the_embargoed_one_is_not(self, space):
        call_command("seed_demo", force=True, stdout=StringIO())
        ordinary = Record.objects.get(title=PROPOSAL_AT_ADVISER_TITLE)
        embargoed = Record.objects.get(title=AT_RDCO_TITLE)
        vendor = _RecordingEmbedder()

        assert not embed_record_summary(ordinary.pk, provider=vendor).refused
        assert embed_record_summary(embargoed.pk, provider=vendor).refused

        sent = " ".join(vendor.sent)
        assert ordinary.title in sent
        assert embargoed.title not in sent


class TestTheBypassIsGone:
    """IR-317's removal trigger was its own tests. These keep it removed."""

    def test_its_module_no_longer_exists(self):
        assert importlib.util.find_spec("apps.ai.policy.bypass") is None

    def test_its_command_no_longer_exists(self):
        with pytest.raises(CommandError, match="Unknown command"):
            call_command("index_with_disclosure_bypass", dry_run=True)

    def test_its_setting_is_not_declared(self):
        assert not hasattr(django_settings, "AI_DISCLOSURE_BYPASS_FOR_DEVELOPMENT")

    def test_the_status_no_longer_reports_it(self, reader, client_for, space):
        response = client_for(reader).get(reverse("ai-status"))

        assert response.status_code == 200, response.content
        assert "disclosure_bypass" not in response.json()

    def test_a_line_left_in_someones_env_opens_nothing(self, embedder, space):
        """A `.env` from before this change still says it. It must do nothing.

        Read off the default root, because the bypass worked by installing one at
        startup, and a test that installed its own would never see that.
        """
        record = _paper(embedder, space, {})

        with use_composition_root(None):
            with override_settings(DEBUG=True, AI_DISCLOSURE_BYPASS_FOR_DEVELOPMENT=True):
                django_apps.get_app_config("ai").ready()

            assert not composition_root().vendor_permits()(record)


def _embargo_set(client_for, record):
    """Set a date as RDCO, who may (ADR-052 §5 as amended for IR-882); owners can't."""
    rdco = User.objects.filter(email="way-out-rdco@cit.edu").first() or make_user(
        "way-out-rdco@cit.edu", RoleName.RDCO,
    )
    response = client_for(rdco).post(
        reverse("record-embargo-set", args=[record.pk]),
        {"embargoed_until": (timezone.localdate() + timedelta(days=90)).isoformat()},
        format="json",
    )
    assert response.status_code == 200, response.content
    return response.json()


class TestTheActsThroughTheRealGate:
    """IR-812. Nothing here injects `permits`, and the vendors are fakes at the exit."""

    @pytest.fixture
    def owner(self, db):
        return make_user("way-out-owner@cit.edu")

    def _owned(self, embedder, space, owner, stamps):
        record = _paper(embedder, space, stamps)
        RecordOwner.objects.create(record=record, user=owner, is_primary=True)
        return record

    def test_a_paper_refused_during_its_embargo_is_indexed_after_release(
        self, embedder, space, owner, client_for, monkeypatch, django_capture_on_commit_callbacks,
    ):
        adviser = make_user("way-out-adviser@cit.edu")
        record = _unindexed(self._owned(embedder, space, owner, _stamps(until_days=30)))
        Record.objects.filter(pk=record.pk).update(adviser=adviser)
        vendor = _RecordingEmbedder()
        monkeypatch.setattr("apps.ai.indexing.build_embedding_provider", lambda: vendor)
        monkeypatch.setattr(
            "apps.ai.tasks.index_record.delay",
            lambda record_id: index_record.apply(args=[record_id]).get(),
        )
        assert embed_active_chunk_set(record.pk, provider=vendor).refused
        assert vendor.sent == []

        with django_capture_on_commit_callbacks(execute=True):
            response = client_for(adviser).post(
                reverse("record-embargo-release", args=[record.pk]), {}, format="json",
            )

        assert response.status_code == 200, response.content
        assert FLOOD_TEXT in vendor.sent
        assert ChunkEmbedding.objects.filter(chunk__record=record).exists()
        assert RecordEmbedding.objects.filter(record=record).exists()

    def test_setting_one_stops_further_sending_and_says_what_left(
        self, embedder, space, owner, reader, client_for,
    ):
        record = self._owned(embedder, space, owner, _stamps(released=True))
        reranker, llm = _ask_recording_vendors(embedder, reader, client_for)
        assert FLOOD_TEXT in reranker.sent
        assert _llm_received(llm, FLOOD_TEXT)

        body = _embargo_set(client_for, record)

        assert "can't be recalled" in body["notice"]
        reranker, llm = _ask_recording_vendors(embedder, reader, client_for)
        assert FLOOD_TEXT not in reranker.sent
        assert not _llm_received(llm, FLOOD_TEXT)
        vendor = _RecordingEmbedder()
        _unindexed(record)
        assert embed_active_chunk_set(record.pk, provider=vendor).refused
        assert embed_record_summary(record.pk, provider=vendor).refused
        assert vendor.sent == []


class TestEarlierAnswersThatQuoteThePaper:
    """
    An answer quoting a paper is that paper's text. Once an embargo is set, it must
    not go back out as chat history, as recall or as a backfilled vector, while the
    reader keeps it in their own transcript. Each test first shows the Turn does go
    out while the paper is clear, so a pass can't come from an empty window.
    """

    @pytest.fixture
    def scene(self, embedder, space, reader, client_for):
        owner = make_user("quoted-owner@cit.edu")
        flood = _paper(embedder, space, _stamps(released=True))
        RecordOwner.objects.create(record=flood, user=owner, is_primary=True)
        pond = make_record(title="Pond Culture", text=POND_TEXT, embedder=embedder, space=space)
        Record.objects.filter(pk=pond.pk).update(ai_consent=True, **_stamps(released=True))
        RecordOwner.objects.create(record=pond, user=owner, is_primary=True)
        client = client_for(reader)
        conversation_id = client.post(reverse("ai-conversations"), {}, format="json").json()["id"]
        _ask_recording_vendors(embedder, reader, client_for, conversation_id=conversation_id)
        turn = Turn.objects.get(conversation_id=conversation_id)
        assert turn.citations.filter(record=flood).exists()
        return {
            "owner": owner, "flood": flood, "pond": pond, "turn": turn,
            "conversation": turn.conversation,
        }

    def _next_prompt_quotes_it(self, embedder, reader, client_for, scene) -> bool:
        _, llm = _ask_recording_vendors(
            embedder, reader, client_for, POND_QUESTION, conversation_id=scene["conversation"].pk,
        )
        assert llm.calls
        return _llm_received(llm, FLOOD_QUESTION)

    def test_chat_history_keeps_it_out_of_the_next_prompt(
        self, scene, embedder, reader, client_for,
    ):
        assert self._next_prompt_quotes_it(embedder, reader, client_for, scene)

        _embargo_set(client_for, scene["flood"])

        assert not self._next_prompt_quotes_it(embedder, reader, client_for, scene)

    def test_the_window_and_the_older_turns_drop_it(self, scene, reader, client_for, embedder):
        with use_composition_root(CompositionRoot(embedder=embedder)):
            turns = scene["conversation"].turns.all()
            assert [t.pk for t in recent_window(turns, user=reader)] == [scene["turn"].pk]
            assert [t.pk for t in sendable_turns(turns, reader)] == [scene["turn"].pk]

            _embargo_set(client_for, scene["flood"])

            assert recent_window(turns, user=reader) == []
            assert sendable_turns(turns, reader) == []

    def test_a_turn_citing_two_papers_stays_out_when_either_is_held(
        self, scene, reader, client_for, embedder,
    ):
        first = scene["turn"].citations.get()
        TurnCitation.objects.create(
            turn=scene["turn"], marker=2, record=scene["pond"],
            chunk=scene["pond"].document_chunks.get(), page=first.page,
        )
        turns = scene["conversation"].turns.all()
        with use_composition_root(CompositionRoot(embedder=embedder)):
            assert [t.pk for t in sendable_turns(turns, reader)] == [scene["turn"].pk]

            _embargo_set(client_for, scene["pond"])

            assert sendable_turns(turns, reader) == []

    def test_recall_drops_it(self, scene, space, embedder, client_for):
        query = embedder.embed_query(FLOOD_QUESTION)
        with use_composition_root(CompositionRoot(embedder=embedder)):
            recalled = ConversationMemory().recall(scene["conversation"], query, space.pk)
            assert scene["turn"].pk in [t.pk for t in recalled]

            _embargo_set(client_for, scene["flood"])

            recalled = ConversationMemory().recall(scene["conversation"], query, space.pk)
            assert scene["turn"].pk not in [t.pk for t in recalled]

    def test_the_backfill_skips_it(self, scene, space, client_for):
        TurnEmbedding.objects.filter(turn=scene["turn"], kind=TURN_ANSWER_VECTOR).delete()

        def planned():
            return plan_turns(
                turns_to_consider(), space_id=space.pk, space_model="m", cost_per_million=0.0,
            )

        assert [p.turn_id for p in planned().to_embed] == [scene["turn"].pk]

        _embargo_set(client_for, scene["flood"])

        plan = planned()
        assert plan.to_embed == []
        assert any("disclosure" in reason for reason in plan.skipped)

    def test_the_backfill_checks_again_right_before_it_sends(self, scene, space, client_for):
        """A run can be long, and planning isn't the moment of sending."""
        TurnEmbedding.objects.filter(turn=scene["turn"], kind=TURN_ANSWER_VECTOR).delete()
        vendor = _RecordingEmbedder()

        _embargo_set(client_for, scene["flood"])

        assert embed_turn_answer(scene["turn"], space_id=space.pk, embedder=vendor) is False
        assert vendor.sent == []
        assert not TurnEmbedding.objects.filter(
            turn=scene["turn"], kind=TURN_ANSWER_VECTOR,
        ).exists()

    def test_an_answer_finished_as_the_embargo_lands_is_not_embedded(
        self, scene, space, client_for,
    ):
        """The model had the paper already, and the answer vector is one more send."""
        chunk = scene["flood"].document_chunks.get()
        answer = GroundedAnswer(
            text="Rainfall gauges [1].",
            citations=(Citation(
                marker=1, chunk_id=chunk.pk, record_id=scene["flood"].pk,
                record_title=scene["flood"].title, source_page=chunk.source_page,
                text=FLOOD_TEXT, context_path=(),
            ),),
            state=GENERATED, embedding_space_id=space.pk,
        )
        vendor = _RecordingEmbedder()
        record_turn(scene["conversation"], "while it is clear", answer, embedder=vendor)
        assert "Rainfall gauges [1]." in vendor.sent

        _embargo_set(client_for, scene["flood"])

        vendor = _RecordingEmbedder()
        turn = record_turn(scene["conversation"], "as it lands", answer, embedder=vendor)
        assert vendor.sent == []
        assert not TurnEmbedding.objects.filter(turn=turn, kind=TURN_ANSWER_VECTOR).exists()

    def test_a_release_lets_it_back_in(self, scene, reader, client_for, embedder):
        adviser = make_user("quoted-adviser@cit.edu")
        Record.objects.filter(pk=scene["flood"].pk).update(adviser=adviser)
        _embargo_set(client_for, scene["flood"])

        response = client_for(adviser).post(
            reverse("record-embargo-release", args=[scene["flood"].pk]), {}, format="json",
        )

        assert response.status_code == 200, response.content
        with use_composition_root(CompositionRoot(embedder=embedder)):
            window = recent_window(scene["conversation"].turns.all(), user=reader)
        assert [t.pk for t in window] == [scene["turn"].pk]

    def test_the_reader_keeps_it_in_their_own_transcript(self, scene, reader, client_for):
        _embargo_set(client_for, scene["flood"])

        response = client_for(reader).get(
            reverse("ai-conversation-detail", args=[scene["conversation"].pk]),
        )

        assert response.status_code == 200, response.content
        assert FLOOD_QUESTION in response.content.decode()
        assert "Rainfall gauges" in response.content.decode()
