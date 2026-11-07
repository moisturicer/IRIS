"""The review text reader's rules (IR-871, ADR-058 §1 as amended). Pure: no
Django, no database, no network. Every PDF is drawn here, so every answer is known."""
import socket

import pytest

from apps.records.review_text import reader, sandbox
from apps.records.review_text.testing import (BODY, THESIS, blank, mixed_font_words, pdf, placed, sized_headings,
                                               two_columns, unruled_table, white_boxed_columns)


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


def test_invisible_boxes_behind_the_lines_make_no_table(read):
    # sample15: every line sits on a white, borderless box. Its edges looked
    # like a two-column grid, so the page read as table rows, a line at a time.
    para = ["The construction industry adds much to the", "growth of the gross domestic product in the",
            "country, as the statistics authority reports."]
    left = [para, ["Delays raise the cost of a project and the", "time it takes, as earlier studies found."]] * 4
    right = [para] * 6
    reading = read(white_boxed_columns(left, right))
    assert not [p for s in reading["sections"] for p in s["passages"] if p["kind"] == "row"]
    assert ("The construction industry adds much to the growth of the gross domestic product in "
            "the country, as the statistics authority reports.") in texts(reading)


def test_a_word_set_partly_in_another_font_stays_whole(read):
    # sample21: the fi ligature, the apostrophe and the dash came from a second
    # font, and each font change split the word ("arti fi cial", "Nursing ' s").
    other = "Helvetica"
    reading = read(mixed_font_words([
        [(BODY, "The use of arti"), (other, "fi"), (BODY, "cial intelligence in Nursing"),
         (other, "'"), (BODY, "s care models grows.")],
        [(BODY, "The Human"), (other, "-"), (BODY, "AI model guides the curriculum.")],
        # A narrow justified space, still a space character, between two fonts.
        [(BODY, "The students' ", 1.6), (other, "perceptions"), (BODY, " were mixed.")],
    ]))
    assert texts(reading) == ["The use of artificial intelligence in Nursing's care models grows.",
                              "The Human-AI model guides the curriculum.",
                              "The students' perceptions were mixed."]


def test_a_captions_second_line_and_an_unruled_tables_header_are_not_headings(read):
    # sample23: a bold caption ran onto a line of its own ("Sustainability"),
    # read as a heading. sample14: an unruled table's bold header row, its
    # cells far apart, read as one.
    reading = read(unruled_table(
        ["Table 3. Result of the test on energy as one of the key concepts of", "Sustainability"],
        ["Cases", "Sum of Squares", "Mean Square"],
        [["Between groups", "1.204", "0.602"], ["Within groups", "48.310", "0.211"]]))
    assert keys(reading) == ["results", "discussion"]


@pytest.mark.parametrize("number", ["2.", "I.", "1"])
def test_a_numbered_heading_with_a_wide_gap_after_its_number_is_found(read, number):
    # sample16, sample30, Sample4: a tab after the number, 19 to 26 pt wide.
    reading = read(mixed_font_words([[("Times-Bold", number, -22), ("Times-Bold", "RELATED LITERATURE")],
                                     [(BODY, "Earlier studies of delays in construction are reviewed here.")]]))
    assert keys(reading) == ["related literature"]


def test_a_bold_word_off_to_the_right_is_a_table_cell_not_a_heading(read):
    # sample13: a stacked header cell, "Standard" over "Deviation", in the
    # right half of the page, read as two headings.
    body = "The table shows the mean score of each statement that the students rated."
    reading = read(placed([[
        (72, "Times-Bold", 12, "Results"), (72, BODY, 11, body), (72, BODY, 11, body),
        (400, "Times-Bold", 11, "Standard"), (400, "Times-Bold", 11, "Deviation"),
        (72, BODY, 11, body), (72, BODY, 11, body),
        (250, "Times-Bold", 12, "Discussion"), (72, BODY, 11, body),
    ]]))
    assert keys(reading) == ["results", "discussion"]


BODY_TEXT = ["The study asked how the curriculum prepares nurses for new tools in care.",
             "It reads the literature and proposes a model for teaching the use of them."]


@pytest.mark.parametrize("font", [BODY, "Times-Italic"])
def test_a_heading_set_larger_than_the_body_is_found(read, font):
    # sample21: 12 pt headings over a 10 pt body, in fonts not named bold.
    reading = read(sized_headings([("Introduction", BODY_TEXT), ("Paper Design", BODY_TEXT),
                                   ("Theoretical Framework", BODY_TEXT)], heading_font=font))
    assert keys(reading) == ["introduction", "paper design", "theoretical framework"]


