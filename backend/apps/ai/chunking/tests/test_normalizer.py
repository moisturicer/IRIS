"""The normalizer: cleans a NormalizedDocument's elements before chunking
(IR-113).

Pure, before/after fixture tests — no I/O, no clock, no randomness. Every
case is stated as "this document goes in, that document comes out."
"""

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from apps.ai.chunking.document import (
    BoundingBox,
    HEADING,
    PAGE_FOOTER,
    PAGE_HEADER,
    PARAGRAPH,
    DocumentElement,
    NormalizedDocument,
)
from apps.ai.chunking.normalizer import normalize
from apps.ai.chunking.registry import build_chunker, registered_strategies
from apps.ai.chunking.values import ChunkingOptions
from apps.ai.extraction.flattening import flatten_for_search


def build(*elements: DocumentElement, title: str = "A Thesis") -> NormalizedDocument:
    return NormalizedDocument(title=title, elements=tuple(elements))


def box(page: int = 1) -> BoundingBox:
    return BoundingBox(page=page, left=0, top=0, right=100, bottom=10)


# --------------------------------------------------------------------------
# Running headers and footers
# --------------------------------------------------------------------------


def test_running_headers_are_dropped():
    document = build(
        DocumentElement(kind=PAGE_HEADER, text="Cebuano Institute of Technology"),
        DocumentElement(kind=PARAGRAPH, text="Actual content."),
    )

    result = normalize(document, ChunkingOptions())

    assert [e.kind for e in result.elements] == [PARAGRAPH]
    assert result.elements[0].text == "Actual content."


def test_running_footers_are_dropped():
    document = build(
        DocumentElement(kind=PARAGRAPH, text="Actual content."),
        DocumentElement(kind=PAGE_FOOTER, text="Republic of the Philippines"),
    )

    result = normalize(document, ChunkingOptions())

    assert [e.kind for e in result.elements] == [PARAGRAPH]


# --------------------------------------------------------------------------
# Stranded page numbers
# --------------------------------------------------------------------------


def test_a_stranded_arabic_page_number_is_dropped():
    document = build(
        DocumentElement(kind=PARAGRAPH, text="End of the section."),
        DocumentElement(kind=PARAGRAPH, text="42"),
    )

    result = normalize(document, ChunkingOptions())

    assert [e.text for e in result.elements] == ["End of the section."]


def test_a_stranded_roman_numeral_page_number_is_dropped():
    document = build(
        DocumentElement(kind=PARAGRAPH, text="xiv"),
        DocumentElement(kind=PARAGRAPH, text="A real sentence about xiv centuries."),
    )

    result = normalize(document, ChunkingOptions())

    assert [e.text for e in result.elements] == [
        "A real sentence about xiv centuries."
    ]


def test_a_short_paragraph_that_is_not_purely_a_number_survives():
    document = build(DocumentElement(kind=PARAGRAPH, text="Chapter 4"))

    result = normalize(document, ChunkingOptions())

    assert [e.text for e in result.elements] == ["Chapter 4"]


# --------------------------------------------------------------------------
# Hyphenation across a line break
# --------------------------------------------------------------------------


def test_a_word_hyphenated_across_a_line_break_is_rejoined():
    document = build(
        DocumentElement(kind=PARAGRAPH, text="This uses a mixed-method-", page=1, bboxes=(box(1),)),
        DocumentElement(kind=PARAGRAPH, text="ology throughout.", page=2, bboxes=(box(2),)),
    )

    result = normalize(document, ChunkingOptions())

    assert len(result.elements) == 1
    assert result.elements[0].text == "This uses a mixed-methodology throughout."


def test_the_rejoined_element_keeps_the_first_fragments_provenance():
    document = build(
        DocumentElement(kind=PARAGRAPH, text="method-", page=1, bboxes=(box(1),)),
        DocumentElement(kind=PARAGRAPH, text="ology.", page=2, bboxes=(box(2),)),
    )

    result = normalize(document, ChunkingOptions())

    assert result.elements[0].page == 1
    assert result.elements[0].bbox == box(1)


def test_a_trailing_hyphen_followed_by_a_capitalized_word_is_not_rejoined():
    """A genuine end-of-sentence hyphen (e.g. a dash used as punctuation)
    should not be merged with an unrelated following sentence."""
    document = build(
        DocumentElement(kind=PARAGRAPH, text="See the appendix-"),
        DocumentElement(kind=PARAGRAPH, text="Chapter 5 begins here."),
    )

    result = normalize(document, ChunkingOptions())

    assert len(result.elements) == 2


def test_a_hyphen_is_not_rejoined_across_a_heading():
    document = build(
        DocumentElement(kind=PARAGRAPH, text="mixed-"),
        DocumentElement(kind=HEADING, text="method"),
    )

    result = normalize(document, ChunkingOptions())

    assert len(result.elements) == 2


# --------------------------------------------------------------------------
# Excluded sections
# --------------------------------------------------------------------------


