"""Contract tests for the chunker core.

These run against *every* registered strategy. A strategy that cannot satisfy
them is not a chunker, whatever else it does.

Nothing here touches Django, a database, the network, or the clock.
"""

import subprocess
import sys
import textwrap

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from apps.ai.chunking import (
    Chunk,
    ChunkingOptions,
    ChunkSet,
    DocumentElement,
    NormalizedDocument,
    UnknownChunkingStrategy,
    build_chunker,
    chunkset_hash,
    registered_strategies,
)
from apps.ai.chunking.tokens import count_tokens

# --------------------------------------------------------------------------
# Fixtures and generators
# --------------------------------------------------------------------------

ALL_STRATEGIES = sorted(registered_strategies())


def doc(*paragraphs: str, title: str = "A Thesis") -> NormalizedDocument:
    return NormalizedDocument(
        title=title,
        elements=tuple(
            DocumentElement(kind="paragraph", text=p) for p in paragraphs
        ),
    )


# Text that exercises the splitter without being pathological: real words,
# varied lengths, and no reliance on punctuation.
_words = st.text(
    alphabet=st.characters(min_codepoint=97, max_codepoint=122),
    min_size=1,
    max_size=12,
)
_paragraph = st.lists(_words, min_size=1, max_size=60).map(" ".join)
_document = st.lists(_paragraph, min_size=1, max_size=8).map(lambda ps: doc(*ps))


@pytest.fixture(params=ALL_STRATEGIES)
def strategy_id(request):
    return request.param


# --------------------------------------------------------------------------
# The port and the registry
# --------------------------------------------------------------------------


def test_at_least_one_strategy_is_registered():
    assert ALL_STRATEGIES, "no chunking strategy is registered"


def test_chunking_produces_a_chunkset(strategy_id):
    options = ChunkingOptions(strategy=strategy_id, max_tokens=20)
    result = build_chunker(options).chunk(doc("alpha beta gamma"), options)

    assert isinstance(result, ChunkSet)
    assert result.chunks
    assert all(isinstance(c, Chunk) for c in result.chunks)


def test_unknown_strategy_raises_and_names_the_known_ids():
    options = ChunkingOptions(strategy="no-such-strategy")

    with pytest.raises(UnknownChunkingStrategy) as excinfo:
        build_chunker(options)

    message = str(excinfo.value)
    assert "no-such-strategy" in message
    for known in ALL_STRATEGIES:
        assert known in message, "the error must name the strategies it knows"


def test_unknown_strategy_does_not_fall_back_to_a_default():
    """The gateway's provider wiring silently falls through to a mock adapter
    on an unrecognised name. That failure mode is not repeated here."""
    with pytest.raises(UnknownChunkingStrategy):
        build_chunker(ChunkingOptions(strategy="typo-in-the-config"))


def test_strategy_id_is_recorded_on_the_chunkset(strategy_id):
    options = ChunkingOptions(strategy=strategy_id, max_tokens=20)
    result = build_chunker(options).chunk(doc("alpha beta"), options)

    assert result.strategy_id == strategy_id


def test_the_port_performs_no_io(strategy_id):
    """A chunker that opens a socket or reads the clock is not a pure function.

    Guarding the socket module is enough to catch the class of mistake: any
    network access inside chunking fails loudly rather than being discovered
    in production.
    """
    import socket as socket_module

    options = ChunkingOptions(strategy=strategy_id, max_tokens=20)
    chunker = build_chunker(options)

    original = socket_module.socket

    def forbidden(*args, **kwargs):  # pragma: no cover - only runs on failure
        raise AssertionError("chunking must not open a socket")

    socket_module.socket = forbidden
    try:
        chunker.chunk(doc("alpha beta gamma delta"), options)
    finally:
        socket_module.socket = original


# --------------------------------------------------------------------------
# Value objects
# --------------------------------------------------------------------------


def test_chunks_are_immutable(strategy_id):
    options = ChunkingOptions(strategy=strategy_id, max_tokens=20)
    chunk = build_chunker(options).chunk(doc("alpha beta"), options).chunks[0]

    with pytest.raises(Exception):
        chunk.text = "mutated"


def test_options_are_immutable():
    options = ChunkingOptions()
    with pytest.raises(Exception):
        options.max_tokens = 9999


# --------------------------------------------------------------------------
# Properties every strategy must satisfy
# --------------------------------------------------------------------------


