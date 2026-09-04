"""Tests for the shared greedy word-count packer.

Both the fixed-window baseline and the structural cascade pack (text,
element) pieces into windows under a token ceiling the same way; this is
that one piece of shared logic, tested once.
"""

from apps.ai.chunking.document import PARAGRAPH, DocumentElement
from apps.ai.chunking.packing import pack_pieces
from apps.ai.chunking.tokens import count_tokens


def _piece(text):
    return (text, DocumentElement(kind=PARAGRAPH, text=text))


def test_packs_pieces_under_the_ceiling_into_one_window():
    pieces = [_piece("alpha"), _piece("beta"), _piece("gamma")]
    windows = pack_pieces(pieces, max_tokens=10)
    assert len(windows) == 1
    assert [p[0] for p in windows[0]] == ["alpha", "beta", "gamma"]


def test_starts_a_new_window_when_the_ceiling_would_be_exceeded():
    pieces = [_piece("one two"), _piece("three four"), _piece("five six")]
    windows = pack_pieces(pieces, max_tokens=4)

    for window in windows:
        total = sum(count_tokens(text) for text, _ in window)
        assert total <= 4
    assert sum(len(w) for w in windows) == len(pieces)


def test_a_single_oversized_piece_gets_its_own_window():
    """The packer never splits a piece itself — that is stages above it."""
    pieces = [_piece("one two three four five")]
    windows = pack_pieces(pieces, max_tokens=2)
    assert len(windows) == 1
    assert windows[0] == pieces


def test_empty_input_produces_no_windows():
    assert pack_pieces([], max_tokens=10) == []


def test_packing_preserves_order():
    pieces = [_piece(f"word{i}") for i in range(20)]
    windows = pack_pieces(pieces, max_tokens=5)
    flattened = [p for window in windows for p in window]
    assert flattened == pieces
