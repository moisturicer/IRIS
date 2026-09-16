"""Splitting a list of texts into vendor-sized batches (IR-128).

[ADR-015] caps a Voyage embedding request by **total input tokens** -- 120,000
with auto-chunking enabled, 32,000 without -- not by how many texts it carries.
An item-count rule is wrong in both directions: two hundred one-word strings
belong in a single request, and two full-page passages do not.
"""

from __future__ import annotations

import math
from typing import Callable, Sequence

#: Words-to-tokens multiplier. Measured rather than guessed: an IRIS chunk at
#: the 512-word ceiling is roughly 700 real BPE tokens (IR-243), so ~1.37.
#: Rounded up, because this guards a ceiling -- undercounting sails past the
#: vendor limit and 400s, while overcounting costs one extra request.
_TOKENS_PER_WORD = 1.4


def estimate_tokens(text: str) -> int:
    """A deliberately conservative token estimate.

    Not a tokenizer: the pure domain carries no vendor tokenizer dependency
    (see `apps.ai.chunking.tokens`), and for a budget check an upper bound is
    worth more than an exact count.
    """
    words = len(text.split())
    return math.ceil(words * _TOKENS_PER_WORD) if words else 0


def batch_by_token_budget(
    texts: Sequence[str],
    budget: int,
    estimate: Callable[[str], int] = estimate_tokens,
) -> list[list[str]]:
    """Group ``texts`` into batches whose estimated tokens stay under ``budget``.

    Order is preserved and nothing is dropped -- a caller matches returned
    vectors back to inputs positionally, so a reordering here would silently
    attach the wrong vector to the wrong chunk.

    A single text larger than the whole budget is sent **alone rather than
    split**. Splitting it would embed half a passage and quietly change what
    the vector means; sending it alone lets the vendor reject it and say so,
    which is a failure someone can act on.
    """
    if budget <= 0:
        raise ValueError(f"budget must be positive, got {budget}")

    batches: list[list[str]] = []
    current: list[str] = []
    running = 0

    for text in texts:
        cost = estimate(text)
        if current and running + cost > budget:
            batches.append(current)
            current, running = [], 0
        current.append(text)
        running += cost

    if current:
        batches.append(current)
    return batches