@pytest.mark.parametrize("line", [
    "Nurses must learn to question what a tool suggests.",
    "Error = | predicted probability - actual class |",   # sample6: a formula
    "Cando, Jean Marie *, Lizares, Estela, Villacastin",  # sample12: authors
    "Judith Ismael, PhD 3 , Sitti Ali, MAN 1",           # sample21: authors and marks
])
def test_a_larger_line_that_is_no_heading_stays_text(read, line):
    reading = read(sized_headings([("Introduction", BODY_TEXT), (line, BODY_TEXT)]))
    assert keys(reading) == ["introduction"]


@pytest.mark.parametrize("fontname, bold", [
    ("NKOLOK+AdvOTab3e3698.B", True), ("ABCDEF+Arial-BoldMT", True), ("Calibri,Bold", True),
    ("Helvetica-Black", True), ("MyriadPro-Semibold", True), ("Garamond-BI", True),
    ("NKONAI+AdvOT29dffb6a.I", False), ("Times-Roman", False), ("Bodoni-Roman", False),
])
def test_bold_is_read_from_the_fonts_name(fontname, bold):
    assert reader.is_bold(fontname) is bold


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


def test_a_paper_with_no_headings_is_one_document_and_says_why(read):
    # Changed deliberately (IR-871, fail safe): no headings is one of the
    # shapes that make sections untrustworthy, so the paper is one section.
    reading = read(pdf([[("para", ["Just one paragraph of text here."])]], running_head=None))
    assert keys(reading) == ["document"]
    assert {"code": "sections_unreliable", "reasons": ["no_headings"]} in reading["warnings"]


# --- fail safe on layouts the rules don't know (IR-871) ---

def _sectioned(*sections):
    """`_unreliable`'s input: (key, number of passages) per section."""
    return [{"key": k, "passages": [{}] * n} for k, n in sections]


def test_good_sections_are_trusted():
    assert reader._unreliable(_sectioned(("front-matter", 3), ("introduction", 9), ("methods", 12))) == []


def test_about_as_many_headings_as_sentences_is_not_trusted():
    # Capitals in a table, or a form, read as headings.
    many = _sectioned(*[(f"row {n}", 1) for n in range(12)])
    assert reader._unreliable(many) == ["too_many_headings"]


def test_one_heading_over_and_over_is_not_trusted():
    repeated = _sectioned(("journal", 9), *[(f"journal#{n}", 9) for n in range(2, 7)], ("methods", 9))
    assert "repeated_headings" in reader._unreliable(repeated)


def test_headings_over_mostly_nothing_are_not_trusted():
    hollow = _sectioned(*[(f"heading {n}", 0) for n in range(6)], ("results", 30))
    assert reader._unreliable(hollow) == ["mostly_empty_sections"]


def test_an_untrusted_paper_keeps_every_sentence_with_its_page(read):
    # A form's worth of capitals lines over a few sentences: twelve headings
    # of three lines each, guessed wrong.
    page = [("plain", f"FIELD {chr(65 + n // 26)}{chr(65 + n % 26)} LABEL") for n in range(36)] + [
        ("para", ["The only paragraph has two sentences. It ends here."])]
    reading = read(pdf([page[:18], page[18:]], running_head=None, numbered=False))
    assert keys(reading) == ["document"]
    assert texts(reading) == ["The only paragraph has two sentences.", "It ends here."]
    assert all(p["page"] == 2 and p["regions"] for p in reading["sections"][0]["passages"])
    assert reading["warnings"][0]["code"] == "sections_unreliable"


def test_a_footnote_in_a_smaller_font_is_its_own_passage(read):
    from apps.records.review_text.testing import BODY, headings

    reading = read(headings([
        ("Times-Bold", 12, "Results"),
        (BODY, 12, "The plant runs on about forty tonnes"),
        (BODY, 12, "of waste each day."),
        (BODY, 8, "1 Measured over eight weeks in 2024."),
    ]))
    found = texts(reading)
    assert "The plant runs on about forty tonnes of waste each day." in found
    assert "1 Measured over eight weeks in 2024." in found


