"""Comparing two Versions' review texts (ADR-058 §3, IR-873). Pure: each
test draws two PDFs with reportlab, reads both with the review text reader in
this process, and compares the readings, so no database is needed and every
edit is known. One known edit per pair, and each must be reported as exactly
that edit and nothing else."""
import copy
import hashlib
import json
import tempfile
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import A4

from apps.records.review_text import reader
from apps.records.review_text.testing import THESIS, pdf
from apps.reviews import comparison
from apps.reviews.comparison import (
    ADDED, CHANGED, COMPARISON_VERSION, MOVED, REMOVED, TENTATIVE, UNCHANGED, compare,
)

REFERENCES = [
    ("plain", "REFERENCES"),
    ("para", ["Cruz, J. (2019). Small plants in Cebu. Cebu Press."]),
]
PAPER = copy.deepcopy(THESIS) + [REFERENCES]


def read(pages, **drawing) -> dict:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "paper.pdf"
        path.write_bytes(pdf(pages, **drawing))
        return reader.read(path)


def edited(change) -> list:
    pages = copy.deepcopy(PAPER)
    change(pages)
    return pages


def only_change(result) -> dict:
    """The comparison's one change, failing if there is any other."""
    changes = [c for s in result["sections"] for c in s["changes"]] or result["changes"]
    unique = list({id(c): c for c in changes}.values())
    assert len(unique) == 1, json.dumps(unique, indent=1)
    return unique[0]


def marked(change) -> list:
    return [(w["op"], w["text"]) for w in change["words"] if w["op"] != "equal"]


@pytest.fixture(scope="module")
def v1():
    return read(PAPER)


@pytest.mark.parametrize("text", [
    "ﬁnal ﬂow", "“Quoted” and ‘single’", "  spaced\tout\n  text ", "Ⅻ ½ ①", "plain",
])
def test_the_comparison_normalises_exactly_as_the_reader_does(text):
    # Repeated in comparison.py because the reader is never imported outside
    # the sandbox; the two must not drift apart.
    assert comparison._reader_norm(text) == reader.norm(text)


class TestUnchanged:

    def test_the_same_paper_reads_unchanged(self, v1):
        result = compare(v1, read(PAPER))
        assert all(s["status"] == UNCHANGED for s in result["sections"])
        assert result["counts"] == {CHANGED: 0, ADDED: 0, REMOVED: 0, MOVED: 0,
                                    "sections_renamed": 0, "sections_moved": 0}

    def test_two_typesettings_of_the_same_text_read_unchanged(self, v1):
        # Another page size, running head and page-number position.
        other = read(PAPER, size=A4, running_head="Waste-to-Energy Study", number_at=50)
        result = compare(v1, other)
        assert [s["status"] for s in result["sections"]] == [UNCHANGED] * len(result["sections"])
        assert result["notices"] == []

    def test_a_hyphen_between_letters_is_no_change_but_one_between_digits_is(self):
        old = {"page_count": 1, "warnings": [], "sections": [_section("results", [
            "The small-scale plant ran.", "It ran on days 2-3."])]}
        new = {"page_count": 1, "warnings": [], "sections": [_section("results", [
            "The smallscale plant ran.", "It ran on days 23."])]}
        change = only_change(compare(old, new))
        assert change["kind"] == CHANGED
        assert marked(change) == [("delete", "2-3."), ("insert", "23.")]


