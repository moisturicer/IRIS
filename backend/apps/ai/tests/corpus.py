"""The corpus the HTTP-boundary suites are driven against.

A module of its own rather than `conftest.py` (IR-295): these are helper
functions, not fixtures, and pytest discourages importing from a conftest.
Both `test_ask_http.py` and `test_conversations_http.py` build their records
here, so the two cannot drift into testing different corpora.
"""

from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.ai.composition import CompositionRoot
from apps.ai.models import VECTOR_COLUMN_DIMENSIONS
from apps.ai.models.chunk import ChunkEmbedding, ChunkSet, DocumentChunk
from apps.ai.models.embedding import RecordEmbedding
from apps.ai.providers.fakes import ScriptedLLM, ScriptedReranker
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.providers.ports import EmbeddingProvider, LLMProvider, StreamDelta
from apps.ai.resilience.circuit import CircuitOpen
from apps.records.models import Record, RecordOwner
from core.enums import PipelineStatus
from core.permissions import ROLE_STUDENT

User = get_user_model()

DIMENSIONS = VECTOR_COLUMN_DIMENSIONS

FLOOD_TEXT = (
    "we trained a convolutional neural network on rainfall gauge data to "
    "predict flooding in the Mananga catchment"
)
POND_TEXT = "sampling procedure for tilapia ponds stocked in brackish water"

FLOOD_QUESTION = "neural network rainfall flooding catchment"


# -- the corpus ---------------------------------------------------------------


# `space`, `embedder` and `client_for` live in this package's conftest, so
# the conversation suite drives the same corpus builder (IR-295).


def make_user(email, role_name=ROLE_STUDENT):
    from apps.accounts.models import Role

    role = Role.objects.get_or_create(name=role_name)[0] if role_name else None
    return User.objects.create_user(
        email=email, password="x", role=role, is_verified=True
    )


#: `page_sizes` for a letter-size page 4 -- `make_record`'s chunk is always
#: `source_page=4`, and `page_sizes` is keyed by page number as a string,
#: the same shape `apps.ai.extraction.docling_mapping._page_sizes` writes.
LETTER = {"4": [612.0, 792.0]}


def make_record(*, title, text, embedder, space, status=PipelineStatus.PUBLISHED,
                owner=None, bboxes=None, page_sizes=None, content_hash=None):
    """A record with one active chunk set, one chunk, and both vectors.

    Both, because retrieval is two-stage: the record vector is what stage 1
    ranks a record on, and without it the record is not a candidate and its
    chunks are never reached.

    `bboxes` and `page_sizes` default to none at all, which is the corpus a
    record with no recovered rectangles produces (IR-334) -- the case every
    other suite here is unaffected by. A test about highlighting passes both.
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
        options={}, content_hash=content_hash or f"c{title}", is_active=True,
        page_sizes=page_sizes or {},
    )
    chunk = DocumentChunk.objects.create(
        chunk_set=chunk_set, record=record, sequence=0, max_sequence=0,
        text=text, content=text, context_path=[title, "Methods"],
        token_count=len(text.split()), text_hash=f"t{record.pk}",
        source_page=4, element_kinds=["paragraph"], bboxes=bboxes or [],
    )
    ChunkEmbedding.objects.create(
        chunk=chunk, space=space, embedding=embedder.embed_documents([text])[0]
    )
    return record


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


class _CutOffLLM(LLMProvider):
    """A mid-sequence cutoff (IR-328): text arrives, then an ordinary
    exception -- not `LLMUnavailable`, which already ends in its own
    honest `done`."""

    def generate(self, system, user):
        raise NotImplementedError("this fake only exercises the streaming path")

    def stream(self, system, user):
        yield StreamDelta(text="Rainfall gauges feed the model [1]. ")
        raise RuntimeError("connection reset")


def root_with(embedder=None, llm=None, resolver=None):
    """A root whose vendors are fakes and whose disclosure gate allows.

    The gate is opened deliberately and explicitly. `Record` carries no
    embargo field yet (IR-250), so the real predicate refuses everything, and
    a test running under it would pass while asserting nothing — every
    assertion about what comes back would be satisfied by an empty list. The
    gate's own refusing behaviour is asserted in `apps/ai/policy/tests/`.

    `resolver` defaults to `None`, which is *not* "no resolution" — it falls
    through to `CompositionRoot`'s own settings-driven default, exactly as an
    unconfigured deployment would. No test here relies on that path actually
    calling a model: every question in this corpus is pronoun-free, so
    `has_back_reference` skips it regardless of what `resolver()` returns.
    Tests exercising resolution itself pass one explicitly (IR-296).
    """
    return CompositionRoot(
        embedder=embedder,
        reranker=ScriptedReranker(),
        llm=llm or ScriptedLLM(),
        resolver=resolver,
        permits=lambda record: True,
    )


def ask(client, question, **body):
    return client.post(reverse("ai-ask"), {"question": question, **body}, format="json")


def ask_stream(client, question, **body):
    return client.post(
        reverse("ai-ask-stream"), {"question": question, **body}, format="json"
    )


def search(client, query, **body):
    return client.post(reverse("ai-search"), {"query": query, **body}, format="json")