def test_a_section_named_in_exclude_sections_is_dropped():
    document = build(
        DocumentElement(kind=HEADING, text="1 Introduction", level=1),
        DocumentElement(kind=PARAGRAPH, text="Intro text."),
        DocumentElement(kind=HEADING, text="References", level=1),
        DocumentElement(kind=PARAGRAPH, text="Smith, J. (2020)."),
    )

    result = normalize(document, ChunkingOptions(exclude_sections=("references",)))

    assert [e.text for e in result.elements] == ["1 Introduction", "Intro text."]


def test_exclude_sections_matches_case_insensitively():
    document = build(
        DocumentElement(kind=HEADING, text="REFERENCES", level=1),
        DocumentElement(kind=PARAGRAPH, text="Smith, J. (2020)."),
    )

    result = normalize(document, ChunkingOptions(exclude_sections=("references",)))

    assert result.elements == ()


def test_an_excluded_section_ends_at_the_next_heading():
    document = build(
        DocumentElement(kind=HEADING, text="References", level=1),
        DocumentElement(kind=PARAGRAPH, text="Smith, J. (2020)."),
        DocumentElement(kind=HEADING, text="Appendix", level=1),
        DocumentElement(kind=PARAGRAPH, text="Appendix content."),
    )

    result = normalize(document, ChunkingOptions(exclude_sections=("references",)))

    assert [e.text for e in result.elements] == ["Appendix", "Appendix content."]


def test_no_exclude_sections_means_nothing_is_dropped_on_that_basis():
    document = build(
        DocumentElement(kind=HEADING, text="References", level=1),
        DocumentElement(kind=PARAGRAPH, text="Smith, J. (2020)."),
    )

    result = normalize(document, ChunkingOptions())

    assert len(result.elements) == 2


# --------------------------------------------------------------------------
# Provenance and structure are otherwise untouched
# --------------------------------------------------------------------------


def test_every_surviving_element_keeps_its_page_and_bbox():
    document = build(
        DocumentElement(kind=PARAGRAPH, text="Kept.", page=3, bboxes=(box(3),)),
    )

    result = normalize(document, ChunkingOptions())

    assert result.elements[0].page == 3
    assert result.elements[0].bbox == box(3)


def test_page_sizes_survive_normalization_unchanged():
    document = NormalizedDocument(
        title="A Thesis",
        elements=(DocumentElement(kind=PARAGRAPH, text="Kept."),),
        page_sizes={1: (612.0, 792.0)},
    )

    result = normalize(document, ChunkingOptions())

    assert result.page_sizes == {1: (612.0, 792.0)}


def test_normalization_is_pure_and_deterministic():
    document = build(
        DocumentElement(kind=PAGE_HEADER, text="Header"),
        DocumentElement(kind=PARAGRAPH, text="Content one."),
        DocumentElement(kind=PARAGRAPH, text="12"),
    )

    first = normalize(document, ChunkingOptions())
    second = normalize(document, ChunkingOptions())

    assert first == second
    # The input is untouched — normalize returns a new document.
    assert len(document.elements) == 3


# --------------------------------------------------------------------------
# No content loss survives the combination of normalize() then chunk()
# --------------------------------------------------------------------------


def test_chunking_a_normalized_document_drops_removed_artefacts_but_keeps_content():
    document = build(
        DocumentElement(kind=PAGE_HEADER, text="Cebuano Institute of Technology"),
        DocumentElement(kind=HEADING, text="1 Introduction", level=1),
        DocumentElement(kind=PARAGRAPH, text="This uses a mixed-method-"),
        DocumentElement(kind=PARAGRAPH, text="ology throughout."),
        DocumentElement(kind=PARAGRAPH, text="12"),
        DocumentElement(kind=PAGE_FOOTER, text="Republic of the Philippines"),
    )
    options = ChunkingOptions(max_tokens=50)

    normalized = normalize(document, options)
    result = build_chunker(options).chunk(normalized, options)

    joined = " ".join(c.content for c in result.chunks)
    assert "Cebuano Institute of Technology" not in joined
    assert "Republic of the Philippines" not in joined
    assert "This uses a mixed-methodology throughout." in joined


# --------------------------------------------------------------------------
# The no-content-loss property, measured against the *normalized* input
# --------------------------------------------------------------------------


def _mixed_document(draw_texts, *, artefacts: bool):
    """A document of ordinary paragraphs, optionally interleaved with the
    artefacts the normalizer is supposed to remove."""
    elements: list[DocumentElement] = []
    for i, text in enumerate(draw_texts):
        if artefacts and i % 3 == 0:
            elements.append(DocumentElement(kind=PAGE_HEADER, text="Running Header"))
            elements.append(DocumentElement(kind=PARAGRAPH, text=str(i + 1)))
        elements.append(DocumentElement(kind=PARAGRAPH, text=text, page=1, bboxes=(box(1),)))
    return build(*elements)


