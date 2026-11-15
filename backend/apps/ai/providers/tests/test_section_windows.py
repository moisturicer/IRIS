"""Section-aligned embedding windows (IR-1056). No database, no vendor."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.ai.providers.batching import (
    estimate_tokens,
    top_level_sections,
    window_for_embedding,
)

T = "A Thesis"


def _chunk(tokens: int) -> str:
    """Exactly ``tokens`` tokens."""
    return "w " * (tokens - 1) + "w"


def test_the_helper_is_exact():
    assert [estimate_tokens(_chunk(n)) for n in (20, 200, 2_000)] == [20, 200, 2_000]


def _flat(windows):
    return [t for window in windows for t in window]


def _sizes(windows):
    return [len(w) for w in windows]


class TestTopLevelSections:
    def test_the_shared_title_is_skipped(self):
        keys = [(T, "1 Intro"), (T, "1 Intro", "1.1 Aim"), (T, "2 Methods")]
        assert top_level_sections(keys) == ["1 Intro", "1 Intro", "2 Methods"]

    def test_a_paper_without_a_title_starts_at_its_first_heading(self):
        keys = [("1 Intro",), ("2 Methods", "2.1 Data")]
        assert top_level_sections(keys) == ["1 Intro", "2 Methods"]

    def test_front_matter_under_the_title_alone_is_its_own_section(self):
        keys = [(T,), (T, "1 Intro")]
        assert top_level_sections(keys) == ["", "1 Intro"]

    def test_a_missing_key_is_unknown_not_a_section(self):
        assert top_level_sections([None, [], (T, "1 Intro")]) == [None, None, ""]

    def test_stored_keys_are_lists(self):
        keys = [[T, "1 Intro"], [T, "2 Methods"]]
        assert top_level_sections(keys) == ["1 Intro", "2 Methods"]

    def test_a_single_chapter_paper_divides_at_its_next_level(self):
        keys = [(T, "1 Only", "1.1 A"), (T, "1 Only", "1.2 B")]
        assert top_level_sections(keys) == ["1.1 A", "1.2 B"]


class TestSectionAlignedWindows:
    def test_a_short_paper_is_one_window_as_before(self):
        texts = [_chunk(100), _chunk(100)]
        keys = [(T, "1 Intro"), (T, "2 Methods")]
        assert window_for_embedding(texts, budget=1_000, section_keys=keys) == [texts]

    def test_the_cut_moves_back_to_the_last_section_break_that_fits(self):
        # Count-based would cut after chunk 4 (1,000 tokens), splitting section 2.
        texts = [_chunk(200)] * 7
        keys = [(T, "1")] * 3 + [(T, "2")] * 4
        assert _sizes(window_for_embedding(texts, budget=1_000)) == [5, 2]

        windows = window_for_embedding(texts, budget=1_000, section_keys=keys)

        assert _sizes(windows) == [3, 4]
        assert _flat(windows) == texts

    def test_the_nearest_break_to_the_limit_wins(self):
        texts = [_chunk(200)] * 6
        keys = [(T, "1"), (T, "2"), (T, "2"), (T, "3"), (T, "3"), (T, "3")]
        assert _sizes(window_for_embedding(texts, budget=1_000, section_keys=keys)) == [3, 3]

    def test_a_break_exactly_at_the_limit_is_taken(self):
        texts = [_chunk(250)] * 6
        keys = [(T, "1")] * 4 + [(T, "2")] * 2
        assert _sizes(window_for_embedding(texts, budget=1_000, section_keys=keys)) == [4, 2]

    def test_a_section_longer_than_a_window_falls_back_to_the_count_cut(self):
        texts = [_chunk(300)] * 6
        keys = [(T, "1")] * 6
        assert window_for_embedding(texts, budget=1_000, section_keys=keys) == (
            window_for_embedding(texts, budget=1_000)
        )

    def test_no_usable_keys_is_exactly_the_count_cut(self):
        texts = [_chunk(300)] * 6
        for keys in ([None] * 6, [()] * 6, [[]] * 6):
            assert window_for_embedding(texts, budget=1_000, section_keys=keys) == (
                window_for_embedding(texts, budget=1_000)
            )

    def test_a_break_next_to_an_unkeyed_chunk_is_not_a_section_break(self):
        texts = [_chunk(300)] * 5
        keys = [(T, "1"), (T, "1"), None, (T, "2"), (T, "2")]
        assert window_for_embedding(texts, budget=1_000, section_keys=keys) == (
            window_for_embedding(texts, budget=1_000)
        )

    def test_an_oversized_chunk_still_goes_alone(self):
        texts = ["small", _chunk(2_000), "small"]
        keys = [(T, "1"), (T, "2"), (T, "3")]
        windows = window_for_embedding(texts, budget=1_000, section_keys=keys)
        assert [_chunk(2_000)] in windows
        assert _flat(windows) == texts

    def test_keys_must_match_the_texts(self):
        with pytest.raises(ValueError):
            window_for_embedding(["a", "b"], budget=1_000, section_keys=[(T, "1")])


_sections = st.lists(
    st.tuples(st.integers(1, 6), st.integers(20, 400)), min_size=1, max_size=12
)


@settings(max_examples=150, deadline=None)
@given(sections=_sections, budget=st.integers(300, 1_500))
def test_property_windows_fit_keep_order_and_never_split_a_section_needlessly(sections, budget):
    texts, keys = [], []
    for index, (count, tokens) in enumerate(sections):
        texts += [_chunk(tokens)] * count
        keys += [(T, f"{index} Section")] * count

    windows = window_for_embedding(texts, budget=budget, section_keys=keys)

    assert _flat(windows) == texts
    tops = top_level_sections(keys)
    start = 0
    for window in windows:
        end = start + len(window)
        if len(window) > 1:
            assert sum(estimate_tokens(t) for t in window) <= budget
        if end < len(texts) and tops[end - 1] == tops[end]:
            # Split inside a section: only allowed when no break fit.
            running = 0
            for i in range(start, len(texts)):
                running += estimate_tokens(texts[i])
                if running > budget:
                    break
                assert not (i + 1 < len(texts) and tops[i] != tops[i + 1]), (
                    f"window {start}..{end} split a section though a break at {i + 1} fit"
                )
        start = end
