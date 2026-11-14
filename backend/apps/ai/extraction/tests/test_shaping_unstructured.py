"""Unstructured shaping at its public boundary (IR-986)."""

import json
from pathlib import Path

import pytest

from apps.ai.extraction.ports import ExtractionError
from apps.ai.extraction.shaping_unstructured import shape_unstructured, unmapped_types
from .unstructured_vendor import recording

SPIKE = Path(__file__).resolve().parents[5] / "docs/evaluation/runs/2026-11-13-unstructured-spike"


def hi_res(name):
    """The Platform ``hi_res`` partition response: a bare element list."""
    return json.loads((SPIKE / "strategies" / f"{name}_hi_res.json").read_text(encoding="utf-8"))


def test_numbered_titles_become_headings_with_depth_from_numbering():
    document = shape_unstructured(recording("numbered_headings"))
    headings = [e for e in document.elements if e.kind == "heading"]
    assert [(h.text, h.level) for h in headings] == [
        ("1 Introduction", 2), ("1.1 Background", 3), ("2 Methods", 2), ("3 Results", 2),
    ]
    assert document.title == ""
    assert document.page_sizes == {1: (612.0, 792.0), 2: (612.0, 792.0)}
    box = headings[0].bboxes[0]
    assert headings[0].page == 1 and box.page == 1
    # 250 dpi pixels to points: 246.118 px * 72/250.
    assert box.left == pytest.approx(70.882, abs=0.001)
    assert box.top == pytest.approx(81.752, abs=0.001)
    assert box.bottom == pytest.approx(96.061, abs=0.001)


def test_hi_res_keeps_reading_order_title_furniture_and_provenance():
    document = shape_unstructured(hi_res("two_columns"))
    furniture = [(e.kind, e.text) for e in document.elements if e.kind in {"header", "footer"}]
    body = [e for e in document.elements if e.kind not in {"header", "footer"}]
    assert furniture == [("header", "IRIS contract fixture"), ("footer", "Page 1")]
    assert [e.text for e in body] == [
        "Two column study", "Left column one opens.", "Left column two continues.", "E = m c^2",
        "Right column one resumes.", "Right column two continues.", "Right column three ends.",
        "Left column three ends.",
    ]
    assert document.title == "Two column study"
    assert (body[0].kind, body[0].level) == ("heading", 1)
    assert body[1].element_id == "0f8b0689b3498198fc4daa381ed8d7f8"
    assert body[1].language == "eng"
    assert all(e.page == 1 for e in document.elements)


def test_page_numbers_are_furniture_kept_on_their_page():
    document = shape_unstructured(recording("numbered_headings"))
    footers = [(e.page, e.text, e.source_label) for e in document.elements if e.kind == "footer"]
    assert footers == [(1, "Page 1", "PageNumber"), (2, "Page 2", "PageNumber")]
    assert sum(e.kind == "header" for e in document.elements) == 2


def test_every_recorded_box_lies_inside_its_page():
    for raw in [*(recording(n) for n in ("figures", "numbered_headings", "table_across_pages", "two_columns")),
                hi_res("two_columns")]:
        document = shape_unstructured(raw)
        boxes = [box for e in document.elements for box in e.bboxes]
        assert boxes
        for box in boxes:
            width, height = document.page_sizes[box.page]
            assert 0 <= box.left < box.right <= width
            assert 0 <= box.top < box.bottom <= height


def test_a_table_across_pages_is_one_table_with_rows_from_its_html():
    raw = recording("table_across_pages")
    document = shape_unstructured(raw)
    tables = [e for e in document.elements if e.kind == "table"]
    assert len(tables) == 1
    table = tables[0]
    assert len(table.rows) == 31
    assert table.rows[0] == ("Sample", "Mass")
    assert table.rows[1] == ("Row 01", "401 g")
    assert table.rows[-1] == ("Row 30", "430 g")
    assert table.text.splitlines()[:2] == ["Sample | Mass", "Row 01 | 401 g"]
    assert table.html.startswith("<table")
    assert [box.page for box in table.bboxes] == [1, 2]
    assert [e.text for e in document.elements if e.kind == "text"] == [
        "The table below continues onto the next page.", "The paragraph after the table.",
    ]


def element(kind, text="", page=1, **metadata):
    box = {"points": [[250, 500], [250, 550], [1000, 550], [1000, 500]],
           "system": "PixelSpace", "layout_width": 2125, "layout_height": 2750}
    return {"type": kind, "element_id": f"id-{kind}-{text[:8]}", "text": text,
            "metadata": {"page_number": page, "coordinates": box, **metadata}}