def test_text_with_no_characters_behind_it_is_unreadable_not_stored(tmp_path, monkeypatch):
    path = tmp_path / "paper.pdf"
    path.write_bytes(pdf(THESIS))
    monkeypatch.setattr(reader, "_unmapped_share", lambda sections: 0.5)
    with pytest.raises(reader.Unreadable):
        reader.read(path)


def test_a_few_unmapped_characters_are_kept_and_counted():
    sections = [{"passages": [{"text": "a b c (cid:12) d e f g h i"}, {"text": "j k l m n o p q r �"}]}]
    assert reader._unmapped_share(sections) == 0.1


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


# --- found on papers from other fields (samples 2-5, 2026-11-06) ---

@pytest.mark.parametrize("line", [
    "ICCOINS.2016.7783277", "10.2190/4YNU-4TMB-22DJ-AN4W", "QUADCOPTER_CONTROL_WITH_A_PHONE",
    "2020-2021", "5", "JET",
])
def test_identifiers_years_and_numbers_are_never_headings(line):
    assert reader._wordy(line) is False


@pytest.mark.parametrize("line", [
    "II. REVIEW OF RELATED LITERATURE", "S.Y. 2018-2019 Decision Tree Result", "2.1 Literature profiling",
])
def test_headings_with_some_numbers_are_still_headings(line):
    assert reader._wordy(line) is True


def test_a_year_or_doi_is_not_section_numbering():
    assert not reader.SINGLE_LEVEL.match("2020 IEEE International Conference on Safety")
    assert not reader.MULTI_LEVEL.match("10.2190 Journal of College Retention")
    assert reader.MULTI_LEVEL.match("3.2 Synthesis results")


@pytest.mark.parametrize("heading, key", [
    ("II. REVIEW OF RELATED LITERATURE", "review of related literature"),
    ("A. Decision Tree Result", "decision tree result"),
    ("CHAPTER 2 METHODOLOGY", "methodology"),
])
def test_roman_and_lettered_numbering_leaves_the_key(heading, key):
    passages = [{"text": "Text.", "page": 1, "paragraph": 1, "kind": "sentence", "regions": []}]
    sections, _ = reader._finish([{"heading": heading, "page": 1, "passages": passages}],
                                 [{"number": 1, "has_words": True}])
    assert sections[0]["key"] == key


def test_a_small_capitals_word_split_after_its_first_letter_is_rejoined():
    first = {"text": "I", "x0": 132.1, "x1": 135.9, "top": 550.1, "bottom": 560.1, "size": 10.0}
    rest = {"text": "NTRODUCTION", "x0": 135.8, "x1": 197.0, "top": 551.6, "bottom": 559.6, "size": 8.0}
    other = {"text": "Next", "x0": 205.0, "x1": 230.0, "top": 550.1, "bottom": 560.1, "size": 10.0}
    assert [w["text"] for w in reader._join_small_caps([first, rest, other])] == ["INTRODUCTION", "Next"]


def test_a_single_letter_word_in_the_same_size_is_left_alone():
    a = {"text": "A", "x0": 72, "x1": 80, "top": 100, "bottom": 110, "size": 10.0}
    word = {"text": "STUDY", "x0": 81, "x1": 120, "top": 100, "bottom": 110, "size": 10.0}
    assert [w["text"] for w in reader._join_small_caps([a, word])] == ["A", "STUDY"]


# --- paragraphs and lists, found on a single-column student paper (sample 6) ---

def _paragraphs(reading):
    """Each paragraph's text, joined, in order."""
    out = {}
    for s in reading["sections"]:
        for p in s["passages"]:
            out.setdefault(p["paragraph"], []).append(p["text"])
    return [" ".join(v) for v in out.values()]


LONG = "words that run all the way across the line to its right edge here"


def test_each_list_item_is_its_own_passage_with_its_hanging_lines(read):
    from apps.records.review_text.testing import BODY, BOLD, placed

    reading = read(placed([[
        (72, BOLD, 12, "Limitations"),
        (108, BODY, 11, "The study has several limitations, listed here:"),
        (90, BODY, 11, "•"), (108, BODY, 11, "The sample was small and " + LONG, True),
        (108, BODY, 11, "and so it may not generalize."),
        (90, BODY, 11, "•"), (108, BODY, 11, "Only some factors were studied.", True),
    ]]))
    paragraphs = _paragraphs(reading)
    assert any(p.endswith("and so it may not generalize.") and "sample was small" in p for p in paragraphs)
    assert any(p.endswith("Only some factors were studied.") and "sample" not in p for p in paragraphs)


