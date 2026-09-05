"""Tests specific to the structural splitting cascade (IR-111).

The shared contract suite in test_chunker_core.py already runs every
registered strategy — including this one — through the universal
properties (no content loss, determinism, dense sequencing, token
ceiling). These tests cover what is specific to structure-awareness: table
header repetition, list-item atomicity, section-scoped merging, and the
grapheme-safe hard split.
"""

from hypothesis import HealthCheck, given, settings, strategies as st

from apps.ai.chunking.document import (
    HEADING,
    LIST_ITEM,
    PARAGRAPH,
    TABLE_HEADER,
    TABLE_ROW,
    DocumentElement,
    NormalizedDocument,
)
from apps.ai.chunking.strategies.structural import STRATEGY_ID
from apps.ai.chunking.tokens import count_tokens
from apps.ai.chunking.values import ChunkingOptions


def build(*elements: DocumentElement, title: str = "A Thesis") -> NormalizedDocument:
    return NormalizedDocument(title=title, elements=tuple(elements))


def options(**overrides) -> ChunkingOptions:
    return ChunkingOptions(strategy=STRATEGY_ID, **overrides)


def chunker():
    from apps.ai.chunking.strategies.structural import StructuralCascadeChunker

    return StructuralCascadeChunker()


# --------------------------------------------------------------------------
# Heading-boundary sectioning
# --------------------------------------------------------------------------


def test_a_section_that_fits_is_emitted_as_one_chunk():
    document = build(
        DocumentElement(kind=HEADING, text="1 Introduction", level=1),
        DocumentElement(kind=PARAGRAPH, text="This is the introduction."),
    )
    result = chunker().chunk(document, options(max_tokens=50))

    assert len(result.chunks) == 1
    assert "Introduction" in result.chunks[0].content
    assert "introduction" in result.chunks[0].content


def test_separate_sections_never_share_a_chunk_when_both_fit_alone_but_not_together():
    document = build(
        DocumentElement(kind=HEADING, text="1 Introduction", level=1),
        DocumentElement(kind=PARAGRAPH, text="alpha beta gamma delta epsilon"),
        DocumentElement(kind=HEADING, text="2 Methodology", level=1),
        DocumentElement(kind=PARAGRAPH, text="zeta eta theta iota kappa"),
    )
    # max_tokens too small to hold both sections in one chunk, comfortably
    # holds each section alone.
    result = chunker().chunk(document, options(max_tokens=10, merge_short_siblings=False))

    contents = [c.content for c in result.chunks]
    assert any("Introduction" in c and "Methodology" not in c for c in contents)
    assert any("Methodology" in c and "Introduction" not in c for c in contents)


# --------------------------------------------------------------------------
# Table handling
# --------------------------------------------------------------------------


def _table_document(n_rows: int, cols_per_row: str = "a b c d") -> NormalizedDocument:
    elements = [DocumentElement(kind=TABLE_HEADER, text="Col1 Col2 Col3 Col4")]
    elements += [
        DocumentElement(kind=TABLE_ROW, text=f"r{i} {cols_per_row}")
        for i in range(n_rows)
    ]
    return build(*elements)


def test_a_table_split_across_chunks_repeats_its_header_in_every_fragment():
    document = _table_document(n_rows=40)
    result = chunker().chunk(document, options(max_tokens=20, merge_short_siblings=False))

    table_chunks = [c for c in result.chunks if TABLE_ROW in c.element_kinds]
    assert len(table_chunks) > 1, "the table must have actually been split"
    for chunk in table_chunks:
        assert "Col1" in chunk.content and "Col2" in chunk.content


def test_a_single_row_that_fits_with_the_header_is_not_split_further():
    document = _table_document(n_rows=1)
    result = chunker().chunk(document, options(max_tokens=50))

    assert len(result.chunks) == 1
    assert "Col1" in result.chunks[0].content
    assert "r0" in result.chunks[0].content


# --------------------------------------------------------------------------
# List handling
# --------------------------------------------------------------------------


def test_no_chunk_begins_or_ends_mid_list_item():
    items = [f"Step {i} do it now" for i in range(12)]
    document = build(*[DocumentElement(kind=LIST_ITEM, text=t) for t in items])

    result = chunker().chunk(document, options(max_tokens=8, merge_short_siblings=False))

    # Every item's full text must appear intact within a single chunk.
    for item in items:
        assert any(item in c.content for c in result.chunks), (
            f"list item split across chunks: {item!r}"
        )


def test_an_oversized_list_item_is_still_never_split_across_two_chunks_worth_of_siblings():
    """An item bigger than max_tokens gets its own chunk(s) via the sentence/
    word cascade, but never merges partial content from a sibling item."""
    huge_item = "word " * 30
    document = build(
        DocumentElement(kind=LIST_ITEM, text=huge_item.strip()),
        DocumentElement(kind=LIST_ITEM, text="short item"),
    )
    result = chunker().chunk(document, options(max_tokens=5, merge_short_siblings=False))

    assert any("short item" in c.content for c in result.chunks)
    assert not any(
        "short item" in c.content and "word" in c.content for c in result.chunks
    )


