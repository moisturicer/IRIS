"""Unstructured shaping with IRIS's own PDF evidence (IR-1057, ADR-067 decisions 5-7)."""

import json
from io import BytesIO, StringIO

from django.core.management import call_command

from apps.ai.chunking.values import ChunkingOptions
from apps.ai.extraction.shaping_unstructured import shape_unstructured, shaping_report
from apps.ai.ingestion.pipeline import build_chunk_set
from apps.documents.pdf_evidence import reader
from apps.documents.pdf_evidence.tests.thesis import thesis_pdf
from .fixtures import DIRECTORY, FIXTURES, pdf_bytes
from .unstructured_vendor import recording


def element(kind, text, page=1, top=500, element_id=None, **metadata):
    box = {"points": [[250, top], [250, top + 50], [1500, top + 50], [1500, top]],
           "system": "PixelSpace", "layout_width": 2125, "layout_height": 2750}
    return {"type": kind, "element_id": element_id or f"id-{text}", "text": text,
            "metadata": {"page_number": page, "coordinates": box, **metadata}}


def evidence(pages=1, **parts):
    return {"reader": "pdf-evidence-1", "error": "", "page_count": pages,
            "pages": [{"page": n, "width": 612.0, "height": 792.0, "has_text_layer": False}
                      for n in range(1, pages + 1)],
            "bookmarks": [], "page_labels": None, "contents": [], **parts}


def headings(document):
    return [(e.text, e.level, e.level_source) for e in document.elements if e.kind == "heading"]


def test_bookmarks_decide_depth_first():
    raw = [element("Title", "Paper", top=200), element("Title", "Methods"),
           element("Title", "Sampling", top=900), element("Title", "2 Results", page=2)]
    marks = [{"title": "Methods", "level": 1, "page": 1}, {"title": "Sampling", "level": 2, "page": 1},
             {"title": "2  Results", "level": 1, "page": 2}]
    assert headings(shape_unstructured(raw, evidence(2, bookmarks=marks))) == [
        ("Paper", 1, "title"), ("Methods", 2, "bookmark"), ("Sampling", 3, "bookmark"), ("2 Results", 2, "bookmark"),
    ]


def test_contents_entries_decide_when_there_are_no_bookmarks():
    raw = [element("Title", "Abstract"), element("Title", "Introduction", page=2),
           element("Title", "Scope", page=2, top=900), element("Title", "Chapter 2 Review", page=3)]
    contents = [
        {"page": 1, "number": "", "title": "Abstract", "indent": 0.0, "page_label": "i"},
        {"page": 1, "number": "", "title": "Introduction", "indent": 0.0, "page_label": "1"},
        {"page": 1, "number": "", "title": "Scope", "indent": 18.0, "page_label": "1"},
        {"page": 1, "number": "Chapter 2", "title": "Review", "indent": 0.0, "page_label": "2"},
    ]
    assert headings(shape_unstructured(raw, evidence(3, contents=contents))) == [
        ("Abstract", 2, "contents"), ("Introduction", 2, "contents"), ("Scope", 3, "contents"),
        ("Chapter 2 Review", 2, "contents"),
    ]


def test_numbering_decides_below_bookmarks_and_contents():
    raw = [element("Title", "2 Methods"), element("Title", "2.1 Sampling", top=900)]
    marks = [{"title": "Methods", "level": 1, "page": 1}]
    assert headings(shape_unstructured(raw, evidence(bookmarks=marks))) == [
        ("2 Methods", 2, "bookmark"), ("2.1 Sampling", 3, "numbering"),
    ]


def line(text, size, bold, top):
    words, left = [], 72.0
    for word in text.split():
        words.append([word, left, top, left + 6 * len(word), top + size])
        left += 6 * len(word) + 3
    return {"box": [72.0, top, left, top + size], "size": size, "bold": bold, "words": words}


def test_font_size_then_bold_decides_unnumbered_headings():
    page = {"page": 1, "width": 612.0, "height": 792.0, "has_text_layer": True, "lines": [
        line("A Study of Rice", 18.0, True, 60), line("Background", 14.0, True, 120),
        line("Prior work", 12.0, True, 200), line("Field notes", 12.0, False, 280),
    ]}
    raw = [element("Title", "A Study of Rice", top=200), element("Title", "Background", top=400),
           element("Title", "Prior work", top=700), element("Title", "Field notes", top=1000)]
    shaped = shape_unstructured(raw, dict(evidence(), pages=[page]))
    assert headings(shaped) == [
        ("A Study of Rice", 1, "title"), ("Background", 2, "font"), ("Prior work", 3, "font"),
        ("Field notes", 4, "font"),
    ]
    assert shaped.title == "A Study of Rice"


