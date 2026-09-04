"""The Docling → IRIS translation (IR-107).

Pure: a dict in, a ``NormalizedDocument`` out. No Django, no network, no
container. That is the point of keeping the mapping separate from the HTTP
client — the part with all the judgement in it is the part that needs no
infrastructure to test.

The fixtures below are hand-written ``DoclingDocument`` payloads in the shape
docling-serve returns under ``document.json_content``.
"""

from apps.ai.chunking.document import (
    CAPTION,
    HEADING,
    LIST_ITEM,
    PARAGRAPH,
    TABLE_HEADER,
    TABLE_ROW,
)
from apps.ai.extraction.docling_mapping import normalized_document_from_docling


def _text_item(ref, label, text, *, page=None, bbox=None, level=None):
    item = {"self_ref": ref, "label": label, "text": text}
    if level is not None:
        item["level"] = level
    if page is not None:
        prov = {"page_no": page}
        if bbox is not None:
            prov["bbox"] = bbox
        item["prov"] = [prov]
    return item


def _topleft(left, top, right, bottom):
    return {"l": left, "t": top, "r": right, "b": bottom, "coord_origin": "TOPLEFT"}


def _doc(*, texts=(), tables=(), groups=(), body_refs=None, pages=None, name="thesis.pdf"):
    payload = {
        "name": name,
        "texts": list(texts),
        "tables": list(tables),
        "pictures": [],
        "groups": list(groups),
        "pages": pages if pages is not None else {"1": {"size": {"width": 612.0, "height": 792.0}}},
    }
    if body_refs is not None:
        payload["body"] = {"children": [{"$ref": ref} for ref in body_refs]}
    return payload


# ---------------------------------------------------------------------------
# Reading order
# ---------------------------------------------------------------------------


def test_reading_order_follows_body_children_not_array_order():
    doc = _doc(
        texts=[
            _text_item("#/texts/0", "text", "second"),
            _text_item("#/texts/1", "text", "first"),
        ],
        body_refs=["#/texts/1", "#/texts/0"],
    )

    result = normalized_document_from_docling(doc)

    assert [e.text for e in result.elements] == ["first", "second"]


def test_falls_back_to_array_order_when_body_is_absent():
    doc = _doc(
        texts=[
            _text_item("#/texts/0", "text", "alpha"),
            _text_item("#/texts/1", "text", "beta"),
        ]
    )

    result = normalized_document_from_docling(doc)

    assert [e.text for e in result.elements] == ["alpha", "beta"]


def test_groups_are_traversed_into():
    doc = _doc(
        texts=[
            _text_item("#/texts/0", "list_item", "one"),
            _text_item("#/texts/1", "list_item", "two"),
        ],
        groups=[{"self_ref": "#/groups/0", "children": [{"$ref": "#/texts/0"}, {"$ref": "#/texts/1"}]}],
        body_refs=["#/groups/0"],
    )

    result = normalized_document_from_docling(doc)

    assert [(e.kind, e.text) for e in result.elements] == [
        (LIST_ITEM, "one"),
        (LIST_ITEM, "two"),
    ]


def test_a_ref_referenced_twice_is_emitted_once():
    """A malformed body that visits the same item twice must not duplicate
    content — a duplicated element would be embedded and retrieved twice."""
    doc = _doc(
        texts=[_text_item("#/texts/0", "text", "only once")],
        body_refs=["#/texts/0", "#/texts/0"],
    )

    result = normalized_document_from_docling(doc)

    assert [e.text for e in result.elements] == ["only once"]


def test_a_dangling_ref_is_skipped_rather_than_raising():
    doc = _doc(
        texts=[_text_item("#/texts/0", "text", "present")],
        body_refs=["#/texts/9", "#/texts/0"],
    )

    result = normalized_document_from_docling(doc)

    assert [e.text for e in result.elements] == ["present"]


# ---------------------------------------------------------------------------
# Labels and kinds
# ---------------------------------------------------------------------------


def test_section_header_becomes_a_heading_carrying_its_level():
    doc = _doc(texts=[_text_item("#/texts/0", "section_header", "3 Methodology", level=2)])

    (element,) = normalized_document_from_docling(doc).elements

    assert element.kind == HEADING
    assert element.is_heading
    assert element.level == 2


