"""The review text reader's rules (IR-871, ADR-058 §1 as amended). Pure: no
Django, no database, no network. Every PDF is drawn here, so every answer is known."""
import socket

import pytest

from apps.records.review_text import reader, sandbox
from apps.records.review_text.testing import THESIS, blank, pdf, two_columns


@pytest.fixture
def read(tmp_path):
    def _read(data):
        path = tmp_path / "paper.pdf"
        path.write_bytes(data)
        return reader.read(path)
    return _read


def texts(reading):
    return [p["text"] for s in reading["sections"] for p in s["passages"]]


def keys(reading):
    return [s["key"] for s in reading["sections"]]


def test_running_heads_and_page_numbers_are_dropped(read):
    reading = read(pdf(THESIS))
    joined = " ".join(texts(reading)) + " ".join(s["heading"] for s in reading["sections"])
    assert "Community Waste-to-Energy Feasibility" not in joined
    assert not any(t.strip().isdigit() for t in texts(reading))


def test_headings_are_found_by_bold_numbering_and_capitals(read):
    # "INTRODUCTION" is bold; "1.1 ..." numbered and "REVIEW OF ..." in
    # capitals are both in the body font.
    assert keys(read(pdf(THESIS))) == [
        "community waste-to-energy feasibility", "introduction", "background of the study",
        "statement of the problem", "review of related literature",
    ]


def test_a_chapter_line_joins_the_title_under_it(read):
    sections = {s["key"]: s for s in read(pdf(THESIS))["sections"]}
    assert sections["introduction"]["heading"] == "CHAPTER 1 INTRODUCTION"
    assert sections["review of related literature"]["heading"] == "CHAPTER 2 REVIEW OF RELATED LITERATURE"
    assert sections["review of related literature"]["page"] == 3


def test_a_numbered_subheading_is_not_read_as_a_wrapped_heading(read):
    sections = {s["key"]: s for s in read(pdf(THESIS))["sections"]}
    assert sections["background of the study"]["heading"] == "1.1 Background of the Study"


def test_line_end_hyphens_rejoin_a_word_and_keep_a_compound(read):
    body = " ".join(texts(read(pdf(THESIS))))
    assert "government" in body          # "govern-" / "ment": hyphenated to fit
    assert "small-scale plants" in body  # "small-" / "scale": appears whole elsewhere


def test_abbreviations_and_initials_end_no_sentence(read):
    found = texts(read(pdf(THESIS)))
    assert "The municipal government asked for a study, e.g. of costs." in found
    assert "Engr. J. Cruz led it." in found


def test_ruled_tables_are_read_as_rows(read):
    rows = [p for s in read(pdf(THESIS))["sections"] for p in s["passages"] if p["kind"] == "row"]
    assert [r["text"] for r in rows] == ["Technology | Output", "Digestion | 40 kW", "Gasification | 90 kW"]
    assert all(r["regions"] for r in rows)


def test_two_columns_are_split_at_the_gutter(read):
    left = [f"Left line {i} reads on." for i in range(14)]
    right = [f"Right line {i} reads on." for i in range(14)]
    body = " ".join(texts(read(two_columns(left, right))))
    assert body.index("Left line 13") < body.index("Right line 0")


def test_words_are_whole_on_a_line_that_is_not_justified(read):
    # The default x_tolerance (3 pt) is a 12 pt space and merged these (prototype finding 1).
    assert "This study asks whether a plant is feasible." in texts(read(pdf(THESIS)))


def test_each_passage_has_its_page_paragraph_and_regions_in_page_fractions(read):
    for section in read(pdf(THESIS))["sections"]:
        for p in section["passages"]:
            assert p["regions"], p
            assert all(r["page"] == p["page"] or r["page"] == p["page"] + 1 for r in p["regions"])
            for r in p["regions"]:
                assert 0 <= r["left"] < r["right"] <= 1 and 0 <= r["top"] < r["bottom"] <= 1
            assert p["paragraph"] >= 1


def test_a_sentence_over_several_lines_has_a_region_per_line(read):
    # "Landfills" ends line 1, line 2 runs to "small-", and "scale plants." opens line 3.
    found = {p["text"]: p for s in read(pdf(THESIS))["sections"] for p in s["passages"]}
    regions = found["Landfills are near capacity, so the cities look at small-scale plants."]["regions"]
    assert len(regions) == 3
    assert [r["top"] for r in regions] == sorted(r["top"] for r in regions)


def test_section_keys_and_hashes_are_stable_and_change_with_the_text(read):
    first, again = read(pdf(THESIS)), read(pdf(THESIS))
    assert [s["text_hash"] for s in first["sections"]] == [s["text_hash"] for s in again["sections"]]
    edited = [page[:] for page in THESIS]
    edited[1] = edited[1][:-1] + [("para", ["This study asks whether two plants are feasible."])]
    changed = {s["key"]: s["text_hash"] for s in read(pdf(edited))["sections"]}
    original = {s["key"]: s["text_hash"] for s in first["sections"]}
    assert changed["statement of the problem"] != original["statement of the problem"]
    assert changed["review of related literature"] == original["review of related literature"]


def test_a_repeated_heading_gets_its_own_key(read):
    pages = [[("heading", "Summary"), ("para", ["One."])], [("heading", "Summary"), ("para", ["Two."])]]
    assert keys(read(pdf(pages, running_head=None))) == ["summary", "summary#2"]