def test_one_heading_style_says_nothing_so_parent_id_decides():
    raw = [element("Title", "Paper", element_id="t"), element("Title", "Setting", element_id="s"),
           element("Title", "Weather", element_id="w", parent_id="s")]
    assert headings(shape_unstructured(raw, evidence())) == [
        ("Paper", 1, "title"), ("Setting", 2, "open_section"), ("Weather", 3, "parent_id"),
    ]


def test_known_thesis_headings_are_top_level_and_others_nest_under_the_open_section():
    raw = [element("Title", "Chapter 1"), element("Title", "Rationale", top=900),
           element("Title", "Limits", top=1500), element("Title", "Acknowledgments", page=2),
           element("Title", "Appendix B Forms", page=3)]
    assert headings(shape_unstructured(raw, evidence(3))) == [
        ("Chapter 1", 2, "known_heading"), ("Rationale", 3, "open_section"),
        ("Limits", 3, "open_section"), ("Acknowledgments", 2, "known_heading"),
        ("Appendix B Forms", 2, "known_heading"),
    ]


def test_evidence_the_reader_failed_on_is_not_read():
    raw = [element("Title", "Methods"), element("Title", "Sampling", top=900)]
    marks = [{"title": "Sampling", "level": 3, "page": 1}]
    failed = dict(evidence(bookmarks=marks), error="unreadable")
    assert headings(shape_unstructured(raw, failed)) == [
        ("Methods", 1, "title"), ("Sampling", 2, "open_section"),
    ]


def printed(document):
    return {e.page: e.printed_page_number for e in document.elements}


def test_page_labels_win_then_page_number_text_then_the_sequence_fills_gaps():
    raw = [element("NarrativeText", "Front", page=1), element("NarrativeText", "Body", page=2),
           element("PageNumber", "- 7 -", page=2), element("NarrativeText", "Chapter opens", page=3),
           element("NarrativeText", "More", page=4), element("Footer", "Page 9 of 40", page=4),
           element("NarrativeText", "Unnumbered", page=5), element("Footer", "Journal 2024", page=5)]
    shaped = shape_unstructured(raw, evidence(5, page_labels=["ii", "", "", "", ""]))
    assert printed(shaped) == {1: "ii", 2: "7", 3: "8", 4: "9", 5: None}


def test_a_gap_the_sequence_contradicts_stays_unnumbered():
    raw = [element("PageNumber", "3", page=1), element("NarrativeText", "x", page=2),
           element("PageNumber", "9", page=3)]
    assert printed(shape_unstructured(raw, evidence(3))) == {1: "3", 2: None, 3: "9"}


def read(pdf):
    return reader.read(BytesIO(pdf), max_pages=50)


def fixture(name):
    return recording(name), read(pdf_bytes(FIXTURES[name]))


def test_numbered_headings_nest_print_their_pages_and_highlight_their_lines():
    raw, pdf = fixture("numbered_headings")
    shaped = shape_unstructured(raw, pdf)
    assert headings(shaped) == [
        ("1 Introduction", 2, "numbering"), ("1.1 Background", 3, "numbering"),
        ("2 Methods", 2, "numbering"), ("3 Results", 2, "numbering"),
    ]
    assert {e.page: e.printed_page_number for e in shaped.elements} == {1: "1", 2: "2"}
    introduction = next(e for e in shaped.elements if e.text == "1 Introduction")
    words = next(l for l in pdf["pages"][0]["lines"] if l["words"][0][0] == "1" and l["size"] == 14.0)
    box = introduction.bboxes[0]
    assert [box.left, box.top, box.right, box.bottom] == words["box"]


def test_a_box_whose_words_do_not_spell_the_element_keeps_the_element_box():
    raw, pdf = fixture("two_columns")
    unmatched = shape_unstructured(raw)
    shaped = shape_unstructured(raw, pdf)
    interleaved = next(e for e in shaped.elements if e.text.startswith("Left column one opens. Right"))
    assert interleaved.bboxes == next(e for e in unmatched.elements if e.text == interleaved.text).bboxes
    assert shaping_report(raw, pdf)["line_boxes"] == {"matched": 2, "fallback": 1}


def test_a_page_with_no_text_layer_keeps_element_boxes():
    raw = [element("NarrativeText", "Scanned words")]
    shaped = shape_unstructured(raw, evidence())
    assert shaped.elements[0].bboxes == shape_unstructured(raw).elements[0].bboxes
    assert shaping_report(raw, evidence())["line_boxes"] == {"no_text_layer": 1}


