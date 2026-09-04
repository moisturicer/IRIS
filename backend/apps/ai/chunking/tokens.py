"""Token counting.

Deliberately a whitespace estimator rather than a model tokenizer. Two
reasons: the count must be *deterministic across processes and versions* for
the tests that matter, and no vendor tokenizer is a dependency of the domain.

When a real tokenizer arrives it replaces this function. That is safe because
``token_count`` is excluded from the chunk-set hash precisely so a tokenizer
upgrade does not mark the whole corpus stale.
"""


def count_tokens(text: str) -> int:
    """Count tokens in ``text``.

    Whitespace-delimited words. Empty and whitespace-only strings count zero.
    """
    return len(text.split())
