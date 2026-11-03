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


def _headings(items):
    elements = shape_llamaparse(result_with(
        [{"type": "heading", "value": text, "level": level} for text, level in items]
    )).elements
    return [(e.text, e.level) for e in elements if e.kind == "heading"]


def test_numbered_headings_take_the_depth_their_numbering_claims():
    # IR-859: levels as LlamaParse returned them for a proxy paper in IR-851.
    assert _headings([
        ("Paper title", 1), ("1 INTRODUCTION", 3), ("1.1 Background", 4),
        ("1.2 Existing libraries", 2), ("1.2.1 DiffEqGPU", 3), ("2 METHODS", 2), ("3 RESULTS", 2),
    ]) == [
        ("Paper title", 1), ("1 INTRODUCTION", 2), ("1.1 Background", 3),
        ("1.2 Existing libraries", 3), ("1.2.1 DiffEqGPU", 4), ("2 METHODS", 2), ("3 RESULTS", 2),
    ]


def test_roman_sections_and_lettered_subsections_are_numbering_too():
    assert _headings([
        ("I. INTRODUCTION", 2), ("A. Decoding", 3), ("B. Locality", 3), ("C. Routing", 2), ("D. Ablation", 2),
        ("II. DESIGN", 2), ("X. CONCLUSION", 1),
    ]) == [
        ("I. INTRODUCTION", 2), ("A. Decoding", 3), ("B. Locality", 3), ("C. Routing", 3), ("D. Ablation", 3),
        ("II. DESIGN", 2), ("X. CONCLUSION", 2),
    ]


def test_unnumbered_headings_are_placed_against_the_numbered_sections():
    assert _headings([
        ("Abstract", 2), ("1 Introduction", 2), ("Self-consistency loop", 4),
        ("2 Method", 2), ("References", 1), ("Appendix", 2),
    ]) == [
        ("Abstract", 2), ("1 Introduction", 2), ("Self-consistency loop", 3),
        ("2 Method", 2), ("References", 2), ("Appendix", 2),
    ]


def test_a_paper_numbering_nothing_keeps_the_vendor_levels():
    assert _headings([("Overview", 1), ("Scope", 2), ("Detail", 3)]) == [
        ("Overview", 1), ("Scope", 2), ("Detail", 3),
    ]


@pytest.mark.parametrize("caption", [
    "TABLE I: Flit classes in MESHKV.", "Table 1: Expected turnover", "Figure 7: 4DProblem error",
    "Fig. 3 Latency per hop", "Tab. 2. Parameters",
])
def test_a_caption_returned_as_a_heading_becomes_text(caption):
    element, = shape_llamaparse(result_with([{"type": "heading", "value": caption, "level": 2}])).elements
    assert (element.kind, element.level, element.source_label) == ("text", None, "heading")


@pytest.mark.parametrize("heading", ["Table of Contents", "Figures and Tables", "Tableau results"])
def test_a_heading_that_only_mentions_tables_or_figures_stays_a_heading(heading):
    element, = shape_llamaparse(result_with([{"type": "heading", "value": heading, "level": 2}])).elements
    assert element.kind == "heading"


def test_a_title_at_section_level_is_raised_above_the_sections():
    raw = result_with([
        {"type": "heading", "value": "Diverse Metallicities in Protoclusters", "level": 2},
        {"type": "heading", "value": "ABSTRACT", "level": 4},
        {"type": "heading", "value": "1 INTRODUCTION", "level": 3},
        {"type": "heading", "value": "2 METHOD", "level": 2},
    ])
    document = shape_llamaparse(raw)
    assert document.title == "Diverse Metallicities in Protoclusters"
    assert [(e.text, e.level) for e in document.elements] == [
        ("Diverse Metallicities in Protoclusters", 1), ("ABSTRACT", 4), ("1 INTRODUCTION", 2), ("2 METHOD", 2),
    ]


def test_front_matter_first_is_not_taken_for_the_title():
    document = shape_llamaparse(result_with([
        {"type": "heading", "value": "Abstract", "level": 2},
        {"type": "heading", "value": "1 Introduction", "level": 2},
    ]))
    assert document.title == ""
    assert [e.level for e in document.elements] == [2, 2]
