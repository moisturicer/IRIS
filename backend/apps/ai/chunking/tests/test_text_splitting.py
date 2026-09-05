"""Tests for the pure text-splitting helpers the cascade's later stages use.

Nothing here touches Django, a database, the network, or the clock.
"""

import unicodedata

from hypothesis import given, settings, strategies as st

from apps.ai.chunking.text_splitting import (
    grapheme_safe_split,
    split_into_clauses,
    split_into_sentences,
    split_into_word_groups,
)

# --------------------------------------------------------------------------
# Sentence splitting
# --------------------------------------------------------------------------


def test_splits_on_sentence_terminators():
    text = "First sentence. Second sentence! Third one? Fourth."
    assert split_into_sentences(text) == [
        "First sentence.",
        "Second sentence!",
        "Third one?",
        "Fourth.",
    ]


def test_single_sentence_with_no_terminator_is_returned_whole():
    assert split_into_sentences("no terminator here") == ["no terminator here"]


def test_sentence_splitting_loses_no_content():
    text = "One. Two. Three four five. Six?"
    assert " ".join(split_into_sentences(text)) == text


def test_empty_text_splits_to_no_sentences():
    assert split_into_sentences("") == []
    assert split_into_sentences("   ") == []


# --------------------------------------------------------------------------
# Clause splitting
# --------------------------------------------------------------------------


def test_splits_on_clause_boundaries():
    text = "alpha, beta; gamma"
    assert split_into_clauses(text) == ["alpha,", "beta;", "gamma"]


def test_no_clause_boundary_returns_whole_text():
    assert split_into_clauses("alpha beta gamma") == ["alpha beta gamma"]


def test_clause_splitting_loses_no_content():
    text = "alpha, beta; gamma, delta"
    assert " ".join(split_into_clauses(text)) == text


# --------------------------------------------------------------------------
# Word-group splitting (the word-boundary guarantee)
# --------------------------------------------------------------------------


def test_splits_into_groups_of_at_most_max_words():
    words = ["w" + str(i) for i in range(25)]
    text = " ".join(words)

    groups = split_into_word_groups(text, max_words=10)

    assert [g.split() for g in groups] == [
        words[0:10],
        words[10:20],
        words[20:25],
    ]


def test_word_group_splitting_loses_no_content():
    text = "one two three four five six seven"
    groups = split_into_word_groups(text, max_words=3)
    assert " ".join(groups) == text


def test_word_group_of_a_single_word_returns_that_word():
    assert split_into_word_groups("solitary", max_words=5) == ["solitary"]


# --------------------------------------------------------------------------
# Grapheme-safe hard splitting — the ceiling's last resort
# --------------------------------------------------------------------------


def test_short_text_is_returned_as_a_single_piece():
    assert grapheme_safe_split("hello", max_chars=10) == ("hello",)


def test_splits_long_text_into_chunks_near_the_budget():
    text = "a" * 50
    pieces = grapheme_safe_split(text, max_chars=10)

    assert "".join(pieces) == text
    assert all(len(p) <= 10 for p in pieces)


def test_never_splits_inside_a_combining_grapheme_cluster():
    """A base character followed by combining marks must stay in one piece.

    Composed with NFD so the diacritics are separate combining codepoints
    rather than pre-composed — exactly the shape Filipino/Cebuano text with
    heavy diacritics takes after normalization.
    """
    base = "ñ"  # n + combining tilde, decomposed
    text = unicodedata.normalize("NFD", base * 30)

    pieces = grapheme_safe_split(text, max_chars=7)

    assert "".join(pieces) == text
    for piece in pieces:
        assert not unicodedata.combining(piece[0]), (
            "a piece must never start with a combining mark"
        )


def test_grapheme_safe_split_never_loses_or_reorders_characters():
    text = "x" * 5 + "́" * 3 + "y" * 5
    pieces = grapheme_safe_split(text, max_chars=4)
    assert "".join(pieces) == text


@settings(max_examples=50)
@given(
    text=st.text(
        alphabet=st.characters(
            whitelist_categories=("Ll", "Mn"), max_codepoint=0x0370
        ),
        min_size=0,
        max_size=200,
    ),
    max_chars=st.integers(min_value=1, max_value=30),
)
def test_property_grapheme_safe_split_reconstructs_exactly(text, max_chars):
    pieces = grapheme_safe_split(text, max_chars=max_chars)
    assert "".join(pieces) == text
    # A boundary must never separate a base character from a combining mark
    # that followed it in the original text. A stray leading combining mark
    # in the *input itself* (no base to attach to) is a malformed-input case
    # the splitter cannot fix, so only pieces after the first are checked.
    for piece in pieces[1:]:
        if piece:
            assert not unicodedata.combining(piece[0])


def test_grapheme_safe_split_of_empty_text_is_empty():
    assert grapheme_safe_split("", max_chars=10) == ()
