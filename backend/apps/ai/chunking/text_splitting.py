"""Sentence, clause, word and grapheme splitting — the cascade's later stages.

Each function here handles one level of the cascade in
:mod:`apps.ai.chunking.strategies.structural` and is deliberately usable on
its own: a good test of a splitter asserts what it does to text, not how the
cascade happens to call it.

Pure: no Django, no I/O, no clock, no randomness. ``unicodedata.combining``
rather than a grapheme-cluster library, because the one property that
actually matters for citation text — a combining mark never separated from
its base character — does not need full UAX #29 segmentation to guarantee.
"""

import re
import unicodedata

# A sentence ends at `.`, `!` or `?` followed by whitespace (or end of
# string). The terminator stays attached to the sentence it closes.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")

# A clause ends at `,` or `;` followed by whitespace. Coarser than a sentence,
# finer than a word — the cascade's stage between the two.
_CLAUSE_BOUNDARY = re.compile(r"(?<=[,;])\s+")


def split_into_sentences(text: str) -> list[str]:
    """Split ``text`` into sentences, terminator attached to each.

    Text with no sentence terminator is returned as one sentence. Empty or
    whitespace-only text splits to no sentences at all.
    """
    text = text.strip()
    if not text:
        return []
    return [s for s in _SENTENCE_BOUNDARY.split(text) if s]


def split_into_clauses(text: str) -> list[str]:
    """Split ``text`` into clauses on `,`/`;` boundaries.

    Text with no clause boundary is returned as one clause.
    """
    text = text.strip()
    if not text:
        return []
    return [c for c in _CLAUSE_BOUNDARY.split(text) if c]


def split_into_word_groups(text: str, max_words: int) -> list[str]:
    """Split ``text`` into groups of at most ``max_words`` whitespace-words.

    This is the guarantee of last resort at the word level: grouping on
    whitespace can never land inside a grapheme cluster, because a cluster
    never contains whitespace.
    """
    words = text.split()
    if not words:
        return []
    max_words = max(1, max_words)
    return [
        " ".join(words[start : start + max_words])
        for start in range(0, len(words), max_words)
    ]


def grapheme_safe_split(text: str, max_chars: int) -> tuple[str, ...]:
    """Hard-split ``text`` into pieces near ``max_chars``, never mid-cluster.

    The true last resort: reached only when a single word has no internal
    whitespace to split on. A boundary is never placed before a combining
    mark — the piece is extended forward until it reaches a base character —
    so a piece may run slightly past ``max_chars`` rather than sever a
    character from its diacritics.
    """
    if not text:
        return ()
    max_chars = max(1, max_chars)

    pieces: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + max_chars, length)
        while end < length and unicodedata.combining(text[end]):
            end += 1
        if end <= start:
            end = start + 1
        pieces.append(text[start:end])
        start = end
    return tuple(pieces)
