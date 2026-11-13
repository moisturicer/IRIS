"""Section keys are stored, read back, and filled in without re-embedding
(IR-1050). Needs a live Postgres; ``db_required`` skips it otherwise."""

import pytest

from apps.ai.chunking import ChunkingOptions, DocumentElement, NormalizedDocument, build_chunker
from apps.ai.chunking.document import HEADING, PARAGRAPH
from apps.ai.models.chunk import DocumentChunk
from apps.ai.repositories import DjangoChunkRepository, _deserialize_options
from apps.records.models import Record

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def _chunk_set():
    document = NormalizedDocument(
        title="T",
        elements=(
            DocumentElement(kind=HEADING, text="1 Intro", level=1),
            DocumentElement(kind=PARAGRAPH, text="alpha beta gamma."),
            DocumentElement(kind=HEADING, text="2 Methods", level=1),
            DocumentElement(kind=PARAGRAPH, text="delta epsilon zeta."),
        ),
    )
    options = ChunkingOptions(strategy="structural-markdown-v1")
    return build_chunker(options).chunk(document, options)


def test_section_keys_round_trip():
    record = Record.objects.create(title="Keys")
    repository = DjangoChunkRepository()
    repository.save(record_id=record.id, extraction_hash="h", chunk_set=_chunk_set())

    stored = repository.get_active(record.id).chunk_set.chunks
    assert [c.section_key for c in stored] == [("T", "1 Intro"), ("T", "2 Methods")]


def test_an_unchanged_rechunk_fills_missing_keys_and_embeds_nothing():
    record = Record.objects.create(title="Backfill")
    repository = DjangoChunkRepository()
    chunk_set = _chunk_set()
    repository.save(record_id=record.id, extraction_hash="h", chunk_set=chunk_set)
    DocumentChunk.objects.filter(record_id=record.id).update(section_key=None)

    outcome = repository.rechunk(record_id=record.id, extraction_hash="h", chunk_set=chunk_set)

    assert outcome.unchanged and outcome.to_embed_count == 0
    keys = list(DocumentChunk.objects.filter(record_id=record.id).order_by("sequence").values_list("section_key", flat=True))
    assert keys == [["T", "1 Intro"], ["T", "2 Methods"]]


def test_an_unchanged_rechunk_corrects_a_stale_key():
    record = Record.objects.create(title="Stale")
    repository = DjangoChunkRepository()
    chunk_set = _chunk_set()
    repository.save(record_id=record.id, extraction_hash="h", chunk_set=chunk_set)
    DocumentChunk.objects.filter(record_id=record.id).update(section_key=["T", "Old"])

    repository.rechunk(record_id=record.id, extraction_hash="h", chunk_set=chunk_set)

    keys = list(DocumentChunk.objects.filter(record_id=record.id).order_by("sequence").values_list("section_key", flat=True))
    assert keys == [["T", "1 Intro"], ["T", "2 Methods"]]


def test_options_stored_before_two_sizes_read_back_unchanged():
    options = _deserialize_options({"strategy": "structural-markdown-v1", "max_tokens": 900, "overlap_tokens": 0})
    assert (options.effective_target_tokens, options.max_tokens) == (900, 900)
    assert options.context_path_max_tokens == 64
