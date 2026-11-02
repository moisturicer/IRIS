"""
The embargo decides what leaves, on every path to a vendor (ADR-052, IR-811).

These run the shipped gate on real rows: no test here injects `permits`, because
one that did could pass with the gate disconnected. A fake vendor stands at each
exit and records what reached it, so "refused" means the text never arrived.

Paths: indexing, the reranker, the answering model and the AI Overview. The last
two classes hold test data to the same gate, now IR-317's bypass is gone (IR-815).
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
from apps.ai.indexing import embed_active_chunk_set, embed_record_summary
from apps.ai.models import ChunkSet
from apps.ai.models.chunk import ChunkEmbedding
from apps.ai.models.embedding import RecordEmbedding
from apps.ai.overview.service import PROMPT_VERSION, generate_overview
from apps.ai.providers.fakes import DeterministicEmbeddingProvider, ScriptedLLM
from apps.ai.providers.ports import RerankedCandidate, Reranker
from apps.records.management.commands.load_corpus import DEFAULT_OWNER_EMAIL
from apps.records.management.commands.seed_demo import AT_RDCO_TITLE, PROPOSAL_AT_ADVISER_TITLE
from apps.records.models import Record

from .corpus import DIMENSIONS, FLOOD_QUESTION, FLOOD_TEXT, ask, make_record, make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def _stamps(*, until_days=None, released=False):
    now = timezone.now()
    stamps = {"embargo_answered_at": now}
    if until_days is not None:
        stamps["embargoed_until"] = timezone.localdate() + timedelta(days=until_days)
    if released:
        stamps["embargo_released_at"] = now
    return stamps


BLOCKED = {
    "never answered": lambda: {},
    "under embargo": lambda: _stamps(until_days=30),
    "its date is today": lambda: _stamps(until_days=0),
    "its date has passed": lambda: _stamps(until_days=-30),
}
ALLOWED = {
    "answered no": lambda: _stamps(),
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
    Record.objects.filter(pk=record.pk).update(dpa_accepted_at=timezone.now(), **stamps)
    record.refresh_from_db()
    return record


def _unindexed(record) -> Record:
    """As it stands after chunking, with its vectors still owed."""
    ChunkEmbedding.objects.filter(chunk__record=record).delete()
    RecordEmbedding.objects.filter(record=record).delete()
    return record


def _llm_received(llm, text) -> bool:
    return any(text in prompt for _, prompt in llm.calls)


def _ask_recording_vendors(embedder, reader, client_for):
    reranker, llm = _TransmittingReranker(), ScriptedLLM(reply="Rainfall gauges [1].")
    root = CompositionRoot(embedder=embedder, reranker=reranker, llm=llm)
    with use_composition_root(root):
        response = ask(client_for(reader), FLOOD_QUESTION)
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
                embargoed_until=timezone.localdate() + timedelta(days=30),
                embargo_released_at=None,
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
