"""Greedy window packing over (text, element) pieces.

Shared by the fixed-window baseline and the structural cascade: both need to
fill windows under a token ceiling without ever exceeding it, and packing a
piece that does not yet fit is never this function's problem — the caller
must hand it pieces that already fit individually.

Pure: no I/O, no clock, no randomness.
"""

from typing import Any

from .tokens import count_tokens

Piece = tuple[str, Any]


def pack_pieces(pieces: list[Piece], max_tokens: int) -> list[list[Piece]]:
    """Greedily fill windows of pieces without exceeding ``max_tokens``.

    A piece is never split here — if a single piece's own token count
    exceeds ``max_tokens``, it is placed alone in its own (oversized) window
    rather than dropped or truncated. Splitting an oversized piece is the
    job of the stage that hands pieces to this function.
    """
    windows: list[list[Piece]] = []
    current: list[Piece] = []
    current_tokens = 0

    for text, element in pieces:
        tokens = count_tokens(text)
        if current and current_tokens + tokens > max_tokens:
            windows.append(current)
            current, current_tokens = [], 0
        current.append((text, element))
        current_tokens += tokens

    if current:
        windows.append(current)
    return windows
