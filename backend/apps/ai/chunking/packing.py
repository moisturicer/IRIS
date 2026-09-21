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

    The window is counted **as its caller will assemble it**, not as the sum
    of its pieces (IR-287). Token counts are not additive across a join: with
    a real tokenizer, joining two pieces can cost more than counting them
    apart, because the separator and the characters either side of it may
    merge differently. Summing was exact while a token was a whitespace word
    and became an undercount the moment it was not -- and an undercount here
    breaches the one guarantee this function exists to make.
    """
    windows: list[list[Piece]] = []
    current: list[Piece] = []
    current_text = ""

    for text, element in pieces:
        candidate = f"{current_text} {text}".strip() if current else text
        if current and count_tokens(candidate) > max_tokens:
            windows.append(current)
            current, candidate = [], text
        current.append((text, element))
        current_text = candidate

    if current:
        windows.append(current)
    return windows