class TestControlledEdits:
    """Each pair differs by one known edit (IR-873's acceptance criteria)."""

    def test_a_changed_number(self, v1):
        def change(p):
            p[1][3] = ("para", [line.replace("2,000", "2,500") for line in p[1][3][1]])
        found = only_change(compare(v1, read(edited(change))))
        assert found["kind"] == CHANGED
        assert found["from"]["section"] == "background of the study"
        assert marked(found) == [("delete", "2,000"), ("insert", "2,500")]
        assert found["from"]["page"] == found["to"]["page"] == 2
        assert found["from"]["regions"] and found["to"]["regions"]

    def test_a_rewritten_sentence(self, v1):
        def change(p):
            p[1][5] = ("para", ["This study examines if one plant could be feasible."])
        found = only_change(compare(v1, read(edited(change))))
        assert found["kind"] == CHANGED
        assert found["to"]["text"] == "This study examines if one plant could be feasible."

    def test_an_added_paragraph(self, v1):
        def change(p):
            p[2].insert(3, ("para", ["A second digester study was run in Iloilo."]))
        found = only_change(compare(v1, read(edited(change))))
        assert (found["kind"], found["from"]) == (ADDED, None)
        assert found["to"]["section"] == "review of related literature"

    def test_a_removed_paragraph(self, v1):
        # Removing it also removes the paper's only other "small-scale", which
        # changes how the reader joins "small-/scale" elsewhere; that must not
        # read as a second change.
        def change(p):
            del p[2][2]
        found = only_change(compare(v1, read(edited(change))))
        assert (found["kind"], found["to"]) == (REMOVED, None)
        assert found["from"]["text"] == "Earlier studies used small-scale digesters in Davao."

    def test_a_paragraph_moved_to_another_section(self, v1):
        def change(p):
            p[2].insert(2, p[1].pop(5))
        result = compare(v1, read(edited(change)))
        found = only_change(result)
        assert found["kind"] == MOVED
        assert (found["from"]["section"], found["to"]["section"]) == (
            "statement of the problem", "review of related literature")
        # Shown in both sections, counted once.
        holding = [s["to"]["key"] for s in result["sections"] if found in s["changes"]]
        assert holding == ["statement of the problem", "review of related literature"]
        assert result["counts"][MOVED] == 1

    def test_a_renamed_heading(self, v1):
        def change(p):
            p[1][4] = ("plain", "1.2 Research Questions")
        result = compare(v1, read(edited(change)))
        [renamed] = [s for s in result["sections"] if s["renamed"]]
        assert (renamed["from"]["key"], renamed["to"]["key"]) == ("statement of the problem",
                                                                  "research questions")
        assert renamed["status"] == CHANGED and renamed["changes"] == []
        assert [s for s in result["sections"] if s is not renamed and s["status"] != UNCHANGED] == []
        assert result["counts"]["sections_renamed"] == 1

    def test_an_edited_table_row(self, v1):
        def change(p):
            p[2][3] = ("table", [["Technology", "Output"], ["Digestion", "45 kW"],
                                 ["Gasification", "90 kW"]])
        found = only_change(compare(v1, read(edited(change))))
        assert found["kind"] == CHANGED
        assert marked(found) == [("delete", "40"), ("insert", "45")]

    def test_a_changed_reference(self, v1):
        def change(p):
            p[3][1] = ("para", ["Cruz, J. (2018). Small plants in Cebu. Cebu Press."])
        found = only_change(compare(v1, read(edited(change))))
        assert found["kind"] == CHANGED and found["from"]["section"] == "references"
        assert marked(found) == [("delete", "(2019)."), ("insert", "(2018).")]

    def test_a_section_moved_whole(self, v1):
        def change(p):
            p[1][2:6] = p[1][4:6] + p[1][2:4]          # 1.2 now before 1.1
        result = compare(v1, read(edited(change)))
        assert result["counts"]["sections_moved"] == 1
        assert [c for s in result["sections"] for c in s["changes"]] == []


class TestNeverForced:

    def test_a_one_character_change_is_changed_never_unchanged(self, v1):
        def change(p):
            p[1][5] = ("para", ["This study asks whether a plant is feasib1e."])
        found = only_change(compare(v1, read(edited(change))))
        assert found["kind"] == CHANGED
        assert marked(found) == [("delete", "feasible."), ("insert", "feasib1e.")]

    def test_a_section_with_new_heading_and_new_text_is_removed_and_added_not_renamed(self, v1):
        def change(p):
            p[1][4] = ("plain", "1.2 Scope and Delimitation")
            p[1][5] = ("para", ["Only Metro Cebu barangays were surveyed in 2024."])
        result = compare(v1, read(edited(change)))
        statuses = {(s["from"] or s["to"])["key"]: s["status"] for s in result["sections"]
                    if s["status"] != UNCHANGED}
        assert statuses == {"statement of the problem": REMOVED, "scope and delimitation": ADDED}
        assert not any(s["renamed"] for s in result["sections"])