# --------------------------------------------------------------------------
# Section-scoped merging of short chunks
# --------------------------------------------------------------------------


def test_short_chunks_merge_within_a_section():
    """A run-type transition (heading/prose -> list -> prose) fragments the
    section into small windows even though the whole thing is short; merging
    must heal that rather than leaving a lone list-item chunk under the
    floor."""
    document = build(
        DocumentElement(kind=HEADING, text="1 Results", level=1),
        DocumentElement(kind=LIST_ITEM, text="ok"),
        DocumentElement(kind=PARAGRAPH, text="alpha beta gamma"),
    )
    result = chunker().chunk(
        document, options(max_tokens=4, min_tokens=3, merge_short_siblings=True)
    )

    for chunk in result.chunks[:-1]:
        assert chunk.token_count >= 3, "a non-terminal chunk fell below the floor"
    assert any(
        "ok" in c.content and "Results" in c.content for c in result.chunks
    ), "the short list item must have merged into a neighbouring chunk"


def test_short_chunks_never_merge_across_a_heading_boundary():
    document = build(
        DocumentElement(kind=HEADING, text="1 Intro", level=1),
        DocumentElement(kind=PARAGRAPH, text="a"),
        DocumentElement(kind=HEADING, text="2 Methods", level=1),
        DocumentElement(kind=PARAGRAPH, text="b"),
    )
    result = chunker().chunk(
        document,
        options(max_tokens=50, min_tokens=10, merge_short_siblings=True),
    )

    assert len(result.chunks) == 2
    contents = [c.content for c in result.chunks]
    assert not any("Intro" in c and "Methods" in c for c in contents)


def test_the_ceiling_wins_when_a_short_chunks_only_neighbour_is_already_full():
    """A short chunk merges into its next sibling only when the ceiling
    allows it. When the only adjacent chunk is already at the ceiling, no
    grouping of these three pieces can satisfy both constraints — 1 + 20
    exceeds a 20-token ceiling regardless of merge order — so the short
    chunk is left below the floor even though it is not the section's last
    chunk. The ceiling (IR-110's guarantee) wins over the floor (this
    ticket's best-effort merge) by design.
    """
    document = build(
        DocumentElement(kind=PARAGRAPH, text="hi"),
        DocumentElement(kind=PARAGRAPH, text=("word " * 20).strip()),
        DocumentElement(kind=PARAGRAPH, text="bye now"),
    )
    result = chunker().chunk(
        document, options(max_tokens=20, min_tokens=5, merge_short_siblings=True)
    )

    for chunk in result.chunks:
        assert chunk.token_count <= 20, "the ceiling must never be exceeded"
    assert result.chunks[0].content == "hi", (
        "no merge is possible here without breaching the ceiling"
    )


def test_the_last_chunk_in_a_section_is_exempt_from_the_minimum_floor():
    document = build(
        DocumentElement(kind=HEADING, text="1 Intro", level=1),
        DocumentElement(kind=PARAGRAPH, text="lonely"),
    )
    # A floor the lone chunk itself cannot satisfy: this must not raise or
    # loop trying to merge a last chunk with a sibling that doesn't exist.
    result = chunker().chunk(
        document, options(max_tokens=50, min_tokens=50, merge_short_siblings=True)
    )
    assert len(result.chunks) == 1


# --------------------------------------------------------------------------
# Sentence and hard-split stages
# --------------------------------------------------------------------------


def test_an_oversized_paragraph_splits_on_sentence_boundaries_first():
    text = "Short one. " + ("word " * 30).strip() + ". Another short one."
    document = build(DocumentElement(kind=PARAGRAPH, text=text))

    result = chunker().chunk(document, options(max_tokens=6, merge_short_siblings=False))

    for chunk in result.chunks:
        assert count_tokens(chunk.content) <= 6


def test_a_pathological_single_run_on_word_is_hard_split_without_losing_characters():
    huge_word = "supercalifragilisticexpialidocious" * 10
    document = build(DocumentElement(kind=PARAGRAPH, text=huge_word))

    result = chunker().chunk(document, options(max_tokens=4, merge_short_siblings=False))

    assert "".join(c.content for c in result.chunks) == huge_word


# --------------------------------------------------------------------------
# Registration and the shared contract
# --------------------------------------------------------------------------


def test_registered_under_its_own_strategy_id():
    from apps.ai.chunking.registry import registered_strategies

    assert STRATEGY_ID in registered_strategies()
    assert "fixed-window" in registered_strategies(), (
        "the baseline must remain registered as the comparison point"
    )


@settings(max_examples=40, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    n_rows=st.integers(min_value=1, max_value=60),
    max_tokens=st.integers(min_value=6, max_value=30),
)
def test_property_table_header_always_present_in_every_row_fragment(n_rows, max_tokens):
    document = _table_document(n_rows=n_rows)
    result = chunker().chunk(
        document, options(max_tokens=max_tokens, merge_short_siblings=False)
    )

    for chunk in result.chunks:
        if TABLE_ROW in chunk.element_kinds:
            assert "Col1" in chunk.content
