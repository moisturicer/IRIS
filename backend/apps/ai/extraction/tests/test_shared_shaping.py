"""The shaping rules that outlived LlamaParse's shaping (IR-988)."""

import pytest

from apps.ai.chunking.document import DocumentElement
from apps.ai.extraction.shaping import CAPTION, FRONT_MATTER, split_formulas


@pytest.mark.parametrize("caption", [
    "TABLE I: Flit classes in MESHKV.", "Table 1: Expected turnover", "Figure 7: 4DProblem error",
    "Fig. 3 Latency per hop", "Tab. 2. Parameters",
])
def test_a_caption_is_recognised(caption):
    assert CAPTION.match(caption)


@pytest.mark.parametrize("heading", [
    "Table of Contents", "Figures and Tables", "Tableau results",
    "TABLES", "FIGURES", "FIGURES AND TABLES", "TABLET DESIGN",
])
def test_a_heading_that_only_mentions_tables_or_figures_is_not_a_caption(heading):
    assert not CAPTION.match(heading)


@pytest.mark.parametrize("text,matches", [
    ("Abstract", True), ("Keywords: rice", True), ("Abstraction layers", False),
])
def test_front_matter_matches_whole_words_only(text, matches):
    assert bool(FRONT_MATTER.match(text)) is matches


def test_display_formulas_split_out_without_changing_neighbouring_prose():
    element = DocumentElement(kind="text", text=r"Before $$x^2 = y$$ after \[a+b\] end.", page=1)

    assert [(e.kind, e.text) for e in split_formulas(element)] == [
        ("text", "Before "), ("formula", "x^2 = y"), ("text", " after "),
        ("formula", "a+b"), ("text", " end."),
    ]


def test_only_text_is_split():
    element = DocumentElement(kind="table", text="$$x$$", page=1)

    assert split_formulas(element) == [element]