def test_known_labels_map_onto_the_chunker_kinds():
    doc = _doc(
        texts=[
            _text_item("#/texts/0", "paragraph", "a paragraph"),
            _text_item("#/texts/1", "list_item", "an item"),
            _text_item("#/texts/2", "caption", "Figure 1"),
        ]
    )

    kinds = [e.kind for e in normalized_document_from_docling(doc).elements]

    assert kinds == [PARAGRAPH, LIST_ITEM, CAPTION]


def test_an_unknown_label_is_carried_through_as_its_own_kind():
    """``document.py`` promises a kind outside the known set degrades to plain
    text rather than failing the document — and page furniture has to stay
    distinguishable so the normalizer stage can drop it."""
    doc = _doc(
        texts=[
            _text_item("#/texts/0", "page_footer", "Page 12 of 340"),
            _text_item("#/texts/1", "formula", "E = mc^2"),
        ]
    )

    kinds = [e.kind for e in normalized_document_from_docling(doc).elements]

    assert kinds == ["page_footer", "formula"]


def test_elements_with_no_text_are_dropped():
    doc = _doc(
        texts=[
            _text_item("#/texts/0", "text", "   "),
            _text_item("#/texts/1", "text", ""),
            _text_item("#/texts/2", "text", "kept"),
        ]
    )

    assert [e.text for e in normalized_document_from_docling(doc).elements] == ["kept"]


def test_element_text_is_stripped_but_otherwise_untouched():
    """Cleaning belongs to the FTS flattening, not here: this text is what
    gets embedded, and mangling it would mangle the vector."""
    doc = _doc(texts=[_text_item("#/texts/0", "text", "  Café — naïve (50%)  ")])

    (element,) = normalized_document_from_docling(doc).elements

    assert element.text == "Café — naïve (50%)"


# ---------------------------------------------------------------------------
# Title
# ---------------------------------------------------------------------------


def test_the_first_title_item_becomes_the_document_title():
    doc = _doc(
        texts=[
            _text_item("#/texts/0", "title", "Optimization of Tilapia Feed Conversion"),
            _text_item("#/texts/1", "text", "body"),
        ]
    )

    result = normalized_document_from_docling(doc)

    assert result.title == "Optimization of Tilapia Feed Conversion"


def test_a_title_item_is_also_kept_as_a_heading():
    """It is the document's top heading as well as its name — dropping it
    would break the context path of everything under it."""
    doc = _doc(texts=[_text_item("#/texts/0", "title", "A Thesis")])

    (element,) = normalized_document_from_docling(doc).elements

    assert (element.kind, element.level) == (HEADING, 1)


def test_the_docling_name_is_the_title_when_there_is_no_title_item():
    doc = _doc(texts=[_text_item("#/texts/0", "text", "body")], name="2024-thesis.pdf")

    assert normalized_document_from_docling(doc).title == "2024-thesis.pdf"


def test_the_fallback_title_is_used_when_docling_names_nothing():
    doc = _doc(texts=[_text_item("#/texts/0", "text", "body")], name="")

    result = normalized_document_from_docling(doc, fallback_title="upload-7.pdf")

    assert result.title == "upload-7.pdf"


# ---------------------------------------------------------------------------
# Pages and regions
# ---------------------------------------------------------------------------


def test_page_sizes_are_carried_through_keyed_by_int():
    doc = _doc(
        texts=[_text_item("#/texts/0", "text", "x")],
        pages={
            "1": {"size": {"width": 612.0, "height": 792.0}},
            "2": {"size": {"width": 595.0, "height": 842.0}},
        },
    )

    result = normalized_document_from_docling(doc)

    assert result.page_sizes == {1: (612.0, 792.0), 2: (595.0, 842.0)}


def test_a_topleft_bbox_is_stored_unchanged():
    doc = _doc(
        texts=[_text_item("#/texts/0", "text", "x", page=1, bbox=_topleft(72.0, 100.0, 540.0, 130.0))]
    )

    (element,) = normalized_document_from_docling(doc).elements

    assert element.page == 1
    assert (element.bbox.left, element.bbox.top, element.bbox.right, element.bbox.bottom) == (
        72.0,
        100.0,
        540.0,
        130.0,
    )
    assert element.bbox.page == 1


