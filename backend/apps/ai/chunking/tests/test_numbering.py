"""Tests for outline-numbering recognition (IR-314).

Pure: a list of heading texts in, a list of depths out. No document, no
Django, no network.
"""

from apps.ai.chunking.numbering import outline_depths


def depths(*headings: str) -> list:
    return outline_depths(headings)


# ---------------------------------------------------------------------------
# Dotted decimals — the style that already worked, asserted unchanged
# ---------------------------------------------------------------------------


def test_dotted_decimals_keep_their_existing_depths():
    assert depths("3 Methodology", "3.2 Sampling", "3.2.1 Ponds") == [1, 2, 3]


def test_a_trailing_dot_and_extra_whitespace_do_not_matter():
    assert depths("1.   Introduction", "1.4.   References") == [1, 2]


def test_a_bare_number_with_no_text_is_not_a_section():
    assert depths("3") == [None]


def test_a_thousands_separator_is_not_a_section_number():
    assert depths("1,000 Samples") == [None]


def test_the_known_decimal_false_positive_is_unchanged():
    """`3.5 kg of Feed` is lexically a section number and still reads as one
    (IR-242's recorded false positive). This change must not make it worse."""
    assert depths("3.5 kg of Feed") == [2]


# ---------------------------------------------------------------------------
# Roman numerals
# ---------------------------------------------------------------------------


def test_roman_numeral_sections_are_top_level():
    assert depths("I. INTRODUCTION", "II. BACKGROUND", "IV. RESULTS") == [1, 1, 1]


def test_a_roman_numeral_may_close_with_a_parenthesis():
    assert depths("II) Background") == [1]


def test_a_word_that_merely_starts_with_roman_letters_is_not_a_numeral():
    assert depths("MIX Design", "Civil Engineering") == [None, None]


# ---------------------------------------------------------------------------
# Letters
# ---------------------------------------------------------------------------


def test_letter_sections_nest_under_the_enclosing_numbered_section():
    assert depths(
        "I. INTRODUCTION",
        "A. Transition Path Sampling",
        "B. AIMMD",
        "E. The GenAIMMD algorithm",
    ) == [1, 2, 2, 2]


def test_a_letter_needs_its_separator():
    """`A Contributions` is a word, not a numbering scheme — it stays
    unnumbered, exactly as before."""
    assert depths("A Contributions") == [None]


def test_letters_nest_under_decimal_sections_too():
    assert depths("2. Model Architecture", "A. Attention", "B. Routing") == [1, 2, 2]


# ---------------------------------------------------------------------------
# The ambiguity: I, V, X, L, C, D and M are both letters and roman numerals
# ---------------------------------------------------------------------------


def test_an_ambiguous_letter_continuing_a_letter_run_is_a_letter():
    """Record 36 runs subsections A through E. `C.` and `D.` are valid roman
    numerals; read as sections they would evict the section they belong to."""
    assert depths(
        "I. INTRODUCTION",
        "A. Transition Path Sampling",
        "B. AIMMD",
        "C. Committors",
        "D. Shooting",
        "E. The GenAIMMD algorithm",
    ) == [1, 2, 2, 2, 2, 2]


def test_an_ambiguous_letter_with_no_letter_run_open_is_a_numeral():
    assert depths("I. INTRODUCTION", "V. CONCLUSION") == [1, 1]


def test_a_new_section_restarts_the_letter_run():
    """Subsections restart at `A.` under each section, so the run from the
    previous section must not bleed across."""
    assert depths(
        "I. INTRODUCTION",
        "A. Scope",
        "B. Aims",
        "II. METHOD",
        "A. Materials",
    ) == [1, 2, 2, 1, 2]


def test_an_ambiguous_letter_after_a_broken_run_falls_back_to_the_numeral():
    """`H.` then `I.` is a run; `B.` then `I.` is not."""
    assert depths("1. Intro", "B. Aims", "I. METHOD") == [1, 2, 1]
    assert depths("1. Intro", "G. Aims", "H. Scope", "I. Limits") == [1, 2, 2, 2]


# ---------------------------------------------------------------------------
# Neither
# ---------------------------------------------------------------------------


def test_an_unnumbered_heading_has_no_derived_depth():
    assert depths("Self-consistency loop", "Fine-tuning") == [None, None]


def test_an_empty_or_blank_heading_has_no_derived_depth():
    assert depths("", "   ") == [None, None]


# ---------------------------------------------------------------------------
# Where a lettered subsection actually sits
# ---------------------------------------------------------------------------


def test_a_letter_nests_under_a_multi_level_decimal_section():
    """A letter claims a depth relative to the section enclosing it, not a
    fixed 2 — under `3.2` it is depth 3, or it would evict its own parent."""
    assert depths("3 Methodology", "3.2 Sampling", "A. Ponds", "B. Nets") == [
        1,
        2,
        3,
        3,
    ]


def test_a_letter_with_no_numbered_section_open_still_reads_as_a_subsection():
    assert depths("A. Scope", "B. Aims") == [2, 2]


def test_a_deeper_numbered_section_restarts_the_letter_run():
    """Subsections restart at `A.` under `3.2` as much as under `3.`, so a run
    must not bleed from one numbered heading into the next at any depth."""
    assert depths(
        "3.1 Sampling", "A. Ponds", "B. Nets", "3.2 Assay", "A. Reagents"
    ) == [2, 3, 3, 2, 3]


# ---------------------------------------------------------------------------
# Not a numeral
# ---------------------------------------------------------------------------


def test_a_separator_with_no_numeral_before_it_is_not_a_section():
    """The roman alternation is entirely optional, so it happily matches the
    empty string; a heading opening with bare punctuation must not be read as
    section one."""
    assert depths(". Foo", ") Bar") == [None, None]