@settings(max_examples=60, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(document=_document, max_tokens=st.integers(min_value=4, max_value=40))
def test_property_token_ceiling_is_a_guarantee(strategy_id, document, max_tokens):
    options = ChunkingOptions(strategy=strategy_id, max_tokens=max_tokens)
    result = build_chunker(options).chunk(document, options)

    for chunk in result.chunks:
        assert chunk.token_count <= max_tokens
        assert count_tokens(chunk.content) <= max_tokens


@settings(max_examples=60, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(document=_document)
def test_property_chunking_is_deterministic(strategy_id, document):
    options = ChunkingOptions(strategy=strategy_id, max_tokens=16)
    chunker = build_chunker(options)

    first = chunker.chunk(document, options)
    second = chunker.chunk(document, options)

    assert first.chunks == second.chunks
    assert first.content_hash == second.content_hash


@settings(max_examples=60, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(document=_document)
def test_property_no_content_is_lost(strategy_id, document):
    """Concatenating every chunk's content in sequence order reproduces the
    input, modulo whitespace.

    Both reference implementations have exception handlers that return the
    unchanged context on error, silently dropping a node. No example-based
    test finds that; this one does.
    """
    options = ChunkingOptions(strategy=strategy_id, max_tokens=16)
    result = build_chunker(options).chunk(document, options)

    rejoined = " ".join(c.content for c in result.chunks).split()
    original = " ".join(e.text for e in document.elements).split()

    assert rejoined == original


@settings(max_examples=40, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(document=_document)
def test_property_sequence_is_dense_and_ascending(strategy_id, document):
    options = ChunkingOptions(strategy=strategy_id, max_tokens=16)
    result = build_chunker(options).chunk(document, options)

    assert [c.sequence for c in result.chunks] == list(range(len(result.chunks)))


@settings(max_examples=40, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(document=_document)
def test_property_no_chunk_is_empty(strategy_id, document):
    options = ChunkingOptions(strategy=strategy_id, max_tokens=16)
    result = build_chunker(options).chunk(document, options)

    assert all(c.content.strip() for c in result.chunks)


# --------------------------------------------------------------------------
# The content hash
# --------------------------------------------------------------------------


def test_hash_is_stable_across_processes():
    """Determinism across runs is not enough: it must hold across processes.

    A hash built on Python's built-in hash() passes an in-process test and
    fails here, because PYTHONHASHSEED is randomised per process.
    """
    script = textwrap.dedent(
        """
        import sys
        sys.path.insert(0, sys.argv[1])
        from apps.ai.chunking import (
            ChunkingOptions, DocumentElement, NormalizedDocument, build_chunker,
        )
        options = ChunkingOptions(max_tokens=8)
        document = NormalizedDocument(
            title="A Thesis",
            elements=(
                DocumentElement(kind="paragraph", text="alpha beta gamma delta"),
                DocumentElement(kind="paragraph", text="epsilon zeta eta theta"),
            ),
        )
        print(build_chunker(options).chunk(document, options).content_hash)
        """
    )
    backend_dir = str(__import__("pathlib").Path(__file__).resolve().parents[4])

    runs = [
        subprocess.run(
            [sys.executable, "-c", script, backend_dir],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        for _ in range(2)
    ]

    assert runs[0] == runs[1]
    assert len(runs[0]) == 64, "expected a sha256 hex digest"


def test_hash_changes_when_text_changes():
    a = Chunk(text="alpha", content="alpha", context_path=("T",), sequence=0, token_count=1)
    b = Chunk(text="beta", content="beta", context_path=("T",), sequence=0, token_count=1)

    assert chunkset_hash([a]) != chunkset_hash([b])


def test_hash_changes_when_sequence_changes():
    a = Chunk(text="alpha", content="alpha", context_path=("T",), sequence=0, token_count=1)
    b = Chunk(text="alpha", content="alpha", context_path=("T",), sequence=1, token_count=1)

    assert chunkset_hash([a]) != chunkset_hash([b])


def test_hash_changes_when_context_path_changes():
    a = Chunk(text="alpha", content="alpha", context_path=("T", "1"), sequence=0, token_count=1)
    b = Chunk(text="alpha", content="alpha", context_path=("T", "2"), sequence=0, token_count=1)

    assert chunkset_hash([a]) != chunkset_hash([b])


def test_hash_ignores_token_count():
    """Token count moves when a tokenizer is upgraded. That is not a semantic
    change and must not mark the whole corpus stale."""
    a = Chunk(text="alpha", content="alpha", context_path=("T",), sequence=0, token_count=1)
    b = Chunk(text="alpha", content="alpha", context_path=("T",), sequence=0, token_count=99)

    assert chunkset_hash([a]) == chunkset_hash([b])


def test_adjacent_chunks_cannot_collide_with_one_joined_chunk():
    """Without a separator between chunks, ["ab", "c"] and ["a", "bc"] digest
    identically. The separator byte is what prevents that."""
    split_one = [
        Chunk(text="ab", content="ab", context_path=(), sequence=0, token_count=1),
        Chunk(text="c", content="c", context_path=(), sequence=1, token_count=1),
    ]
    split_two = [
        Chunk(text="a", content="a", context_path=(), sequence=0, token_count=1),
        Chunk(text="bc", content="bc", context_path=(), sequence=1, token_count=1),
    ]

    assert chunkset_hash(split_one) != chunkset_hash(split_two)


# --------------------------------------------------------------------------
# Failure behaviour
# --------------------------------------------------------------------------


def test_an_error_inside_chunking_raises_rather_than_returning_partial_output(strategy_id):
    """A strategy must not swallow an exception and return what it had so far.

    That is the content-loss bug both reference implementations carry.
    """

    class Exploding(str):
        def split(self, *args, **kwargs):
            raise RuntimeError("boom")

    document = NormalizedDocument(
        title="A Thesis",
        elements=(DocumentElement(kind="paragraph", text=Exploding("alpha beta")),),
    )
    options = ChunkingOptions(strategy=strategy_id, max_tokens=4)

    with pytest.raises(RuntimeError, match="boom"):
        build_chunker(options).chunk(document, options)


def test_empty_document_produces_an_empty_chunkset(strategy_id):
    options = ChunkingOptions(strategy=strategy_id, max_tokens=16)
    result = build_chunker(options).chunk(
        NormalizedDocument(title="Empty", elements=()), options
    )

    assert result.chunks == ()
    assert result.content_hash == chunkset_hash([])