def test_a_bottomleft_bbox_is_converted_to_topleft():
    """Docling emits either origin. The stored form is top-left because that
    is what the PDF.js viewport uses, so no consumer can forget to convert."""
    doc = _doc(
        texts=[
            _text_item(
                "#/texts/0",
                "text",
                "x",
                page=1,
                bbox={"l": 72.0, "t": 692.0, "r": 540.0, "b": 662.0, "coord_origin": "BOTTOMLEFT"},
            )
        ],
        pages={"1": {"size": {"width": 612.0, "height": 792.0}}},
    )

    (element,) = normalized_document_from_docling(doc).elements

    assert (element.bbox.top, element.bbox.bottom) == (100.0, 130.0)
    assert (element.bbox.left, element.bbox.right) == (72.0, 540.0)


def test_a_degenerate_bbox_is_dropped_rather_than_stored():
    """A zero-area rect draws a broken highlight. Better no region than a
    wrong one — the page number survives either way."""
    doc = _doc(
        texts=[_text_item("#/texts/0", "text", "x", page=3, bbox=_topleft(72.0, 100.0, 72.0, 100.0))]
    )

    (element,) = normalized_document_from_docling(doc).elements

    assert element.page == 3
    assert element.bbox is None


def test_a_missing_prov_leaves_page_and_bbox_unset():
    doc = _doc(texts=[_text_item("#/texts/0", "text", "no provenance")])

    (element,) = normalized_document_from_docling(doc).elements

    assert element.page is None
    assert element.bbox is None


def test_an_unknown_page_falls_back_to_a_default_height_for_conversion():
    """A prov pointing at a page absent from ``pages`` must not lose the
    element; the conversion uses the default page height instead."""
    doc = _doc(
        texts=[
            _text_item(
                "#/texts/0",
                "text",
                "x",
                page=9,
                bbox={"l": 10.0, "t": 700.0, "r": 100.0, "b": 690.0, "coord_origin": "BOTTOMLEFT"},
            )
        ],
        pages={"1": {"size": {"width": 612.0, "height": 792.0}}},
    )

    (element,) = normalized_document_from_docling(doc).elements

    assert element.page == 9
    assert element.bbox is not None
    assert element.bbox.top < element.bbox.bottom


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def _cell(text, row, col, *, header=False, bbox=None):
    cell = {
        "text": text,
        "start_row_offset_idx": row,
        "end_row_offset_idx": row + 1,
        "start_col_offset_idx": col,
        "end_col_offset_idx": col + 1,
        "column_header": header,
    }
    if bbox is not None:
        cell["bbox"] = bbox
    return cell


def test_a_table_becomes_a_header_row_followed_by_data_rows():
    table = {
        "self_ref": "#/tables/0",
        "label": "table",
        "prov": [{"page_no": 2, "bbox": _topleft(72.0, 100.0, 540.0, 200.0)}],
        "data": {
            "num_rows": 2,
            "num_cols": 2,
            "table_cells": [
                _cell("Species", 0, 0, header=True),
                _cell("Weight", 0, 1, header=True),
                _cell("Tilapia", 1, 0),
                _cell("412 g", 1, 1),
            ],
        },
    }
    doc = _doc(tables=[table], body_refs=["#/tables/0"])

    elements = normalized_document_from_docling(doc).elements

    assert [(e.kind, e.text) for e in elements] == [
        (TABLE_HEADER, "| Species | Weight |"),
        (TABLE_ROW, "| Tilapia | 412 g |"),
    ]


def test_a_table_with_no_header_row_emits_only_data_rows():
    table = {
        "self_ref": "#/tables/0",
        "label": "table",
        "data": {"table_cells": [_cell("a", 0, 0), _cell("b", 0, 1)]},
    }
    doc = _doc(tables=[table], body_refs=["#/tables/0"])

    elements = normalized_document_from_docling(doc).elements

    assert [e.kind for e in elements] == [TABLE_ROW]


