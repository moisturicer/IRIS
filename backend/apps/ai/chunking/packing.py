"""Greedy window packing over (text, element) pieces.

Shared by the fixed-window baseline and the structural cascade: both need to
fill windows under a token ceiling without ever exceeding it, and packing a
piece that does not yet fit is never this function's problem — the caller
must hand it pieces that already fit individually.

Pure except for one read: counting a token means loading the vendored
``voyage-context-4`` vocabulary once per process (see ``tokens``). No Django,
no database, no network, no clock, no randomness.
"""

from typing import Any, Iterable

from .tokens import count_tokens

Piece = tuple[str, Any]

#: How every stage joins the parts of a window back into one string. Shared
#: so that what gets *counted* and what gets *emitted* cannot drift apart.
JOIN = " "


def assembled(parts: Iterable[str]) -> str:
    """Join ``parts`` the way the emitting stage will."""
    return JOIN.join(part for part in parts if part).strip()


def assembled_fits(parts: Iterable[str], max_tokens: int) -> bool:
    """Whether ``parts``, once joined, stay under ``max_tokens``.

    **Counted as assembled, never summed (IR-287).** Token counts are not
    additive across a join: with a real tokenizer, joining two strings can
    cost more than counting them apart, because the separator and the
    characters either side of it may merge differently. Summing was exact
    while a token was a whitespace word, and became an undercount the moment
    it was not -- an undercount that breaches the one guarantee every packing
    stage in this package exists to make.

    Every stage that fills a window under the ceiling goes through here, so
    there is one place the rule is stated and one place it can be wrong.
    """
    return count_tokens(assembled(parts)) <= max_tokens


def pack_pieces(pieces: list[Piece], max_tokens: int) -> list[list[Piece]]:
    """Greedily fill windows of pieces without exceeding ``max_tokens``.

    A piece is never split here — if a single piece's own token count
    exceeds ``max_tokens``, it is placed alone in its own (oversized) window
    rather than dropped or truncated. Splitting an oversized piece is the
    job of the stage that hands pieces to this function.

    The window is counted **as its caller will assemble it**, not as the sum
    of its pieces -- see ``assembled_fits`` for why that distinction is the
    whole of IR-287's effect on this module.
    """
    windows: list[list[Piece]] = []
    current: list[Piece] = []

    for piece in pieces:
        text = piece[0]
        if current and not assembled_fits([t for t, _ in current] + [text], max_tokens):
            windows.append(current)
            current = []
        current.append(piece)

    if current:
        windows.append(current)
    return windows