_words = st.text(
    alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=1, max_size=12
)
_paragraph = st.lists(_words, min_size=1, max_size=40).map(" ".join)
_texts = st.lists(_paragraph, min_size=1, max_size=8)


@settings(max_examples=60, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(texts=_texts, artefacts=st.booleans())
@pytest.mark.parametrize("strategy_id", sorted(registered_strategies()))
def test_property_no_content_is_lost_after_normalization(strategy_id, texts, artefacts):
    """Concatenating every chunk's content reproduces the *normalized*
    document, modulo whitespace.

    Measured against the normalized input rather than the raw one on
    purpose: normalization is defined by what it removes, so comparing to
    the raw document would fail on exactly the artefacts it is supposed to
    drop, and comparing to nothing at all would let a swallowed exception
    silently take a paragraph with it.
    """
    document = _mixed_document(texts, artefacts=artefacts)
    options = ChunkingOptions(strategy=strategy_id, max_tokens=16)

    normalized = normalize(document, options)
    result = build_chunker(options).chunk(normalized, options)

    rejoined = " ".join(c.content for c in result.chunks).split()
    expected = " ".join(e.text for e in normalized.elements).split()

    assert rejoined == expected


# --------------------------------------------------------------------------
# A page-number pattern must not eat words
# --------------------------------------------------------------------------


@pytest.mark.parametrize("word", ["civil", "did", "vivid", "mix", "dill", "lid", "mill"])
def test_a_word_spelled_from_roman_letters_is_not_mistaken_for_a_folio(word):
    """`^[ivxlcdm]{1,8}$` matched every one of these, silently deleting a
    one-word caption, list item or table cell. Content loss of exactly the
    kind the no-content-loss property exists to catch — and invisible to any
    example written with digits."""
    document = build(DocumentElement(kind=PARAGRAPH, text=word))

    result = normalize(document, ChunkingOptions())

    assert [e.text for e in result.elements] == [word]


@pytest.mark.parametrize("numeral", ["i", "ii", "iv", "ix", "xiv", "xl", "XLII"])
def test_a_well_formed_front_matter_numeral_is_still_dropped(numeral):
    document = build(DocumentElement(kind=PARAGRAPH, text=numeral))

    result = normalize(document, ChunkingOptions())

    assert result.elements == ()


def test_an_empty_element_is_not_treated_as_a_page_number():
    """Every part of the roman pattern is optional, so it matches the empty
    string; without a guard an empty element would be dropped as a folio for
    the wrong reason."""
    document = build(DocumentElement(kind=PARAGRAPH, text="   "))

    result = normalize(document, ChunkingOptions())

    assert len(result.elements) == 1


def test_a_word_hyphenated_at_a_line_break_inside_one_element_is_rejoined():
    """Docling keeps a paragraph's own line breaks, so the split word is more
    often inside an element than across two."""
    document = build(
        DocumentElement(kind=PARAGRAPH, text="This uses a mixed-method-\nology throughout.")
    )

    result = normalize(document, ChunkingOptions())

    assert result.elements[0].text == "This uses a mixed-methodology throughout."


def test_an_internal_hyphen_before_a_capital_is_not_rejoined():
    document = build(
        DocumentElement(kind=PARAGRAPH, text="See the appendix-\nChapter 5 begins here.")
    )

    result = normalize(document, ChunkingOptions())

    assert result.elements[0].text == "See the appendix-\nChapter 5 begins here."


def test_rejoining_inside_an_element_keeps_its_provenance():
    document = build(
        DocumentElement(kind=PARAGRAPH, text="method-\nology.", page=6, bboxes=(box(6),))
    )

    result = normalize(document, ChunkingOptions())

    assert result.elements[0].page == 6
    assert result.elements[0].bboxes == (box(6),)


# --------------------------------------------------------------------------
# Excluded from chunking, but not from full-text search
# --------------------------------------------------------------------------


def test_an_excluded_section_is_still_available_to_full_text_search():
    """The second half of the acceptance criterion, and the half that is easy
    to lose: the references are dropped from *chunking*, not from the record.
    `apps.documents.tasks` builds `extracted_text` from the extraction's own
    document — the one that has not been normalized — so this stays true only
    as long as nothing routes the normalized document into flattening.
    """
    document = build(
        DocumentElement(kind=HEADING, text="4 Results", level=1),
        DocumentElement(kind=PARAGRAPH, text="Yields rose in every treated pond."),
        DocumentElement(kind=HEADING, text="References", level=1),
        DocumentElement(kind=PARAGRAPH, text="Dela Cruz, J. (2024). Pond salinity."),
    )
    options = ChunkingOptions(exclude_sections=("References",), max_tokens=50)

    normalized = normalize(document, options)
    chunks = build_chunker(options).chunk(normalized, options)
    indexed = flatten_for_search(document)

    assert "Dela Cruz" not in " ".join(c.content for c in chunks.chunks)
    assert "Dela Cruz" in indexed
    assert "Yields rose" in indexed