def test_table_rows_inherit_the_table_region_when_cells_carry_none():
    table = {
        "self_ref": "#/tables/0",
        "label": "table",
        "prov": [{"page_no": 2, "bbox": _topleft(72.0, 100.0, 540.0, 200.0)}],
        "data": {"table_cells": [_cell("a", 0, 0), _cell("b", 0, 1)]},
    }
    doc = _doc(tables=[table], body_refs=["#/tables/0"])

    (row,) = normalized_document_from_docling(doc).elements

    assert row.page == 2
    assert (row.bbox.top, row.bbox.bottom) == (100.0, 200.0)


def test_a_table_row_region_is_the_union_of_its_own_cells():
    """Falling back to the whole table's box would highlight forty rows to
    cite one. Cell boxes are what make a row citation precise."""
    table = {
        "self_ref": "#/tables/0",
        "label": "table",
        "prov": [{"page_no": 2, "bbox": _topleft(72.0, 100.0, 540.0, 400.0)}],
        "data": {
            "table_cells": [
                _cell("a", 0, 0, bbox=_topleft(72.0, 120.0, 300.0, 140.0)),
                _cell("b", 0, 1, bbox=_topleft(310.0, 118.0, 540.0, 142.0)),
            ]
        },
    }
    doc = _doc(tables=[table], body_refs=["#/tables/0"])

    (row,) = normalized_document_from_docling(doc).elements

    assert (row.bbox.left, row.bbox.top, row.bbox.right, row.bbox.bottom) == (
        72.0,
        118.0,
        540.0,
        142.0,
    )


def test_a_text_item_carrying_a_data_key_is_not_mistaken_for_a_table():
    """Routing on the presence of ``data`` alone would send it into table
    handling, which returns nothing — the element would vanish silently."""
    doc = _doc(
        texts=[{"self_ref": "#/texts/0", "label": "text", "text": "prose", "data": {"x": 1}}],
        body_refs=["#/texts/0"],
    )

    assert [e.text for e in normalized_document_from_docling(doc).elements] == ["prose"]


def test_an_unlabelled_item_carrying_table_cells_is_still_read_as_a_table():
    """The safety net for a label Docling renames or omits."""
    item = {"self_ref": "#/tables/0", "data": {"table_cells": [_cell("a", 0, 0)]}}
    doc = _doc(tables=[item], body_refs=["#/tables/0"])

    assert [e.kind for e in normalized_document_from_docling(doc).elements] == [TABLE_ROW]


def test_a_document_index_is_read_as_a_table():
    item = {
        "self_ref": "#/tables/0",
        "label": "document_index",
        "data": {"table_cells": [_cell("1 Introduction", 0, 0), _cell("1", 0, 1)]},
    }
    doc = _doc(tables=[item], body_refs=["#/tables/0"])

    assert [e.text for e in normalized_document_from_docling(doc).elements] == [
        "| 1 Introduction | 1 |"
    ]


def test_a_table_with_no_cells_emits_nothing():
    doc = _doc(tables=[{"self_ref": "#/tables/0", "label": "table", "data": {}}], body_refs=["#/tables/0"])

    assert normalized_document_from_docling(doc).elements == ()


def test_empty_trailing_cells_do_not_produce_an_empty_row():
    table = {
        "self_ref": "#/tables/0",
        "label": "table",
        "data": {"table_cells": [_cell("", 0, 0), _cell("  ", 0, 1), _cell("real", 1, 0)]},
    }
    doc = _doc(tables=[table], body_refs=["#/tables/0"])

    elements = normalized_document_from_docling(doc).elements

    assert [e.text for e in elements] == ["| real |"]


# ---------------------------------------------------------------------------
# Whole-payload edge cases
# ---------------------------------------------------------------------------


def test_an_empty_payload_produces_an_empty_document():
    result = normalized_document_from_docling({}, fallback_title="x.pdf")

    assert result.elements == ()
    assert result.title == "x.pdf"
    assert result.page_sizes == {}


def test_a_page_entry_without_a_size_is_skipped_not_fatal():
    doc = _doc(texts=[_text_item("#/texts/0", "text", "x")], pages={"1": {}, "2": {"size": {"width": 1.0, "height": 2.0}}})

    assert normalized_document_from_docling(doc).page_sizes == {2: (1.0, 2.0)}
