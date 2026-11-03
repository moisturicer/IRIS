"""Shaping at its public boundary, using the synthetic PDF recordings."""

import pytest

from apps.ai.extraction.shaping import shape_llamaparse
from .llamaparse_fixtures import recorded, result_with


def test_recorded_headings_keep_vendor_depth_and_line_evidence():
    document = shape_llamaparse(recorded("numbered_headings"))
    headings = [element for element in document.elements if element.kind == "heading"]
    assert [(h.text, h.level) for h in headings] == [
        ("1 Introduction", 2), ("1.1 Background", 3), ("2 Methods", 2), ("3 Results", 2),
    ]
    assert document.title == ""
    assert document.page_sizes == {1: (612.0, 792.0), 2: (612.0, 792.0)}
    assert document.confidence == 1.0
    heading = headings[0]
    assert heading.page == 1
    assert heading.printed_page_number == "1"
    assert heading.bboxes[0].left == 72.97
    assert heading.bboxes[0].top == 83.85


def test_kinds_keep_nested_ordered_lists_tables_and_uncaptioned_figures():
    document = shape_llamaparse(result_with([
        {"type": "list", "ordered": True, "items": [
            {"type": "text", "value": "First"},
            {"type": "list", "ordered": False, "items": [{"type": "text", "value": "Child"}]},
        ]},
        {"type": "table", "rows": [["Name", "Value"], ["A", "42"]], "html": "<table>original</table>"},
        {"type": "image", "caption": "", "name": "figure.png"},
        {"type": "code", "value": "x = 42"},
        {"type": "link", "text": "Reference", "url": "https://example.test"},
        {"type": "new_vendor_kind", "value": "Kept verbatim"},
    ]))
    listing, table, figure, code, link, unknown = document.elements
    assert listing.kind == "list" and listing.ordered
    assert listing.children[1].kind == "list"
    assert listing.children[1].children[0].text == "Child"
    assert "First" in listing.text and "Child" in listing.text
    assert table.kind == "table"
    assert table.rows == (("Name", "Value"), ("A", "42"))
    assert table.text == "Name | Value\nA | 42"
    assert table.html == "<table>original</table>"
    assert figure.kind == "image" and figure.text == "" and figure.description == ""
    assert (code.kind, code.text, link.kind, link.text) == ("code", "x = 42", "link", "Reference")
    assert unknown.kind == "paragraph" and unknown.source_label == "new_vendor_kind"
    assert all(e.page == 1 and e.printed_page_number == "iv" for e in document.elements)


def test_display_formulas_are_declared_elements_without_changing_neighboring_prose():
    document = shape_llamaparse(result_with([
        {"type": "text", "value": r"Before $$x^2 = y$$ after \[a+b\] end."},
    ]))
    assert [(e.kind, e.text) for e in document.elements] == [
        ("text", "Before "), ("formula", "x^2 = y"), ("text", " after "),
        ("formula", "a+b"), ("text", " end."),
    ]
    recorded_formulas = [e for e in shape_llamaparse(recorded("figures")).elements if e.kind == "formula"]
    assert [e.text for e in recorded_formulas] == ["a^2 + b^2 = c^2"]


@pytest.mark.parametrize("page,level,title", [(1, 1, "Actual title"), (2, 1, "Actual title"), (3, 1, ""), (1, 2, "")])
def test_title_requires_an_early_level_one_heading(page, level, title):
    raw = result_with([{"type": "heading", "value": "Actual title", "level": level}])
    raw["items"]["pages"][0]["page_number"] = page
    assert shape_llamaparse(raw).title == title


def test_merged_table_retains_both_pages_and_does_not_duplicate_the_continuation():
    document = shape_llamaparse(recorded("table_across_pages"))
    tables = [e for e in document.elements if e.kind == "table"]
    assert len(tables) == 1
    assert len(tables[0].rows) == 31
    assert tables[0].rows[-1] == ("Row 30", "430 g")
    assert {box.page for box in tables[0].bboxes} == {1, 2}
    assert "<thead>" in tables[0].html


def test_documented_list_nesting_preserves_numbering_and_declares_nested_formulas():
    listing = shape_llamaparse(result_with([
        {"type": "list", "ordered": True, "items": [
            {"type": "text", "value": "First $$x=1$$"},
            {"type": "list", "ordered": False, "items": [{"type": "text", "value": "Child"}]},
            {"type": "text", "value": "Second"},
        ]},
    ])).elements[0]
    assert listing.text == "1. First $$x=1$$\n  - Child\n2. Second"
    assert [e.kind for e in listing.children[0].children] == ["text", "formula"]


def test_failed_grounding_keeps_available_items_and_low_confidence_metadata():
    raw = result_with([{"type": "text", "value": "Available passage."}])
    raw["grounded_items"] = [{"page_number": 1, "success": False, "items": None}]
    raw["metadata"]["pages"][0]["confidence"] = 0.1
    document = shape_llamaparse(raw)
    assert [e.text for e in document.elements] == ["Available passage."]
    assert document.page_metadata[1]["confidence"] == 0.1