def test_headings_and_body_at_different_margins_keep_paragraphs_whole(read):
    from apps.records.review_text.testing import BODY, BOLD, placed

    reading = read(placed([[
        (72, BOLD, 12, "3.1 Revision to Sampling"),
        (144, BODY, 11, "Initially, the study planned to employ random"),
        (108, BODY, 11, "sampling across the population. However, it changed"),
        (108, BODY, 11, "near the end of the term."),
        (144, BODY, 11, "The final study used convenience sampling."),
    ]]))
    assert _paragraphs(reading) == [
        "Initially, the study planned to employ random sampling across the population. "
        "However, it changed near the end of the term.",
        "The final study used convenience sampling.",
    ]


def test_a_reference_with_a_hanging_indent_is_one_paragraph(read):
    from apps.records.review_text.testing import BODY, BOLD, placed

    reading = read(placed([[
        (72, BOLD, 12, "References"),
        (72, BODY, 11, "Cruz, J. (2020). A study of " + LONG),
        (90, BODY, 11, "Journal of Cebu Studies, 3(1), 1-9."),
        (72, BODY, 11, "Lim, A. (2021). Another study of " + LONG),
        (90, BODY, 11, "Philippine Review, 4(2), 10-20."),
    ]]))
    paragraphs = _paragraphs(reading)
    assert len(paragraphs) == 2
    assert paragraphs[0].startswith("Cruz") and paragraphs[0].endswith("3(1), 1-9.")


def test_an_indented_paragraph_opening_a_page_is_not_glued_to_the_last(read):
    from apps.records.review_text.testing import BODY, BOLD, placed

    first = [(72, BOLD, 12, "Findings"), (108, BODY, 11, "The first paragraph opens here and"),
             (72, BODY, 11, "ends on this page.")]
    # A page set mostly at the indent, as a list-heavy page is.
    second = [(108, BODY, 11, "The second paragraph opens the page"), (72, BODY, 11, "and ends here."),
              (108, BODY, 11, "A third one, indented."), (108, BODY, 11, "A fourth one, indented.")]
    paragraphs = _paragraphs(read(placed([first, second])))
    assert paragraphs[:2] == ["The first paragraph opens here and ends on this page.",
                              "The second paragraph opens the page and ends here."]


def test_a_bold_word_in_mid_sentence_alone_on_its_line_is_not_a_heading(read):
    from apps.records.review_text.testing import BODY, BOLD, placed

    reading = read(placed([[(72, BOLD, 12, "Consent"), (72, BODY, 11, "Participation is"),
                            (72, BOLD, 11, "completely"), (72, BODY, 11, "voluntary.")]]))
    assert [s["heading"] for s in reading["sections"]] == ["Consent"]


# --- back matter: forms and reference lists (sample 6, sample 1) ---

def test_a_paragraph_drawn_as_one_box_per_line_reads_as_text_once(read):
    from apps.records.review_text.testing import boxed_paragraph

    reading = read(boxed_paragraph([
        "This survey aims to gather information",
        "related to student attendance and school",
        "experiences. Participation is voluntary.",
    ]))
    assert texts(reading) == [
        "This survey aims to gather information related to student attendance and school experiences.",
        "Participation is voluntary.",
    ]
    assert all(p["kind"] == "sentence" for s in reading["sections"] for p in s["passages"])


def test_a_numbered_list_item_is_its_own_passage_and_its_number_ends_no_sentence(read):
    from apps.records.review_text.testing import BODY, BOLD, placed

    reading = read(placed([[
        (72, BOLD, 12, "Consent to Participate"),
        (72, BODY, 11, "By proceeding, you confirm that:"),
        (90, BODY, 11, "1."), (108, BODY, 11, "You understand the purpose of this research.", True),
        (90, BODY, 11, "2."), (108, BODY, 11, "You are participating voluntarily.", True),
    ]]))
    assert texts(reading) == ["By proceeding, you confirm that:",
                              "1. You understand the purpose of this research.",
                              "2. You are participating voluntarily."]


