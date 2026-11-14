"""A label can point at a figure by page and box (IR-1125). Pure."""

from types import SimpleNamespace

import pytest

from apps.ai.evaluation.labels import QuestionSetError, parse_question_set
from apps.ai.regions import Region


def _set(label):
    return parse_question_set({
        "name": "figures",
        "questions": [{"id": "f1", "question": "Which model is most accurate?", "expected": [label]}],
    })


FIGURE = {"record": "Paper", "page": 3, "region": {"left": 0.1, "top": 0.2, "right": 0.5, "bottom": 0.6}}


def passage(*regions, title="Paper"):
    return SimpleNamespace(record_id=1, record_title=title, content="", regions=regions)


def test_an_uncaptioned_figure_needs_no_quote():
    label = _set(FIGURE).questions[0].expected[0]

    assert label.is_figure and label.quote == ""
    assert label.describe.startswith("figure p3")


def test_a_figure_matches_by_page_and_overlap_not_by_text():
    label = _set(FIGURE).questions[0].expected[0]

    assert label.matches(passage(Region(3, 0.12, 0.25, 0.5, 0.6)))
    assert not label.matches(passage(Region(4, 0.1, 0.2, 0.5, 0.6)))
    assert not label.matches(passage(Region(3, 0.45, 0.2, 0.9, 0.6)))
    assert not label.matches(passage(Region(3, 0.1, 0.2, 0.5, 0.6), title="Other"))


@pytest.mark.parametrize("bad", [
    {**FIGURE, "page": None},
    {**FIGURE, "region": {"left": 0.5, "top": 0.2, "right": 0.1, "bottom": 0.6}},
    {**FIGURE, "region": {"left": 0.1, "top": 0.2, "right": 1.5, "bottom": 0.6}},
    {**FIGURE, "region": {"left": 0.1}},
])
def test_a_malformed_region_is_refused(bad):
    with pytest.raises(QuestionSetError):
        _set(bad)


def test_a_captioned_figure_may_carry_a_quote_too_and_it_is_validated():
    with pytest.raises(QuestionSetError):
        _set({**FIGURE, "quote": "too short"})
    label = _set({**FIGURE, "quote": "Figure 2: loss curves for every model"}).questions[0].expected[0]
    assert label.as_dict()["region"]["right"] == 0.5
