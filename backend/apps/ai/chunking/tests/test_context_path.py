"""Tests for the context-path decorator (IR-112).

Runs against every registered strategy, wrapped, plus decorator-specific
truncation and no-heading behaviour.
"""

from hypothesis import given, settings, strategies as st

from apps.ai.chunking import (
    ChunkingOptions,
    DocumentElement,
    NormalizedDocument,
    build_chunker,
    build_context_path_chunker,
    registered_strategies,
)
from apps.ai.chunking.context_path import ContextPathChunker, _truncate_middle
from apps.ai.chunking.document import HEADING, PARAGRAPH, TABLE_HEADER, TABLE_ROW
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


def test_a_repeated_table_header_does_not_desync_the_cursor():
    """The structural cascade repeats a table's header row in every fragment
    it splits that table into (IR-111). A cursor that naively advances by a
    chunk's full word count over-counts on every fragment after the first,
    racing ahead of the true document position — regression test for that.
    """
    document = doc(
        DocumentElement(kind=HEADING, text="1 Results", level=1),
        DocumentElement(kind=TABLE_HEADER, text="Col1 Col2 Col3 Col4"),
        *[
            DocumentElement(kind=TABLE_ROW, text=f"r{i} a b c")
            for i in range(20)
        ],
        DocumentElement(kind=HEADING, text="2 Discussion", level=1),
        DocumentElement(kind=PARAGRAPH, text="This is the discussion section text."),
    )
    options = ChunkingOptions(
        strategy="structural-markdown-v1", max_tokens=15, merge_short_siblings=False
    )
    result = build_context_path_chunker(options).chunk(document, options)

    table_chunks = [c for c in result.chunks if TABLE_ROW in c.element_kinds]
    assert table_chunks, "the table must have actually been split into fragments"
    for chunk in table_chunks:
        assert chunk.context_path[-1] == "1 Results", (
            "a table fragment drifted into the next section's heading path: "
            f"{chunk.context_path!r} for {chunk.content!r}"
        )

    last_chunk = result.chunks[-1]
    assert last_chunk.context_path[-1] == "2 Discussion"
    assert "discussion section" in last_chunk.content


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
    """12 was 6 before IR-287, when the budget was counted in words.

    The path is the same, the intent is the same -- a budget that the full
    four-segment path overruns and the title-plus-nearest pair fits -- and
    the number moved because the unit did.
    """
    path = ("Thesis Title", "1 Chapter One", "1.1 Section", "1.1.2 Subsection")
    truncated = _truncate_middle(path, max_tokens=12)

    assert truncated[0] == "Thesis Title"
    assert truncated[-1] == "1.1.2 Subsection"
    assert "1 Chapter One" not in truncated
    assert count_tokens(" > ".join(truncated)) <= 12


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


@settings(max_examples=40)
@given(document=_document)
def test_property_no_content_is_lost_with_decorator_applied(document):
    options = ChunkingOptions(strategy="structural-markdown-v1", max_tokens=16)
    result = build_context_path_chunker(options).chunk(document, options)

    rejoined = " ".join(c.content for c in result.chunks).split()
    original = " ".join(e.text for e in document.elements).split()
    assert rejoined == original


@settings(max_examples=40)
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


def test_a_folded_heading_keeps_the_path_of_the_section_it_folded_into():
    """IR-241 folds a heading-only chunk forward, so a chunk can now span a
    heading boundary — which no chunk could do before, because sectioning
    split on every heading.

    The merged chunk must carry the *child's* path. Taking the first word's
    trail would hand it "3 Methodology" and silently drop "3.2 Sampling
    Procedure", making the path less specific than before the fold — the
    opposite of what the context path is for (IR-112).
    """
    document = doc(
        DocumentElement(kind=HEADING, text="3 Methodology", level=1),
        DocumentElement(kind=HEADING, text="3.2 Sampling Procedure", level=2),
        DocumentElement(
            kind=PARAGRAPH, text="Samples were collected weekly from twelve ponds."
        ),
        title="Optimization of Tilapia Feed Conversion",
    )
    options = ChunkingOptions(strategy="structural-markdown-v1", max_tokens=50)
    result = build_context_path_chunker(options).chunk(document, options)

    merged = [c for c in result.chunks if "Samples were collected" in c.content]
    assert len(merged) == 1
    assert merged[0].context_path == (
        "Optimization of Tilapia Feed Conversion",
        "3 Methodology",
        "3.2 Sampling Procedure",
    )
    assert "3 Methodology" in merged[0].content, "the heading text is not lost"


