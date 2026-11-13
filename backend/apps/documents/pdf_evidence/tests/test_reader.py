"""The PDF evidence reader, called in-process on fixture PDFs (IR-1053)."""

from io import BytesIO

import pytest

from apps.ai.extraction.tests.fixtures import FIXTURES, pdf_bytes
from apps.documents.pdf_evidence import reader
from apps.documents.pdf_evidence.tests.thesis import thesis_pdf


def read(data: bytes, max_pages: int = 100) -> dict:
    return reader.read(BytesIO(data), max_pages=max_pages)


def line_text(line: dict) -> str:
    return " ".join(word[0] for word in line["words"])


def lines_of(evidence: dict, page: int) -> list[dict]:
    return evidence["pages"][page - 1]["lines"]


def test_a_heading_line_carries_its_words_boxes_size_and_bold():
    evidence = read(pdf_bytes(FIXTURES["numbered_headings"]))

    heading = next(line for line in lines_of(evidence, 1) if line_text(line) == "1 Introduction")
    assert heading["size"] == 14.0
    assert heading["bold"] is True
    number, x0, top, x1, bottom = heading["words"][0]
    assert number == "1"
    # Drawn at left 72, top 80 in top-left page points (layouts.py).
    assert abs(x0 - 72) < 1 and 78 < top < 84 and x1 > x0 and bottom > top
    body = next(line for line in lines_of(evidence, 1) if line_text(line).startswith("The introduction"))
    assert (body["size"], body["bold"]) == (10.0, False)


def test_two_columns_on_one_baseline_stay_two_lines():
    evidence = read(pdf_bytes(FIXTURES["two_columns"]))

    texts = [line_text(line) for line in lines_of(evidence, 1)]
    assert "Left column one opens." in texts
    assert "Right column one resumes." in texts


def test_every_fixture_page_has_a_text_layer_and_its_size():
    for name, pages in (("numbered_headings", 2), ("two_columns", 1),
                        ("table_across_pages", 2), ("figures", 1)):
        evidence = read(pdf_bytes(FIXTURES[name]))
        assert evidence["page_count"] == pages, name
        assert [(p["page"], p["width"], p["height"], p["has_text_layer"]) for p in evidence["pages"]] == [
            (n, 612.0, 792.0, True) for n in range(1, pages + 1)], name
        assert evidence["bookmarks"] == [] and evidence["page_labels"] is None, name


def test_bookmarks_keep_their_level_and_page():
    evidence = read(thesis_pdf())

    assert evidence["bookmarks"] == [
        {"title": "Contents", "level": 1, "page": 2},
        {"title": "1 Introduction", "level": 1, "page": 4},
        {"title": "1.1 Background", "level": 2, "page": 4},
        {"title": "2 Methods", "level": 1, "page": 5},
    ]


def test_roman_and_arabic_page_labels_are_read():
    assert read(thesis_pdf())["page_labels"] == ["i", "ii", "iii", "1", "2"]


def test_a_page_with_no_text_layer_stores_nothing_else():
    page = read(thesis_pdf())["pages"][2]

    assert page == {"page": 3, "width": 612.0, "height": 792.0, "has_text_layer": False}


def test_contents_entries_carry_number_title_indent_and_printed_page():
    evidence = read(thesis_pdf())

    assert evidence["contents"] == [
        {"page": 2, "number": "", "title": "Abstract", "indent": 0.0, "page_label": "iii"},
        {"page": 2, "number": "1", "title": "Introduction", "indent": 0.0, "page_label": "1"},
        {"page": 2, "number": "1.1", "title": "Background", "indent": 18.0, "page_label": "1"},
        {"page": 2, "number": "2", "title": "Methods", "indent": 0.0, "page_label": "2"},
    ]


def test_a_paper_with_no_contents_page_has_no_entries():
    assert read(pdf_bytes(FIXTURES["numbered_headings"]))["contents"] == []


def test_more_pages_than_the_limit_is_over_budget():
    with pytest.raises(reader.OverBudget):
        read(thesis_pdf(), max_pages=4)
