"""The FTS string derived from the structured document (IR-107).

``Record.search_vector`` is a working GIN index built over text shaped by
these rules. These tests pin the rules so a future extraction change cannot
alter search behaviour without someone saying so out loud.
"""

from apps.ai.chunking.document import (
    HEADING,
    PARAGRAPH,
    TABLE_ROW,
    DocumentElement,
    NormalizedDocument,
)
from apps.ai.extraction.flattening import clean_text, flatten_for_search


def _document(*texts: str) -> NormalizedDocument:
    return NormalizedDocument(
        title="t", elements=tuple(DocumentElement(kind=PARAGRAPH, text=t) for t in texts)
    )


def test_elements_are_joined_into_one_line():
    result = flatten_for_search(_document("First paragraph.", "Second paragraph."))

    assert result == "First paragraph. Second paragraph."


def test_headings_and_table_rows_are_indexed_alongside_prose():
    document = NormalizedDocument(
        title="t",
        elements=(
            DocumentElement(kind=HEADING, text="3 Methodology"),
            DocumentElement(kind=PARAGRAPH, text="Samples were collected weekly."),
            DocumentElement(kind=TABLE_ROW, text="| Tilapia | 412 g |"),
        ),
    )

    result = flatten_for_search(document)

    assert "3 Methodology" in result
    assert "Samples were collected weekly." in result
    assert "Tilapia" in result


def test_stranded_page_numbers_are_dropped():
    assert clean_text("Real content here\n42\nMore content here") == (
        "Real content here More content here"
    )


def test_very_short_lines_are_dropped():
    assert clean_text("Real content here\nx\nMore content here") == (
        "Real content here More content here"
    )


def test_runs_of_whitespace_collapse():
    assert clean_text("Alpha    beta\n\n\n  gamma  ") == "Alpha beta gamma"


def test_non_indexable_characters_become_spaces():
    assert clean_text("Feed conversion @ 1.6 [ratio]") == "Feed conversion 1.6 ratio"


def test_accented_and_non_ascii_words_survive():
    """``\\w`` is Unicode-aware, and the corpus is bilingual — stripping
    non-ASCII would silently drop Cebuano and every accented author name."""
    assert clean_text("Café tilapia sa Cebu") == "Café tilapia sa Cebu"


def test_an_empty_document_flattens_to_an_empty_string():
    assert flatten_for_search(NormalizedDocument(title="t")) == ""


def test_flattening_does_not_alter_the_element_text_itself():
    """Element text is what gets embedded; these rules are for a text index
    that is not its consumer."""
    document = _document("Feed conversion @ 1.6 [ratio]")

    flatten_for_search(document)

    assert document.elements[0].text == "Feed conversion @ 1.6 [ratio]"