def test_every_unrecorded_type_has_its_stated_use():
    document = shape_unstructured([
        element("Title", "Table 1: Sample masses"),
        element("Title", "Results", detection_class_prob=0.2),
        element("ListItem", "First point"),
        element("ListItem", "Second point"),
        element("NarrativeText", "Between lists."),
        element("Image", "axis label 0 10 20"),
        element("FigureCaption", "Figure 2: A plotted series."),
        element("Formula", "N-1 |A) = >> 2(n)|n). n=0"),
        element("Formula", "$$a^2 + b^2 = c^2$$"),
        element("NarrativeText", "Energy is $$E = mc^2$$ here."),
        element("CodeSnippet", "x = 42"),
        element("Address", "1 Private Lane, Cebu"),
        element("EmailAddress", "someone@example.test"),
        element("FigureCaption", "Fig. 3 stands alone."),
        element("Hologram", "Kept verbatim"),
    ])
    shaped = [(e.kind, e.text, e.source_label) for e in document.elements]
    assert shaped == [
        ("text", "Table 1: Sample masses", "Title"),
        ("text", "Results", "Title"),
        ("list", "- First point\n- Second point", "ListItem"),
        ("text", "Between lists.", "NarrativeText"),
        ("image", "Figure 2: A plotted series.", "Image"),
        ("image", "", "Formula"),
        ("formula", "a^2 + b^2 = c^2", "Formula"),
        ("text", "Energy is ", "NarrativeText"),
        ("formula", "E = mc^2", "NarrativeText"),
        ("text", " here.", "NarrativeText"),
        ("code", "x = 42", "CodeSnippet"),
        ("text", "Fig. 3 stands alone.", "FigureCaption"),
        ("paragraph", "Kept verbatim", "Hologram"),
    ]
    listing = document.elements[2]
    assert [child.text for child in listing.children] == ["First point", "Second point"]
    figure, crop = document.elements[4], document.elements[5]
    assert figure.figure == "id-Image-axis lab" and crop.figure == "id-Formula-N-1 |A) "
    assert len(figure.bboxes) == 2

    assert all("Private Lane" not in e.text and "@" not in e.text for e in document.elements)


def test_unmapped_types_are_counted():
    raw = [element("Hologram", "a"), element("Hologram", "b"), element("NarrativeText", "c")]
    assert unmapped_types(raw) == {"Hologram": 2}


def test_unstructured_chunking_output_is_refused():
    with pytest.raises(ExtractionError, match="CompositeElement"):
        shape_unstructured([element("CompositeElement", "pre-chunked")])


def test_a_page_number_that_contradicts_page_breaks_is_refused():
    with pytest.raises(ExtractionError, match="page break"):
        shape_unstructured([element("NarrativeText", "one"), {"type": "PageBreak", "metadata": {}},
                            element("NarrativeText", "still one?", page=1)])


def test_a_shaped_document_stores_flattens_and_hashes_like_any_other():
    from apps.ai.chunking.document import DocumentElement, NormalizedDocument
    from apps.ai.extraction.flattening import flatten_for_search
    from apps.ai.extraction.hashing import extraction_hash
    from apps.ai.extraction.serialization import document_from_json, document_to_json

    document = shape_unstructured(recording("numbered_headings"))
    assert document_from_json(document_to_json(document)) == document
    assert extraction_hash(document) == extraction_hash(shape_unstructured(recording("numbered_headings")))
    assert flatten_for_search(document) == (
        "1 Introduction The introduction states the question this fixture asks. 1.1 Background "
        "Background material follows its numbered heading. 2 Methods Methods are described before "
        "any result is reported. 3 Results Results close the document on its second page."
    )
    plain = NormalizedDocument(title="t", elements=(DocumentElement(kind="text", text="x"),))
    assert "element_id" not in document_to_json(plain)["elements"][0]
    assert "language" not in document_to_json(plain)["elements"][0]


def test_a_caption_before_its_image_binds_and_keeps_its_box_first():
    caption = element("FigureCaption", "Figure 1: Above.")
    caption["metadata"]["coordinates"]["points"] = [[250, 100], [250, 140], [900, 140], [900, 100]]
    (figure,) = shape_unstructured([caption, element("Image", "")]).elements
    assert (figure.kind, figure.text) == ("image", "Figure 1: Above.")
    assert figure.bboxes[0].top == pytest.approx(28.8)


def test_an_unknown_coordinate_system_is_refused():
    raw = element("NarrativeText", "x")
    raw["metadata"]["coordinates"]["system"] = "PointSpace"
    with pytest.raises(ExtractionError, match="coordinate system"):
        shape_unstructured([raw])


def platform(name):
    """A Platform ``hi_res`` recording (IR-985, IR-1101)."""
    from .unstructured_platform_vendor import recording as platform_recording

    return platform_recording(name)


def test_a_table_hi_res_splits_at_a_page_break_is_joined():
    document = shape_unstructured(platform("ruled_table"))

    tables = [e for e in document.elements if e.kind == "table"]
    assert len(tables) == 1
    table = tables[0]
    assert table.rows[0] == ("Sample", "Mass")
    # Cell values are the vendor's OCR ("401 g" reads "4019"); the labels are exact.
    assert [row[0] for row in table.rows[1:]] == [f"Row {n:02d}" for n in range(1, 41)]
    assert table.page == 1
    assert {box.page for box in table.bboxes} == {1, 2}
    body = [e.text for e in document.elements if e.kind not in {"header", "footer"}]
    assert body[-1] == "The paragraph after the table."


def _split(second_columns):
    raw = platform("ruled_table")
    for element in raw:
        if element["type"] == "Table" and element["metadata"]["page_number"] == 2:
            cells = "".join(f"<td>c{i}</td>" for i in range(second_columns))
            element["metadata"]["text_as_html"] = f"<table><tr>{cells}</tr></table>"
    return raw


def test_a_next_page_table_with_other_columns_is_not_joined():
    document = shape_unstructured(_split(3))

    assert sum(e.kind == "table" for e in document.elements) == 2


def test_a_table_after_body_text_on_the_next_page_is_not_joined():
    raw = platform("ruled_table")
    at = next(i for i, e in enumerate(raw) if e["type"] == "Table" and e["metadata"]["page_number"] == 2)
    text = {**raw[at + 1], "text": "A paragraph opens page 2.", "element_id": "x"}
    raw.insert(at, text)

    document = shape_unstructured(raw)

    assert sum(e.kind == "table" for e in document.elements) == 2