def test_a_fixed_window_chunk_ending_on_a_heading_keeps_its_own_sections_path():
    """The fixed-window baseline knows nothing about headings — its own
    docstring says so — so it will happily close a window on one.

    Such a window is mostly the *previous* section's prose, and labelling it
    with the trailing heading would put Introduction text under Methods. This
    is why the rule is "first word that is not a heading" rather than simply
    the chunk's last word: the last-word rule fixes IR-241's folded chunk and
    silently breaks the strategy the cascade is measured against on the eval
    set, which would confound that comparison.
    """
    document = doc(
        DocumentElement(kind=HEADING, text="1 Intro", level=1),
        DocumentElement(kind=PARAGRAPH, text="alpha beta gamma delta epsilon"),
        DocumentElement(kind=HEADING, text="2 Methods", level=1),
        DocumentElement(kind=PARAGRAPH, text="zeta eta theta"),
        title="A Thesis",
    )
    options = ChunkingOptions(strategy="fixed-window", max_tokens=9)
    result = build_context_path_chunker(options).chunk(document, options)

    for chunk in result.chunks:
        if "alpha" in chunk.content:
            assert chunk.context_path == ("A Thesis", "1 Intro"), (
                f"Introduction prose labelled {chunk.context_path} "
                f"in chunk {chunk.content!r}"
            )



# ---------------------------------------------------------------------------
# Unnumbered headings and the numbered outline (IR-248)
# ---------------------------------------------------------------------------


def test_an_unnumbered_heading_does_not_evict_the_numbered_section_it_sits_in():
    """IR-248. Docling promotes plenty of things to `section_header` that carry
    no section number — on a real 45-page SRS, 61 of 92 headings. At level 1
    each of them evicted the numbered parent, so `1.3` and `1.4` ended up
    trailed to a bullet-list lead-in (`IRIS shall NOT:`) instead of to
    `1. Introduction`.
    """
    document = doc(
        DocumentElement(kind=HEADING, text="1.   Introduction", level=1),
        DocumentElement(kind=PARAGRAPH, text="opening"),
        DocumentElement(kind=HEADING, text="IRIS shall NOT:", level=1),
        DocumentElement(kind=PARAGRAPH, text="a bullet lead-in"),
        DocumentElement(kind=HEADING, text="1.3.   Definitions", level=2),
        DocumentElement(kind=PARAGRAPH, text="the terms used"),
        title="SRS",
    )
    options = ChunkingOptions(strategy="structural-markdown-v1", max_tokens=12)
    result = build_context_path_chunker(options).chunk(document, options)

    defs = [c for c in result.chunks if "the terms used" in c.content][0]
    assert defs.context_path == ("SRS", "1.   Introduction", "1.3.   Definitions")

    lead_in = [c for c in result.chunks if "bullet lead-in" in c.content][0]
    assert lead_in.context_path[:2] == ("SRS", "1.   Introduction"), (
        "the fragment should nest inside the section, not replace it"
    )


def test_consecutive_unnumbered_headings_are_siblings_under_their_numbered_parent():
    """`Assumptions` and `Dependencies` are real subsections of `2.5`; they are
    siblings of each other, not ancestors."""
    document = doc(
        DocumentElement(kind=HEADING, text="2.   Overall Description", level=1),
        DocumentElement(kind=HEADING, text="Assumptions", level=1),
        DocumentElement(kind=PARAGRAPH, text="we assume things"),
        DocumentElement(kind=HEADING, text="Dependencies", level=1),
        DocumentElement(kind=PARAGRAPH, text="we depend on things"),
        title="SRS",
    )
    options = ChunkingOptions(strategy="structural-markdown-v1", max_tokens=12)
    result = build_context_path_chunker(options).chunk(document, options)

    dep = [c for c in result.chunks if "depend on things" in c.content][0]
    assert dep.context_path == ("SRS", "2.   Overall Description", "Dependencies")
    assert "Assumptions" not in dep.context_path, "siblings, not ancestors"


def test_front_matter_before_any_numbered_heading_is_unaffected():
    """`ABSTRACT`, `Keywords` and the like arrive before the outline starts, so
    there is no numbered parent to nest under and nothing changes."""
    document = doc(
        DocumentElement(kind=HEADING, text="ABSTRACT", level=1),
        DocumentElement(kind=PARAGRAPH, text="the summary"),
        DocumentElement(kind=HEADING, text="Keywords", level=1),
        DocumentElement(kind=PARAGRAPH, text="rag, chunking"),
        title="A Paper",
    )
    options = ChunkingOptions(strategy="structural-markdown-v1", max_tokens=12)
    result = build_context_path_chunker(options).chunk(document, options)

    kw = [c for c in result.chunks if "rag, chunking" in c.content][0]
    assert kw.context_path == ("A Paper", "Keywords")


def test_a_document_with_no_numbering_at_all_is_unchanged():
    document = doc(
        DocumentElement(kind=HEADING, text="Introduction", level=1),
        DocumentElement(kind=PARAGRAPH, text="alpha"),
        DocumentElement(kind=HEADING, text="Method", level=1),
        DocumentElement(kind=PARAGRAPH, text="beta"),
        title="Essay",
    )
    options = ChunkingOptions(strategy="structural-markdown-v1", max_tokens=12)
    result = build_context_path_chunker(options).chunk(document, options)

    beta = [c for c in result.chunks if "beta" in c.content][0]
    assert beta.context_path == ("Essay", "Method")