def test_a_reference_opening_the_next_page_is_a_new_entry(read):
    from apps.records.review_text.testing import BODY, BOLD, placed

    first = [(72, BOLD, 12, "References"),
             (72, BODY, 11, "Bartunek, J. M. (1987). First-order change and " + LONG),
             (90, BODY, 11, "https://doi.org/10.1177/0021886387")]
    second = [(72, BODY, 11, "Boateng, G. O. (2018). Best practices for " + LONG),
              (90, BODY, 11, "Frontiers in Public Health, 6, 149.")]
    paragraphs = _paragraphs(read(placed([first, second])))
    assert len(paragraphs) == 2 and paragraphs[1].startswith("Boateng")


@pytest.mark.parametrize("text, font", [
    ("•", "Times-Roman"), ("", "Symbol"), ("l", "Wingdings-Regular"), ("§", "ABCDEF+Wingdings"),
])
def test_a_word_bullet_in_any_of_its_fonts_is_a_list_mark(text, font):
    assert reader._is_mark({"text": text, "fontname": font})


def test_a_single_letter_in_a_text_font_is_not_a_list_mark():
    assert not reader._is_mark({"text": "l", "fontname": "TimesNewRomanPSMT"})
    assert not reader._is_mark({"text": "A", "fontname": "Arial"})


# --- reference lists, every style in the samples (2026-11-06) ---

def test_one_line_entries_at_the_same_margin_are_separate(read):
    from apps.records.review_text.testing import BODY, BOLD, placed

    reading = read(placed([[
        (72, BOLD, 12, "References"),
        (72, BODY, 11, "Mohsan, S. (2023). Unmanned aerial vehicles: practical aspects and"),
        (96, BODY, 11, "applications. Intelligent Service Robotics."),
        (72, BODY, 11, "PID controller. (2023). https://en.wikipedia.org/wiki/PID"),
        (72, BODY, 11, "Rovira, A. (2022). A review. Ad Hoc Networks, 130."),
    ]]))
    assert len(_paragraphs(reading)) == 3


def test_a_web_address_on_its_own_line_continues_its_entry(read):
    from apps.records.review_text.testing import BODY, BOLD, placed

    reading = read(placed([[
        (72, BOLD, 12, "References"),
        (72, BODY, 11, "Mishkin, F. S. (2019). The economics of money and " + LONG),
        (90, BODY, 11, "(12th ed.)."),
        (102, BODY, 11, "https://books.google.com/books/about"),
    ]]))
    paragraphs = _paragraphs(reading)
    assert len(paragraphs) == 1 and paragraphs[0].endswith("https://books.google.com/books/about")


def test_a_page_number_that_runs_on_is_not_a_numbered_list_item(read):
    from apps.records.review_text.testing import BODY, BOLD, placed

    reading = read(placed([[
        (72, BOLD, 12, "References"),
        (72, BODY, 11, "Zhang, C. (2023). A fusion strategy for drones, Drones, 7(1), " + LONG),
        (90, BODY, 11, "34."), (110, BODY, 11, "https://doi.org/10.3390/drones7010034", True),
    ]]))
    assert len(_paragraphs(reading)) == 1


def test_numbered_references_keep_their_numbers(read):
    from apps.records.review_text.testing import BODY, BOLD, placed

    entries = [(f"[{n}]", f"A. Author{n}, \u201cTitle number {n},\u201d J. Studies, vol. {n}, 2020.") for n in range(1, 9)]
    lines = [(150, BOLD, 12, "REFERENCES")]
    for label, text in entries:
        lines += [(120, BODY, 9, label), (150, BODY, 9, text, True)]
    passages = [p["text"] for s in read(placed([lines]))["sections"] for p in s["passages"]]
    assert [p.split()[0] for p in passages] == [label for label, _ in entries]


def test_a_hanging_entry_carried_onto_the_next_page_ends_where_the_next_begins(read):
    # The entry begins at 72 with its body at 96. On the next page its lines
    # sit at 330, so its first line's distance (-24 pt) puts the next entry
    # at 306, where it begins.
    from apps.records.review_text.testing import BODY, BOLD, placed

    first = [(72, BOLD, 12, "References"),
             (72, BODY, 9, "Sommer, J. (2024). Updating, evidence evaluation, and operator"),
             (96, BODY, 9, "availability: a theoretical framework for understanding")]
    second = [(330, BODY, 9, "belief. Psychological Review, 131(2), 373-401."),
              (306, BODY, 9, "Zhu, P. (2024). Investor attention and consumer price"),
              (330, BODY, 9, "index inflation rate in the United States today.")]
    paragraphs = _paragraphs(read(placed([first, second])))
    assert len(paragraphs) == 2 and paragraphs[1].startswith("Zhu")
