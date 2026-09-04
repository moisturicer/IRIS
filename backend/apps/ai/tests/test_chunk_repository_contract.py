"""Contract suite for ChunkRepository (IR-89 F).

Runs identically against InMemoryChunkRepository and DjangoChunkRepository:
if they diverge, one of them is wrong, and this suite is what says so. Only
the Django case needs a database — parametrized cases carry their own
markers so the in-memory half always runs.
"""

import pytest

from apps.ai.chunking import Chunk, ChunkingOptions, ChunkSet, chunkset_hash
from apps.ai.chunking.document import BoundingBox
from apps.ai.repositories import InMemoryChunkRepository, DjangoChunkRepository


def _sample_chunk_set() -> ChunkSet:
    chunks = (
        Chunk(
            text="A Thesis > 1 Intro\n\nAlpha beta.",
            content="Alpha beta.",
            context_path=("A Thesis", "1 Intro"),
            sequence=0,
            token_count=2,
            source_page=1,
            element_kinds=frozenset({"paragraph"}),
            bboxes=(BoundingBox(page=1, left=0.0, top=0.0, right=10.0, bottom=10.0),),
        ),
        Chunk(
            text="A Thesis > 1 Intro\n\nGamma delta epsilon.",
            content="Gamma delta epsilon.",
            context_path=("A Thesis", "1 Intro"),
            sequence=1,
            token_count=3,
            source_page=1,
            element_kinds=frozenset({"paragraph"}),
            bboxes=(),
        ),
    )
    return ChunkSet(
        chunks=chunks,
        strategy_id="fixed-window",
        options=ChunkingOptions(max_tokens=50),
        content_hash=chunkset_hash(chunks),
    )


def _make_in_memory():
    return InMemoryChunkRepository(), 1


def _make_django():
    from apps.records.models import Record

    return DjangoChunkRepository(), Record.objects.create(title="A thesis").id


REPOSITORY_FACTORIES = [
    pytest.param(_make_in_memory, id="in-memory"),
    pytest.param(
        _make_django,
        id="django",
        marks=[pytest.mark.db_required, pytest.mark.django_db],
    ),
]


@pytest.mark.parametrize("make_repository", REPOSITORY_FACTORIES)
def test_get_active_returns_none_when_nothing_is_saved(make_repository):
    repo, record_id = make_repository()

    assert repo.get_active(record_id) is None


@pytest.mark.parametrize("make_repository", REPOSITORY_FACTORIES)
def test_a_chunk_set_round_trips_exactly(make_repository):
    repo, record_id = make_repository()
    original = _sample_chunk_set()

    repo.save(record_id=record_id, extraction_hash="hash-1", chunk_set=original)
    persisted = repo.get_active(record_id)

    assert persisted is not None
    assert persisted.record_id == record_id
    assert persisted.extraction_hash == "hash-1"
    assert persisted.chunk_set == original
    assert persisted.chunk_set.content_hash == original.content_hash


@pytest.mark.parametrize("make_repository", REPOSITORY_FACTORIES)
def test_saving_again_replaces_the_active_chunk_set(make_repository):
    repo, record_id = make_repository()
    first = _sample_chunk_set()
    repo.save(record_id=record_id, extraction_hash="hash-1", chunk_set=first)

    second_chunks = (
        Chunk(text="X", content="X", context_path=(), sequence=0, token_count=1),
    )
    second = ChunkSet(
        chunks=second_chunks,
        strategy_id="fixed-window",
        options=ChunkingOptions(max_tokens=50),
        content_hash=chunkset_hash(second_chunks),
    )
    repo.save(record_id=record_id, extraction_hash="hash-2", chunk_set=second)

    persisted = repo.get_active(record_id)
    assert persisted.chunk_set == second
    assert persisted.extraction_hash == "hash-2"


@pytest.mark.parametrize("make_repository", REPOSITORY_FACTORIES)
def test_an_empty_chunk_set_round_trips(make_repository):
    repo, record_id = make_repository()
    empty = ChunkSet(
        chunks=(), strategy_id="fixed-window", options=ChunkingOptions(), content_hash=chunkset_hash([])
    )

    repo.save(record_id=record_id, extraction_hash="hash-1", chunk_set=empty)
    persisted = repo.get_active(record_id)

    assert persisted.chunk_set.chunks == ()
    assert persisted.chunk_set.content_hash == empty.content_hash


@pytest.mark.parametrize("make_repository", REPOSITORY_FACTORIES)
def test_context_path_and_element_kinds_round_trip(make_repository):
    """These two fields are the ones most likely to silently degrade
    through a serialization layer: a tuple collapsing to a list changes
    nothing observable in a shallow equality check unless the value object
    itself enforces the type, which Chunk does not — so compare the
    specific values, not just chunk_set equality."""
    repo, record_id = make_repository()
    original = _sample_chunk_set()

    repo.save(record_id=record_id, extraction_hash="hash-1", chunk_set=original)
    persisted = repo.get_active(record_id)

    first = persisted.chunk_set.chunks[0]
    assert first.context_path == ("A Thesis", "1 Intro")
    assert isinstance(first.context_path, tuple)
    assert first.element_kinds == frozenset({"paragraph"})
    assert first.bboxes == (BoundingBox(page=1, left=0.0, top=0.0, right=10.0, bottom=10.0),)