def test_a_thesis_reads_bookmarks_and_roman_labels_from_its_own_pdf():
    raw = [element("Title", "A Thesis About Evidence", page=1, top=400),
           element("Title", "Table of Contents", page=2, top=250),
           element("NarrativeText", "", page=3),
           element("Title", "1 Introduction", page=4, top=250),
           element("Title", "1.1 Background", page=4, top=450),
           element("Title", "2 Methods", page=5, top=250)]
    shaped = shape_unstructured(raw, read(thesis_pdf()))
    assert headings(shaped) == [
        ("A Thesis About Evidence", 1, "title"), ("Table of Contents", 2, "font"),
        ("1 Introduction", 2, "bookmark"), ("1.1 Background", 3, "bookmark"),
        ("2 Methods", 2, "bookmark"),
    ]
    assert printed(shaped) == {1: "i", 2: "ii", 3: "iii", 4: "1", 5: "2"}


def test_citations_from_an_unstructured_document_highlight_lines_under_nested_headings():
    raw, pdf = fixture("numbered_headings")
    chunks = build_chunk_set(shape_unstructured(raw, pdf), ChunkingOptions()).chunks
    background = next(c for c in chunks if "Background material" in c.text)
    assert background.context_path == ("1 Introduction", "1.1 Background")
    lines = {tuple(l["box"]) for page in pdf["pages"] for l in page["lines"]}
    assert background.bboxes and all(
        (b.left, b.top, b.right, b.bottom) in lines for b in background.bboxes)


def test_the_report_names_each_heading_signal_and_line_box_outcome():
    raw, pdf = fixture("numbered_headings")
    report = shaping_report(raw, pdf)
    assert report["signals"] == {"numbering": 4}
    assert report["line_boxes"] == {"matched": 8}
    assert report["printed_pages"] == [1, 2]
    assert report["headings"][1] == ("1.1 Background", 3, "numbering")


def test_the_report_command_prints_signals_and_rates(tmp_path):
    result = tmp_path / "result.json"
    result.write_text(json.dumps(recording("two_columns")), encoding="utf-8")
    out = tmp_path / "report.json"
    call_command("report_unstructured_shaping", "--pair", str(result),
                 str(DIRECTORY / FIXTURES["two_columns"].filename), "--out", str(out),
                 stdout=StringIO())
    report = json.loads(out.read_text(encoding="utf-8"))["two_columns.pdf"]
    assert (report["match_rate"], report["fallback_rate"], report["no_text_layer_rate"]) == (
        0.667, 0.333, 0.0)
    assert report["signals"] == {"title": 1}


def test_every_layout_fixture_that_prints_its_page_numbers_carries_them():
    for name, pages in (("numbered_headings", 2), ("two_columns", 1), ("table_across_pages", 2)):
        shaped = shape_unstructured(*fixture(name))
        assert {e.page: e.printed_page_number for e in shaped.elements} == {
            n: str(n) for n in range(1, pages + 1)}, name


def test_a_bookmarked_title_stays_the_title_and_known_headings_outrank_parent_id():
    raw = [element("Title", "Rice Study", element_id="t"),
           element("Title", "Field work", element_id="f", top=900),
           element("Title", "References", element_id="r", page=2, parent_id="f")]
    marks = [{"title": "Rice Study", "level": 1, "page": 1}]
    shaped = shape_unstructured(raw, evidence(2, bookmarks=marks))
    assert headings(shaped) == [
        ("Rice Study", 1, "title"), ("Field work", 2, "open_section"), ("References", 2, "known_heading"),
    ]
    assert shaped.title == "Rice Study"


def test_a_running_header_repeating_a_heading_lends_it_no_style():
    page = {"page": 1, "width": 612.0, "height": 792.0, "has_text_layer": True, "lines": [
        line("Background", 8.0, False, 20), line("Background", 14.0, True, 120),
        line("Prior work", 12.0, True, 200),
    ]}
    raw = [element("Title", "1 Study"), element("Title", "Background", top=400),
           element("Title", "Prior work", top=700)]
    assert headings(shape_unstructured(raw, dict(evidence(), pages=[page]))) == [
        ("1 Study", 2, "numbering"), ("Background", 2, "font"), ("Prior work", 3, "font"),
    ]


def test_a_roman_looking_word_in_a_footer_is_not_a_page_number():
    raw = [element("Footer", "DC", page=1), element("Footer", "xii", page=2)]
    assert printed(shape_unstructured(raw, evidence(2))) == {1: None, 2: "xii"}
