"""Splitting a list of texts into vendor-sized batches (IR-128).

[ADR-015] caps a Voyage embedding request by **total input tokens** -- 120,000
with auto-chunking enabled, 32,000 without -- not by how many texts it carries.
An item-count rule is wrong in both directions: two hundred one-word strings
belong in a single request, and two full-page passages do not.
"""

from __future__ import annotations

from typing import Callable, Sequence

from apps.ai.chunking.tokens import count_tokens


def estimate_tokens(text: str) -> int:
    """What Voyage will charge this text against the request's token budget.

    **The same count the chunker uses** (IR-287): one tokenizer, one
    definition of a token, so a chunk built to fit a ceiling is batched
    against the vendor limit by the same arithmetic. This used to multiply
    the word count by a measured 1.4 because the domain carried no tokenizer;
    it carries the real one now, and an estimate that disagreed with the
    chunker was a second source of truth waiting to drift.

    Exact rather than padded. The budget below the vendor cap is where
    headroom belongs -- padding here would hide how much of the cap a batch
    actually uses.
    """
    return count_tokens(text)


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


def batch_documents_by_token_budget(
    documents: Sequence[Sequence[str]],
    budget: int,
    estimate: Callable[[str], int] = estimate_tokens,
) -> list[list[list[str]]]:
    """Group whole *documents* into requests whose estimated tokens stay
    under ``budget``.

    The unit is the document, not the chunk: contextualized embedding is only
    contextualized because a document's chunks travel together, so splitting
    one across two requests would silently produce vectors computed against
    half the context. A document larger than the whole budget is therefore
    sent **alone and whole**, on the same reasoning as an oversized single
    text next door — let the vendor reject it and say so, rather than quietly
    changing what the vectors mean.

    Order is preserved at both levels, because the caller matches vectors back
    to chunks positionally.
    """
    if budget <= 0:
        raise ValueError(f"budget must be positive, got {budget}")

    batches: list[list[list[str]]] = []
    current: list[list[str]] = []
    running = 0

    for document in documents:
        chunks = list(document)
        cost = sum(estimate(text) for text in chunks)
        if current and running + cost > budget:
            batches.append(current)
            current, running = [], 0
        current.append(chunks)
        running += cost

    if current:
        batches.append(current)
    return batches


#: The most tokens one contextualized *document* may carry (IR-423). Under
#: ``voyage-context-4``'s 32,000-token window with room to spare (~6%): the
#: estimator counts a text's own tokens and not the wrapping Voyage adds around
#: each chunk, and a document over the window is a 400 -- "contextualized chunk
#: embeddings do not support truncation" -- not a truncated success. Also below
#: the request budget in ``voyage.py`` so a window always fits a request alone.
EMBED_WINDOW_TOKENS = 30_000


def window_for_embedding(
    texts: Sequence[str],
    budget: int | None = None,
    estimate: Callable[[str], int] = estimate_tokens,
) -> list[list[str]]:
    """Cut one document's chunk texts into consecutive windows that each fit
    the model's context window (IR-423).

    The same rule as ``batch_by_token_budget`` -- consecutive, order preserved,
    nothing dropped, one oversized chunk left alone for the vendor to reject --
    named for what it decides here. **The trade-off is real and belongs on the
    record:** a chunk is contextualized only against its own window, so chunks
    either side of a window boundary no longer see each other. That is inherent
    to the model's limit; the alternative is no vectors at all. A paper that
    fits in one window is unchanged.

    The budget is read at call time, so a test (or a future setting) can move
    it without rebinding a default.
    """
    return batch_by_token_budget(
        texts, EMBED_WINDOW_TOKENS if budget is None else budget, estimate
    )
