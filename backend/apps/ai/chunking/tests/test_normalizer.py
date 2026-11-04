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


def test_a_numbered_reference_heading_is_excluded():
    """IR-244. The matcher compared whole heading text, so the shipped default
    list only ever fired on a heading reading exactly "References". Both real
    CIT-U submissions run through IR-116 number their sections, and both kept
    their bibliography: record 29 has "5. REFERENCES", record 30 has
    "1.4.   References" (three spaces, as the document writes it).
    """
    for heading in ("5. REFERENCES", "1.4.   References", "2.1.1 References", "5 References"):
        document = build(
            DocumentElement(kind=HEADING, text="4. Results", level=1),
            DocumentElement(kind=PARAGRAPH, text="findings"),
            DocumentElement(kind=HEADING, text=heading, level=1),
            DocumentElement(kind=PARAGRAPH, text="Adebiyi, M. O. et al."),
        )
        result = normalize(document, ChunkingOptions(exclude_sections=("References",)))
        texts = [e.text for e in result.elements]
        assert heading not in texts, f"{heading!r} was not excluded"
        assert "Adebiyi, M. O. et al." not in texts, f"body under {heading!r} survived"
        assert "findings" in texts, "the preceding section must be untouched"


def test_a_heading_that_merely_contains_the_word_is_not_excluded():
    """The fix must not become a substring match. These are real sections with
    real content, and losing one is worse than keeping a bibliography."""
    for heading in ("Reference Architecture", "References and Further Reading",
                    "3. Referencing Conventions"):
        document = build(
            DocumentElement(kind=HEADING, text=heading, level=1),
            DocumentElement(kind=PARAGRAPH, text="real content here"),
        )
        result = normalize(document, ChunkingOptions(exclude_sections=("References",)))
        texts = [e.text for e in result.elements]
        assert heading in texts, f"{heading!r} was wrongly excluded"
        assert "real content here" in texts


def test_the_shipped_default_list_excludes_what_the_real_documents_use():
    """The defaults in .env.example, against the headings the two real
    submissions actually carry."""
    shipped = ("References", "Bibliography", "Works Cited", "Literature Cited")
    for heading in ("5. REFERENCES", "1.4.   References", "7. BIBLIOGRAPHY",
                    "Works Cited", "6.2 Literature Cited"):
        document = build(
            DocumentElement(kind=HEADING, text=heading, level=1),
            DocumentElement(kind=PARAGRAPH, text="citation list"),
        )
        result = normalize(document, ChunkingOptions(exclude_sections=shipped))
        assert [e.text for e in result.elements] == [], f"{heading!r} survived"


def test_the_table_of_contents_is_excluded_but_the_title_block_is_not():
    """IR-246. A table of contents is the worst retrieval bait in a thesis: it
    holds every section name and none of their content, so it scores against a
    query about any section and returns a page number. On record 30 it ranked
    within 0.005 of the correct answer for "user characteristics and
    constraints".

    The title block is deliberately kept — it carries the document's identity,
    which is the one part of front matter worth retrieving.
    """
    from django.conf import settings as django_settings

    document = build(
        DocumentElement(kind=HEADING, text="CEBU INSTITUTE OF TECHNOLOGY UNIVERSITY", level=1),
        DocumentElement(kind=HEADING, text="Software Requirements Specifications", level=1),
        DocumentElement(kind=HEADING, text="Table of Contents", level=1),
        DocumentElement(kind=TABLE_ROW, text="| 1.1. Purpose | 4 |"),
        DocumentElement(kind=TABLE_ROW, text="| 1.2. Scope | 4 |"),
        DocumentElement(kind=HEADING, text="1.   Introduction", level=1),
        DocumentElement(kind=PARAGRAPH, text="This document is the SRS."),
    )
    result = normalize(
        document,
        ChunkingOptions(exclude_sections=tuple(django_settings.AI_CHUNK_EXCLUDE_SECTIONS)),
    )
    texts = [e.text for e in result.elements]

    assert "Table of Contents" not in texts
    assert not any("Purpose | 4" in t for t in texts), "TOC rows survived"
    assert "CEBU INSTITUTE OF TECHNOLOGY UNIVERSITY" in texts, "the title block must survive"
    assert "This document is the SRS." in texts, "the section after the TOC must survive"


def test_the_navigation_indexes_are_excluded_by_default():
    """`List of Tables` / `List of Figures` are the same shape as a table of
    contents: section or caption names plus page numbers, no content."""
    from django.conf import settings as django_settings

    shipped = tuple(django_settings.AI_CHUNK_EXCLUDE_SECTIONS)
    for heading in ("Table of Contents", "Contents", "List of Tables", "List of Figures"):
        document = build(
            DocumentElement(kind=HEADING, text=heading, level=1),
            DocumentElement(kind=PARAGRAPH, text="page-number filler"),
        )
        result = normalize(document, ChunkingOptions(exclude_sections=shipped))
        assert [e.text for e in result.elements] == [], f"{heading!r} survived"


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
        DocumentElement(kind=PARAGRAPH, text="This uses a mixed method throughout."),
        DocumentElement(kind=PAGE_FOOTER, text="Republic of the Philippines"),
    )
    options = ChunkingOptions(max_tokens=50)

    normalized = normalize(document, options)
    result = build_chunker(options).chunk(normalized, options)

    joined = " ".join(c.content for c in result.chunks)
    assert "Cebuano Institute of Technology" not in joined
    assert "Republic of the Philippines" not in joined
    assert "This uses a mixed method throughout." in joined


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