def test_table_of_contents_lines_and_captions_are_not_headings(read):
    pages = [[
        ("plain", "INTRODUCTION ........ 1"),
        ("plain", "Table 1 Respondents"),
        ("heading", "Methods"),
        ("para", ["We asked people."]),
    ]]
    assert keys(read(pdf(pages, running_head=None))) == ["front-matter", "methods"]


def test_a_paper_with_no_headings_says_so(read):
    reading = read(pdf([[("para", ["Just one paragraph of text here."])]], running_head=None))
    assert keys(reading) == ["front-matter"]
    assert {"code": "no_headings"} in reading["warnings"]


def test_a_scan_has_no_sections_and_names_its_pages(read):
    reading = read(blank(pages=2))
    assert reading["sections"] == [] and reading["page_count"] == 2


def test_a_file_that_is_not_a_pdf_is_unreadable(read):
    with pytest.raises(reader.Unreadable):
        read(b"%PDF-1.7 not really")


def test_the_page_cap_is_over_budget(tmp_path):
    path = tmp_path / "paper.pdf"
    path.write_bytes(pdf(THESIS))
    with pytest.raises(reader.OverBudget):
        reader.read(path, max_pages=2)


def test_no_network_is_touched(read, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the review text reader opened a socket")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    assert texts(read(pdf(THESIS)))


def test_the_reader_imports_nothing_from_django_or_the_ai(tmp_path):
    source = (reader.__file__ and open(reader.__file__, encoding="utf-8").read())
    for forbidden in ("django", "apps.", "httpx", "openai", "requests", "urllib", "socket"):
        assert f"import {forbidden}" not in source and f"from {forbidden}" not in source, forbidden


def test_the_reader_version_names_its_rules_and_pdfplumber(read):
    assert read(pdf(THESIS))["reader"].startswith(f"review-reader-{reader.RULES_VERSION}/pdfplumber-")


def test_every_reading_has_the_stored_shape(read):
    for data in (pdf(THESIS), blank(), two_columns(["a line here"] * 12, ["b line here"] * 12)):
        assert sandbox.valid(read(data))


def test_control_characters_never_reach_stored_text():
    assert reader._clean("ab\x00c\x07d") == "abcd"


def test_a_heading_past_the_column_width_keeps_its_repeat_suffix():
    passages = [{"text": "One.", "page": 1, "paragraph": 1, "kind": "sentence", "regions": []}]
    long = {"heading": "Results " * 40, "page": 1, "passages": passages}
    sections, _ = reader._finish([dict(long), dict(long)], [{"number": 1, "has_words": True}])
    assert [len(s["key"]) <= 255 for s in sections] == [True, True]
    assert sections[0]["key"] != sections[1]["key"] and sections[1]["key"].endswith("#2")


# --- found on the first real paper (a two-column journal article, 2026-11-06) ---

def test_a_footer_across_both_columns_is_dropped_however_low_it_sits(read):
    from apps.records.review_text.testing import journal

    body = " ".join(texts(read(journal())))
    assert "JOURNAL" not in body and "Volume 7" not in body


def test_a_title_across_the_page_does_not_stop_two_columns_being_split(read):
    from apps.records.review_text.testing import journal

    reading = read(journal(pages=1))
    body = " ".join(texts(reading))
    assert body.index("P1L2 line 4") < body.index("P1R0 line 0")


def test_paragraphs_in_a_right_hand_column_are_paragraphs_not_lines(read):
    from apps.records.review_text.testing import journal

    passages = [p for s in read(journal(pages=1))["sections"] for p in s["passages"]]
    right = [p for p in passages if p["text"].startswith("P1R")]
    # Five lines a paragraph, five sentences: one paragraph number each, three in all.
    assert len({p["paragraph"] for p in right}) == 3


def test_a_heading_wraps_only_in_its_own_font_and_size(read):
    from apps.records.review_text.testing import BOLD, headings

    reading = read(headings([(BOLD, 12, "Materials and Methods"), ("Times-BoldItalic", 11, "Review Design")]))
    assert [s["heading"] for s in reading["sections"]] == ["Materials and Methods", "Review Design"]


def test_a_hyphen_at_a_heading_line_end_is_rejoined(read):
    from apps.records.review_text.testing import BOLD, headings

    reading = read(headings([(BOLD, 11, "Conceptual Foundations of Accom-"), (BOLD, 11, "modation")]))
    assert reading["sections"][0]["heading"] == "Conceptual Foundations of Accommodation"


def test_a_few_stray_mid_line_hyphens_do_not_decide_every_break():
    from collections import Counter

    known = Counter({"ad-justment": 2, "adjustment": 9, "small-scale": 3})
    assert reader._keeps_hyphen("ad", "justment", known) is False
    assert reader._keeps_hyphen("small", "scale", known) is True
    assert reader._keeps_hyphen("govern", "ment", Counter()) is False


def test_a_chapter_opening_each_page_is_never_a_running_head(read):
    titles = ["INTRODUCTION", "METHODOLOGY", "RESULTS", "CONCLUSION"]
    pages = [[("plain", f"CHAPTER {n}"), ("plain", title), ("para", [f"Text {n}."])]
             for n, title in enumerate(titles, start=1)]
    headings_found = [s["heading"] for s in read(pdf(pages, running_head=None))["sections"]]
    assert headings_found == [f"CHAPTER {n} {title}" for n, title in enumerate(titles, start=1)]
