"""The normalizer: cleans a NormalizedDocument's elements before chunking
(IR-113).

Pure, before/after fixture tests — no I/O, no clock, no randomness. Every
case is stated as "this document goes in, that document comes out."
"""

import pytest
from hypothesis import given, settings, strategies as st

from apps.ai.chunking.document import (
    BoundingBox,
    HEADING,
    PAGE_FOOTER,
    PAGE_HEADER,
    PARAGRAPH,
    TABLE_HEADER,
    TABLE_ROW,
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


def _para(text, page):
    return DocumentElement(kind=PARAGRAPH, text=text, page=page, bboxes=(box(page),))


def test_a_short_line_repeating_across_pages_is_dropped_whatever_its_label():
    """IR-247. Record 30 carries `Published Date: 17/04/2026` on nearly every
    page, and Docling labels the same string `page_header` 18 times and
    `paragraph` 27 times. Normalization dropped furniture by trusting the
    label, so the 27 survivors landed in 20 of 75 chunks — 27% of the corpus —
    sometimes twice in one chunk.
    """
    elements = [_para("Published Date: 17/04/2026", page) for page in range(1, 11)]
    # Distinct per page, as real prose is. An identical short line on every
    # page would be furniture by this rule's own definition, whatever it says
    # about itself — see the test below, which pins that deliberately.
    elements += [_para(f"Findings for section {page}.", page) for page in range(1, 11)]
    result = normalize(build(*elements), ChunkingOptions())
    texts = [e.text for e in result.elements]

    assert "Published Date: 17/04/2026" not in texts
    assert sum(t.startswith("Findings for section") for t in texts) == 10, (
        "content must be untouched"
    )


def test_a_short_line_identical_on_every_page_is_furniture_whatever_it_says():
    """The rule cannot read meaning, only shape. A short line repeated verbatim
    across most pages is furniture by definition — that is the whole premise —
    and a document that puts real content in that shape loses it.

    Recorded rather than hidden: the escape hatch is that furniture must be
    short, so anything above ten words survives regardless.
    """
    elements = [_para("Confidential draft.", page) for page in range(1, 11)]
    result = normalize(build(*elements), ChunkingOptions())

    assert [e.text for e in result.elements] == []


def test_a_line_repeating_within_one_page_is_kept():
    """The rule keys on *page spread*, not raw frequency. A line repeated
    several times on one page is a list label or a table cell, not furniture."""
    elements = [_para("Status: pending", 1) for _ in range(8)]
    elements.append(_para("Some prose.", 1))
    result = normalize(build(*elements), ChunkingOptions())

    assert [e.text for e in result.elements].count("Status: pending") == 8


def test_a_repeated_table_header_is_never_treated_as_furniture():
    """`repeat_table_header` is a feature (IR-111): a table split across pages
    carries its header into every fragment. Furniture detection must not
    delete the very thing another rule works to repeat."""
    elements = []
    for page in range(1, 11):
        elements.append(
            DocumentElement(kind=TABLE_HEADER, text="| FR-ID | Label |", page=page,
                            bboxes=(box(page),))
        )
        elements.append(
            DocumentElement(kind=TABLE_ROW, text=f"| FR-{page} | thing |", page=page,
                            bboxes=(box(page),))
        )
    result = normalize(build(*elements), ChunkingOptions())

    assert [e.text for e in result.elements].count("| FR-ID | Label |") == 10


def test_a_long_repeated_paragraph_is_not_furniture():
    """Furniture is terse. A full sentence repeating across pages is a
    boilerplate clause, and deleting it is content loss."""
    sentence = (
        "This document is confidential and may not be reproduced without the "
        "written permission of the university research office."
    )
    elements = [_para(sentence, page) for page in range(1, 11)]
    result = normalize(build(*elements), ChunkingOptions())

    assert [e.text for e in result.elements].count(sentence) == 10


def test_dropping_furniture_leaves_surviving_regions_untouched():
    """Normalization drops elements rather than rewriting a string precisely so
    page and bbox data survives for the citation overlay."""
    elements = [_para("Published Date: 17/04/2026", page) for page in range(1, 11)]
    keeper = _para("Real content.", 4)
    elements.append(keeper)
    result = normalize(build(*elements), ChunkingOptions())
    survivor = [e for e in result.elements if e.text == "Real content."][0]

    assert survivor.page == 4
    assert survivor.bboxes == keeper.bboxes


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


@settings(max_examples=60)
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
