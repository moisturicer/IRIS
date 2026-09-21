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

from .tokens import count_tokens

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


def split_into_token_groups(text: str, max_tokens: int) -> list[str]:
    """Split ``text`` into whitespace-word runs of at most ``max_tokens`` tokens.

    This is the guarantee of last resort at the word level: grouping on
    whitespace can never land inside a grapheme cluster, because a cluster
    never contains whitespace.

    The budget is counted, not estimated from the word count (IR-287). A
    fixed words-per-group rule was correct only while a "token" *was* a word;
    with a real tokenizer it under-fills prose and, worse, over-fills
    token-dense text such as LaTeX -- and an over-full group does not fit,
    so the cascade would fall straight through to splitting word by word.

    A single word larger than the whole budget is returned alone rather than
    cut; severing it is the grapheme stage's job, not this one's.
    """
    words = text.split()
    if not words:
        return []
    max_tokens = max(1, max_tokens)

    groups: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = current + [word]
        if current and count_tokens(" ".join(candidate)) > max_tokens:
            groups.append(" ".join(current))
            current = [word]
        else:
            current = candidate
    if current:
        groups.append(" ".join(current))
    return groups


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
