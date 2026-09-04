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


@pytest.mark.parametrize("make_repository", REPOSITORY_FACTORIES)
def test_page_sizes_round_trip_with_integer_keys(make_repository):
    """JSON object keys are strings; the repository must hand back the same
    int-keyed mapping the chunker produced, not the string-keyed one a naive
    JSONField round-trip would leave behind."""
    repo, record_id = make_repository()
    chunks = (Chunk(text="X", content="X", context_path=(), sequence=0, token_count=1),)
    original = ChunkSet(
        chunks=chunks,
        strategy_id="fixed-window",
        options=ChunkingOptions(max_tokens=50),
        content_hash=chunkset_hash(chunks),
        page_sizes={1: (612.0, 792.0), 2: (612.0, 792.0)},
    )

    repo.save(record_id=record_id, extraction_hash="hash-1", chunk_set=original)
    persisted = repo.get_active(record_id)

    assert persisted.chunk_set.page_sizes == {1: (612.0, 792.0), 2: (612.0, 792.0)}
    assert all(isinstance(k, int) for k in persisted.chunk_set.page_sizes)


# --- incremental re-chunking (IR-115 G) ---------------------------------
#
# The counts below are the contract, not an implementation detail: a caller
# decides how much of the token budget to spend from them, so the in-memory
# repository has to report the same plan the Django one acts on.


def _set_of(*texts: str) -> ChunkSet:
    chunks = tuple(
        Chunk(text=t, content=t, context_path=(), sequence=i, token_count=1)
        for i, t in enumerate(texts)
    )
    return ChunkSet(
        chunks=chunks,
        strategy_id="fixed-window",
        options=ChunkingOptions(),
        content_hash=chunkset_hash(chunks),
    )


@pytest.mark.parametrize("make_repository", REPOSITORY_FACTORIES)
def test_a_first_rechunk_has_nothing_to_reuse(make_repository):
    repo, record_id = make_repository()

    outcome = repo.rechunk(
        record_id=record_id, extraction_hash="h1", chunk_set=_set_of("a", "b")
    )

    assert outcome.unchanged is False
    assert outcome.to_embed_count == 2
    assert outcome.reused == 0


@pytest.mark.parametrize("make_repository", REPOSITORY_FACTORIES)
def test_rechunking_identical_content_is_a_no_op(make_repository):
    repo, record_id = make_repository()
    repo.rechunk(record_id=record_id, extraction_hash="h1", chunk_set=_set_of("a", "b"))

    outcome = repo.rechunk(
        record_id=record_id, extraction_hash="h1", chunk_set=_set_of("a", "b")
    )

    assert outcome.unchanged is True
    assert outcome.to_embed_count == 0
    assert outcome.to_embed == ()


@pytest.mark.parametrize("make_repository", REPOSITORY_FACTORIES)
def test_one_changed_chunk_is_the_only_one_to_embed(make_repository):
    repo, record_id = make_repository()
    repo.rechunk(record_id=record_id, extraction_hash="h1", chunk_set=_set_of("a", "b", "c"))

    outcome = repo.rechunk(
        record_id=record_id, extraction_hash="h2", chunk_set=_set_of("a", "B", "c")
    )

    assert outcome.to_embed_count == 1
    assert outcome.reused == 2
    assert [c.text for c in outcome.to_embed] == ["B"]


@pytest.mark.parametrize("make_repository", REPOSITORY_FACTORIES)
def test_a_removed_chunk_is_reported(make_repository):
    repo, record_id = make_repository()
    repo.rechunk(record_id=record_id, extraction_hash="h1", chunk_set=_set_of("a", "b"))

    outcome = repo.rechunk(
        record_id=record_id, extraction_hash="h2", chunk_set=_set_of("a")
    )

    assert outcome.soft_deleted == 1


@pytest.mark.parametrize("make_repository", REPOSITORY_FACTORIES)
def test_rechunk_makes_the_new_set_the_active_one(make_repository):
    repo, record_id = make_repository()
    repo.rechunk(record_id=record_id, extraction_hash="h1", chunk_set=_set_of("a"))

    repo.rechunk(record_id=record_id, extraction_hash="h2", chunk_set=_set_of("b"))

    active = repo.get_active(record_id)
    assert [c.text for c in active.chunk_set.chunks] == ["b"]
    assert active.extraction_hash == "h2"


@pytest.mark.parametrize("make_repository", REPOSITORY_FACTORIES)
def test_a_no_op_leaves_the_original_extraction_hash_in_place(make_repository):
    """The content hash is meaning; the extraction hash is provenance. A
    re-extraction that produces byte-identical chunks must cost nothing,
    which means it does not get to rewrite the row either."""
    repo, record_id = make_repository()
    repo.rechunk(record_id=record_id, extraction_hash="h1", chunk_set=_set_of("a"))

    repo.rechunk(record_id=record_id, extraction_hash="h2", chunk_set=_set_of("a"))

    assert repo.get_active(record_id).extraction_hash == "h1"


# --------------------------------------------------------------------------
# Degenerate regions (IR-113)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("make_repository", REPOSITORY_FACTORIES)
def test_a_degenerate_region_still_round_trips_as_a_bounding_box(make_repository):
    """The flag is a rendering hint written on the way out. It must not
    change the value the domain reads back, or the chunk would stop
    reporting the page it came from."""
    repo, record_id = make_repository()
    degenerate = BoundingBox(page=3, left=72.0, top=100.0, right=72.0, bottom=100.0)
    chunk_set = ChunkSet(
        chunks=(
            Chunk(
                text="A scanned line.",
                content="A scanned line.",
                context_path=(),
                sequence=0,
                token_count=3,
                source_page=3,
                bboxes=(degenerate,),
            ),
        ),
        strategy_id="structural-markdown-v1",
        options=ChunkingOptions(),
        content_hash="",
    )
    object.__setattr__(chunk_set, "content_hash", chunkset_hash(chunk_set.chunks))

    repo.save(record_id=record_id, extraction_hash="hash-1", chunk_set=chunk_set)
    persisted = repo.get_active(record_id)

    assert persisted.chunk_set.chunks[0].bboxes == (degenerate,)
