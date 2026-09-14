"""Token counting.

Deliberately a whitespace estimator rather than a model tokenizer. Two
reasons: the count must be *deterministic across processes and versions* for
the tests that matter, and no vendor tokenizer is a dependency of the domain.

When a real tokenizer arrives it replaces this function. That is safe because
``token_count`` is excluded from the chunk-set hash precisely so a tokenizer
upgrade does not mark the whole corpus stale.

**The unit is words, and "512" does not mean 512 tokens (IR-243).** Measured
on a real 47-page submission: an IRIS chunk at the ceiling holds 511 words,
while docling-core's ``HybridChunker(max_tokens=512)`` -- a real BPE
tokenizer, same source PDF, same conversion -- caps at 355 words for the same
nominal budget. ``AI_CHUNK_MAX_TOKENS=512`` therefore produces chunks roughly
44% larger in real embedding-tokenizer terms than the number suggests; the
rough equivalent of the Docling default is nearer 360 words.

Nothing overflows -- ``voyage-context-4`` has ample context -- so IR-243
**deliberately did not recalibrate the default**. What the right ceiling is
for theses is a retrieval-quality question, and IR-133's recall@10 harness is
what can answer it; picking a number now would substitute taste for the
measurement the eval set exists to provide, and would re-chunk and re-embed
the whole corpus on a guess. The number stays 512 words until there is
evidence, and this paragraph exists so nobody reads it as 512 tokens in the
meantime.
"""


def count_tokens(text: str) -> int:
    """Count tokens in ``text``.

    Whitespace-delimited words. Empty and whitespace-only strings count zero.
    """
    return len(text.split())