class TestTrust:

    def test_sections_that_couldnt_be_identified_are_compared_by_page(self, v1):
        def change(p):
            p[1][3] = ("para", [line.replace("2,000", "2,500") for line in p[1][3][1]])
        new = _collapsed(read(edited(change)))
        result = compare(v1, new)
        assert result["mode"] == "pages" and result["sections"] == []
        assert result["notices"] == [{"code": "sections_unidentified", "side": "to"}]
        found = only_change(result)
        assert found["kind"] == CHANGED and found["to"]["page"] == 2
        assert marked(found) == [("delete", "2,000"), ("insert", "2,500")]

    def test_text_that_shrinks_on_the_same_pages_is_doubted_and_its_removals_tentative(self, v1):
        # Same three pages of body (plus references), most of the text gone:
        # more likely text the reader missed than an author's edit.
        def change(p):
            p[1][3] = ("para", ["Metro Cebu generates waste."])
            del p[2][2:]
        result = compare(v1, read(edited(change)))
        assert {"code": "may_be_unreliable", "side": "to"} in result["notices"]
        removals = [c for s in result["sections"] for c in s["changes"] if c["kind"] == REMOVED]
        assert removals and all(c["certainty"] == TENTATIVE for c in removals)

    @pytest.mark.parametrize("kept, pages, doubted", [
        (61, 10, False),    # 39% fewer words: an edit
        (59, 10, True),     # 41% fewer: text the reader may have missed
        (59, 9, True),      # one page fewer is still the same pages
        (59, 8, False),     # 20% fewer pages: the paper was cut, so the words were too
    ])
    def test_the_text_jump_is_doubted_only_past_its_threshold_on_steady_pages(
            self, kept, pages, doubted):
        # TEXT_JUMP is 40% of the words; PAGE_STEADY is 10% of the pages, or one.
        assert (comparison.TEXT_JUMP, comparison.PAGE_STEADY) == (0.4, 0.1)
        sentences = [f"Sentence number {n} of the paper." for n in range(100)]
        old = {"page_count": 10, "warnings": [], "sections": [_section("body", [
            " ".join(sentences[i:i + 4]) for i in range(0, 100, 4)])]}
        words = [w for s in sentences for w in s.split()]
        cut = " ".join(words[:len(words) * kept // 100])
        new = {"page_count": pages, "warnings": [], "sections": [_section("body", [cut])]}
        notices = compare(old, new)["notices"]
        assert (notices == [{"code": "may_be_unreliable", "side": "to"}]) is doubted, notices

    def test_more_text_on_the_same_pages_doubts_the_earlier_version_and_its_additions(self, v1):
        def change(p):
            p[1][3] = ("para", ["Metro Cebu generates waste."])
            del p[2][2:]
        result = compare(read(edited(change)), v1)
        assert {"code": "may_be_unreliable", "side": "from"} in result["notices"]
        changes = [c for s in result["sections"] for c in s["changes"]]
        assert {c["certainty"] for c in changes if c["kind"] == ADDED} == {TENTATIVE}
        assert all(c["certainty"] != TENTATIVE for c in changes if c["kind"] == REMOVED)

    def test_pages_without_text_matter_only_when_they_differ(self, v1):
        same = dict(v1, warnings=[{"code": "pages_without_text", "pages": [3]}])
        assert compare(same, same)["notices"] == []
        more = dict(v1, warnings=[{"code": "pages_without_text", "pages": [2, 3]}])
        assert compare(same, more)["notices"] == [{"code": "may_be_unreliable", "side": "to"}]


class TestReproducible:

    def test_every_comparison_carries_its_version_and_repeats_exactly(self, v1):
        new = read(edited(lambda p: p[2].insert(3, ("para", ["A second study ran."]))))
        first, second = compare(v1, new), compare(copy.deepcopy(v1), copy.deepcopy(new))
        assert first["comparison_version"] == COMPARISON_VERSION
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


class TestAppearsIn:

    def test_text_is_found_inside_and_across_passages_or_not_at_all(self, v1):
        [inside] = comparison.appears_in(v1, "whether a plant is feasible")
        assert [(p["section"], p["page"]) for p in inside] == [("statement of the problem", 2)]
        [across] = comparison.appears_in(v1, "small-scale plants. The municipal government")
        assert len(across) == 2 and {p["page"] for p in across} == {2}
        assert comparison.appears_in(v1, "a sentence nobody wrote") == []


class TestDocuments:

    def test_each_slot_reads_unchanged_replaced_added_or_removed(self):
        old = [{"slot": "Consent form", "upload_id": 1}, {"slot": "Approval sheet", "upload_id": 2},
               {"slot": "Endorsement", "upload_id": 3}]
        new = [{"slot": "Consent form", "upload_id": 4}, {"slot": "Approval sheet", "upload_id": 2},
               {"slot": "Ethics clearance", "upload_id": 5}]
        assert {d["slot"]: d["status"] for d in comparison.compare_documents(old, new)} == {
            "Approval sheet": UNCHANGED, "Consent form": "replaced",
            "Endorsement": REMOVED, "Ethics clearance": ADDED,
        }


# --- helpers --------------------------------------------------------------------

def _section(key, sentences, page=1):
    passages = [{"text": t, "page": page, "paragraph": 1, "kind": "sentence", "regions": []}
                for t in sentences]
    digest = hashlib.sha256("\n".join(sentences).encode()).hexdigest()
    return {"key": key, "heading": key.title(), "page": page, "text_hash": digest,
            "passages": passages}


def _collapsed(reading) -> dict:
    """``reading`` as the reader stores a paper whose sections it can't trust:
    one ``document`` section holding every passage (ADR-058 §1, build note 5)."""
    passages = [p for s in reading["sections"] for p in s["passages"]]
    return dict(reading, warnings=[{"code": "sections_unreliable", "reasons": ["no_headings"]}],
                sections=[{"key": "document", "heading": "", "page": 1, "text_hash": "collapsed",
                           "passages": passages}])
