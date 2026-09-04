"""Tests for the context-path decorator (IR-112).

Runs against every registered strategy, wrapped, plus decorator-specific
truncation and no-heading behaviour.
"""

from hypothesis import HealthCheck, given, settings, strategies as st

from apps.ai.chunking import (
    ChunkingOptions,
    DocumentElement,
    NormalizedDocument,
    build_chunker,
    build_context_path_chunker,
    registered_strategies,
)
from apps.ai.chunking.context_path import ContextPathChunker, _truncate_middle
from apps.ai.chunking.document import HEADING, PARAGRAPH
from apps.ai.chunking.tokens import count_tokens

ALL_STRATEGIES = sorted(registered_strategies())


def doc(*elements: DocumentElement, title: str = "A Thesis") -> NormalizedDocument:
    return NormalizedDocument(title=title, elements=tuple(elements))


# --------------------------------------------------------------------------
# Composition with every registered strategy
# --------------------------------------------------------------------------


def test_composes_with_every_registered_strategy():
    document = doc(
        DocumentElement(kind=HEADING, text="3 Methodology", level=1),
        DocumentElement(kind=PARAGRAPH, text="Samples were collected weekly."),
    )
    for strategy_id in ALL_STRATEGIES:
        options = ChunkingOptions(strategy=strategy_id, max_tokens=50)
        result = build_context_path_chunker(options).chunk(document, options)

        assert result.chunks
        for chunk in result.chunks:
            assert chunk.text.startswith("A Thesis")
            assert chunk.context_path


def test_wrapping_does_not_change_the_inner_strategys_id():
    options = ChunkingOptions(strategy="fixed-window", max_tokens=50)
    document = doc(DocumentElement(kind=PARAGRAPH, text="alpha beta gamma"))

    plain = build_chunker(options).chunk(document, options)
    wrapped = ContextPathChunker(build_chunker(options)).chunk(document, options)

    assert wrapped.strategy_id == plain.strategy_id


# --------------------------------------------------------------------------
# Content: embedded text vs. displayed content
# --------------------------------------------------------------------------


def test_embedded_text_begins_with_the_context_path_but_content_does_not():
    document = doc(
        DocumentElement(kind=HEADING, text="3 Methodology", level=1),
        DocumentElement(kind=HEADING, text="3.2 Sampling Procedure", level=2),
        DocumentElement(
            kind=PARAGRAPH,
            text="Samples were collected weekly from twelve ponds.",
        ),
        title="Optimization of Tilapia Feed Conversion",
    )
    options = ChunkingOptions(
        strategy="structural-markdown-v1", max_tokens=50, merge_short_siblings=False
    )
    result = build_context_path_chunker(options).chunk(document, options)

    chunk = result.chunks[-1]
    assert chunk.context_path == (
        "Optimization of Tilapia Feed Conversion",
        "3 Methodology",
        "3.2 Sampling Procedure",
    )
    assert chunk.text.startswith(
        "Optimization of Tilapia Feed Conversion > 3 Methodology > 3.2 Sampling Procedure"
    )
    assert "Optimization of Tilapia Feed Conversion" not in chunk.content
    assert "Samples were collected weekly" in chunk.content


def test_a_chunk_with_no_enclosing_heading_still_gets_a_valid_path():
    document = doc(DocumentElement(kind=PARAGRAPH, text="no heading precedes this"))
    options = ChunkingOptions(strategy="fixed-window", max_tokens=50)
    result = build_context_path_chunker(options).chunk(document, options)

    assert result.chunks[0].context_path == ("A Thesis",)


def test_context_path_participates_in_the_content_hash():
    doc_a = doc(
        DocumentElement(kind=HEADING, text="1 Intro", level=1),
        DocumentElement(kind=PARAGRAPH, text="same words here"),
    )
    doc_b = doc(
        DocumentElement(kind=HEADING, text="1 Different", level=1),
        DocumentElement(kind=PARAGRAPH, text="same words here"),
    )
    options = ChunkingOptions(strategy="fixed-window", max_tokens=50)
    chunker = build_context_path_chunker

    hash_a = chunker(options).chunk(doc_a, options).content_hash
    hash_b = chunker(options).chunk(doc_b, options).content_hash

    assert hash_a != hash_b


# --------------------------------------------------------------------------
# Truncation from the middle
# --------------------------------------------------------------------------


def test_truncate_middle_keeps_title_and_nearest_section():
    path = ("Thesis Title", "1 Chapter One", "1.1 Section", "1.1.2 Subsection")
    truncated = _truncate_middle(path, max_tokens=6)

    assert truncated[0] == "Thesis Title"
    assert truncated[-1] == "1.1.2 Subsection"
    assert "1 Chapter One" not in truncated
    assert count_tokens(" > ".join(truncated)) <= 6


def test_truncate_middle_is_a_noop_when_the_path_already_fits():
    path = ("Thesis Title", "1 Intro")
    assert _truncate_middle(path, max_tokens=48) == path


def test_context_path_never_exceeds_its_token_budget():
    document = doc(
        DocumentElement(
            kind=HEADING,
            text="A Very Long Heading With Quite A Few Words In It Indeed",
            level=1,
        ),
        DocumentElement(kind=PARAGRAPH, text="content"),
        title="An Extremely Long Thesis Title That Uses Many Words On Its Own",
    )
    options = ChunkingOptions(
        strategy="fixed-window", max_tokens=50, context_path_max_tokens=5
    )
    result = build_context_path_chunker(options).chunk(document, options)

    for chunk in result.chunks:
        assert count_tokens(" > ".join(chunk.context_path)) <= 5


# --------------------------------------------------------------------------
# Properties from B (IR-110) still hold with the decorator applied
# --------------------------------------------------------------------------

_words = st.text(
    alphabet=st.characters(min_codepoint=97, max_codepoint=122),
    min_size=1,
    max_size=12,
)
_paragraph = st.lists(_words, min_size=1, max_size=40).map(" ".join)
_document = st.lists(_paragraph, min_size=1, max_size=6).map(
    lambda ps: doc(*[DocumentElement(kind=PARAGRAPH, text=p) for p in ps])
)


@settings(max_examples=40, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(document=_document)
def test_property_no_content_is_lost_with_decorator_applied(document):
    options = ChunkingOptions(strategy="structural-markdown-v1", max_tokens=16)
    result = build_context_path_chunker(options).chunk(document, options)

    rejoined = " ".join(c.content for c in result.chunks).split()
    original = " ".join(e.text for e in document.elements).split()
    assert rejoined == original


@settings(max_examples=40, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(document=_document)
def test_property_decorated_chunking_is_deterministic(document):
    options = ChunkingOptions(strategy="structural-markdown-v1", max_tokens=16)

    first = build_context_path_chunker(options).chunk(document, options)
    second = build_context_path_chunker(options).chunk(document, options)

    assert first.chunks == second.chunks
    assert first.content_hash == second.content_hash


def test_empty_chunkset_is_passed_through_unchanged():
    options = ChunkingOptions(strategy="fixed-window", max_tokens=16)
    document = NormalizedDocument(title="Empty", elements=())

    result = build_context_path_chunker(options).chunk(document, options)

    assert result.chunks == ()
